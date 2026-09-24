"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from search_medical_embeddings import rank
from web_app.config import settings
from web_app.sessions import SessionData

logger = logging.getLogger("naturist.retrieval")

GENERIC_QUERY_WORDS_PATH = Path(__file__).with_name("generic_query_words.txt")
GENERIC_QUERY_WORDS = frozenset(
    GENERIC_QUERY_WORDS_PATH.read_text(encoding="utf-8").split()
)

# Normalize text for case-insensitive and diacritic-insensitive comparisons.
def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


# Split long consultation text into bounded search queries without losing its tail.
def _split_query(value: str, limit: int = 900) -> list[str]:
    """Split long consultation text without dropping its tail."""
    remaining = " ".join(value.split())
    parts: list[str] = []
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        parts.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    return [part for part in parts if part]


# Extract searchable words while excluding short and generic terms.
def _meaningful_words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"\w+", _plain(value))
        if len(word) >= 4 and word not in GENERIC_QUERY_WORDS
    }


# Check whether a complete phrase occurs after normalizing case and diacritics.
def _contains_exact_phrase(value: str, phrase: str) -> bool:
    """Match the complete user problem while ignoring case and diacritics."""
    normalized_value = " ".join(_plain(value).split())
    normalized_phrase = " ".join(_plain(phrase).split())
    if not normalized_phrase:
        return False
    return bool(re.search(
        rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
        normalized_value,
    ))


# Build deduplicated bounded queries from the entire consultation profile.
def consultation_queries(profile: Any) -> list[str]:
    """Build bounded queries from every meaningful consultation exchange."""
    values: list[str] = []
    if profile.health_problem:
        values.append(profile.health_problem)

    pending_question = ""
    for entry in profile.transcript:
        role = entry.get("role")
        content = str(entry.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            pending_question = content
        elif role == "user":
            values.append(
                f"Întrebare: {pending_question} Răspuns: {content}"
                if pending_question else f"Informație utilizator: {content}"
            )
            pending_question = ""

    values.extend(profile.health_context)
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in _split_query(value):
            key = part.casefold()
            if key not in seen:
                seen.add(key)
                queries.append(part)
    return queries


class Retriever:
    # Configure retrieval limits and verify that the local index is available.
    def __init__(self, index_dir: Path, documents_dir: Path) -> None:
        self.index_dir = index_dir.resolve()
        self.documents_dir = documents_dir.resolve()
        self.search_limit = settings.retrieval_limit
        self.search_candidates = settings.retrieval_candidates
        self.evidence_context_chars = settings.evidence_context_chars
        self.max_evidence = settings.max_evidence
        if not (self.index_dir / "index.sqlite3").is_file():
            raise FileNotFoundError("Local retrieval index is missing.")
        logger.info(
            "retriever_initialized index=%s search_limit=%s candidates=%s "
            "context_chars=%s max_evidence=%s",
            self.index_dir,
            self.search_limit,
            self.search_candidates,
            self.evidence_context_chars,
            self.max_evidence,
        )

    # Expand short indexed excerpts with nearby source lines when the file is available.
    def _context(self, result: dict[str, Any]) -> str:
        """Read a few neighboring lines from documents/ when the indexed excerpt is short."""
        relative = Path(str(result["source_relative_path"]))
        path = (self.documents_dir / relative).resolve()
        if not path.is_relative_to(self.documents_dir) or not path.is_file():
            return str(result["text"])
        if len(str(result["text"])) >= 600:
            return str(result["text"])
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, int(result["line_start"]) - 5)
            end = min(len(lines), int(result["line_end"]) + 4)
            return "\n".join(lines[start:end])[:1800]
        except (OSError, ValueError):
            return str(result["text"])

    # Return all chunks from files whose names explicitly mention the health topic.
    def _dedicated_document_chunks(self, topic_words: set[str]) -> list[dict[str, Any]]:
        """Return every chunk from documents whose filename explicitly names a consultation topic."""
        if not topic_words:
            return []
        connection = sqlite3.connect(self.index_dir / "index.sqlite3")
        connection.row_factory = sqlite3.Row
        try:
            sources = [
                str(row[0]) for row in connection.execute("SELECT relative_path FROM files")
                if any(word in _plain(Path(str(row[0])).stem) for word in topic_words)
            ]
            if not sources:
                return []
            placeholders = ",".join("?" for _ in sources)
            rows = connection.execute(
                f"SELECT * FROM chunks WHERE source_relative_path IN ({placeholders}) "
                "ORDER BY source_relative_path, line_start, chunk_id",
                sources,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    # Return and prioritize every chunk containing the complete health problem phrase.
    def _topic_coverage_chunks(self, topic_text: str) -> list[dict[str, Any]]:
        """Return every indexed chunk that contains the complete user problem."""
        if not topic_text.strip():
            return []
        connection = sqlite3.connect(self.index_dir / "index.sqlite3")
        connection.row_factory = sqlite3.Row
        try:
            selected: list[dict[str, Any]] = []
            for row in connection.execute("SELECT * FROM chunks"):
                item = dict(row)
                haystack = _plain(" ".join([
                    str(item.get("heading") or ""), str(item.get("text") or "")
                ]))
                if _contains_exact_phrase(haystack, topic_text):
                    selected.append(item)
            selected.sort(key=lambda item: (
                # Put documents whose filename names the problem first. This keeps
                # dedicated treatment plans at the front of the single AI context.
                0 if any(
                    word in _plain(Path(str(item.get("source_relative_path") or "")).stem)
                    for word in _meaningful_words(topic_text)
                ) else 1,
                -sum(
                    _plain(" ".join([
                        str(item.get("heading") or ""), str(item.get("text") or "")
                    ])).count(word)
                    for word in _meaningful_words(topic_text)
                ),
                str(item.get("source_relative_path") or "").casefold(),
                int(item.get("line_start") or 0),
                int(item.get("chunk_id") or 0),
            ))
            return selected
        finally:
            connection.close()

    # Run hybrid retrieval and assemble a deduplicated, prioritized evidence inventory.
    def collect(self, session: SessionData) -> dict[str, dict[str, str]]:
        profile = session.profile
        queries = consultation_queries(profile)
        if not queries:
            logger.info("retrieval_completed queries=0 evidence_entries=0 reason=no_queries")
            return {}
        topic_text = profile.health_problem
        topic_words = _meaningful_words(topic_text)
        if topic_words:
            queries.insert(0, topic_text.strip())
            queries.insert(1, " ".join(sorted(topic_words)))
        search_queries = queries + [f"{query} contraindicații interacțiuni atenționări" for query in queries]
        logger.info(
            "retrieval_started base_queries=%s search_queries=%s topic_words=%s",
            len(queries),
            len(search_queries),
            len(topic_words),
        )
        batches: list[list[dict[str, Any]]] = []
        total_candidates = 0
        total_accepted = 0
        for query_number, search_query in enumerate(search_queries, start=1):
            word_set = _meaningful_words(search_query)
            accepted: list[dict[str, Any]] = []
            candidates = list(rank(
                self.index_dir,
                search_query,
                limit=self.search_limit,
                candidates=self.search_candidates,
            ))
            total_candidates += len(candidates)
            for result in candidates:
                source_text = " ".join([
                    str(result["source_relative_path"]), str(result["heading"]), str(result["text"])
                ])
                matching = any(word in _plain(source_text) for word in word_set)
                safety = "ATENTIONARI-SI-CONTRAINDICATII" in str(result["source_relative_path"])
                if (result.get("lexical_rank") is not None and matching) or safety:
                    accepted.append(result)
            if accepted:
                batches.append(accepted)
            total_accepted += len(accepted)
            logger.info(
                "retrieval_query_completed number=%s candidates=%s accepted=%s",
                query_number,
                len(candidates),
                len(accepted),
            )

        evidence: dict[str, dict[str, str]] = {}
        topic_chunks = self._topic_coverage_chunks(topic_text)
        dedicated_chunks = self._dedicated_document_chunks(topic_words)
        logger.info(
            "retrieval_priority_chunks topic_coverage=%s dedicated_document=%s",
            len(topic_chunks),
            len(dedicated_chunks),
        )
        for result in topic_chunks:
            if len(evidence) >= self.max_evidence:
                break
            token = f"C{result['chunk_id']}"
            evidence[token] = {
                "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                "text": self._context(result)[: self.evidence_context_chars],
            }
        for result in dedicated_chunks:
            if len(evidence) >= self.max_evidence:
                break
            token = f"C{result['chunk_id']}"
            evidence[token] = {
                "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                "text": self._context(result)[: self.evidence_context_chars],
            }
        positions = [0] * len(batches)
        while len(evidence) < self.max_evidence:
            progressed = False
            for batch_number, results in enumerate(batches):
                while positions[batch_number] < len(results):
                    result = results[positions[batch_number]]
                    positions[batch_number] += 1
                    token = f"C{result['chunk_id']}"
                    if token in evidence:
                        continue
                    evidence[token] = {
                        "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                        "text": self._context(result)[: self.evidence_context_chars],
                    }
                    progressed = True
                    break
                if len(evidence) >= self.max_evidence:
                    break
            if not progressed:
                break

        logger.info(
            "retrieval_completed queries=%s search_candidates=%s search_accepted=%s "
            "batches=%s evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(search_queries),
            total_candidates,
            total_accepted,
            len(batches),
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence
