"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from search_medical_embeddings import rank
from web_app.sessions import SessionData

GENERIC_QUERY_WORDS = {
    "acest", "aceasta", "aveti", "care", "ceva", "despre", "doresc", "pentru", "problema",
    "recomandari", "raspuns", "simptome", "tratament", "naturist", "vreau", "utilizator",
    "naturista", "naturiste", "sanatate", "doriti", "intrebare", "informatii", "medicale",
    "spuneti",
}
MAX_EVIDENCE = 500
EVIDENCE_CONTEXT_CHARS = 900


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


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


def _meaningful_words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"\w+", _plain(value))
        if len(word) >= 4 and word not in GENERIC_QUERY_WORDS
    }


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
    def __init__(self, index_dir: Path, documents_dir: Path) -> None:
        self.index_dir = index_dir.resolve()
        self.documents_dir = documents_dir.resolve()
        if not (self.index_dir / "index.sqlite3").is_file():
            raise FileNotFoundError("Local retrieval index is missing.")

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

    def _topic_coverage_chunks(self, topic_words: set[str]) -> list[dict[str, Any]]:
        """Return every indexed chunk that directly mentions the topic."""
        if not topic_words:
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
                if any(word in haystack for word in topic_words):
                    selected.append(item)
            selected.sort(key=lambda item: (
                # Put documents whose filename names the problem first. This keeps
                # dedicated treatment plans at the front of the single AI context.
                0 if any(
                    word in _plain(Path(str(item.get("source_relative_path") or "")).stem)
                    for word in topic_words
                ) else 1,
                -sum(
                    _plain(" ".join([
                        str(item.get("heading") or ""), str(item.get("text") or "")
                    ])).count(word)
                    for word in topic_words
                ),
                str(item.get("source_relative_path") or "").casefold(),
                int(item.get("line_start") or 0),
                int(item.get("chunk_id") or 0),
            ))
            return selected
        finally:
            connection.close()

    def collect(self, session: SessionData) -> dict[str, dict[str, str]]:
        profile = session.profile
        queries = consultation_queries(profile)
        if not queries:
            return {}
        topic_text = profile.health_problem
        topic_words = _meaningful_words(topic_text)
        if topic_words:
            queries.insert(0, " ".join(sorted(topic_words)))
        search_queries = queries + [f"{query} contraindicații interacțiuni atenționări" for query in queries]
        batches: list[list[dict[str, Any]]] = []
        for search_query in search_queries:
            word_set = _meaningful_words(search_query)
            accepted: list[dict[str, Any]] = []
            for result in rank(self.index_dir, search_query, limit=40, candidates=240):
                source_text = " ".join([
                    str(result["source_relative_path"]), str(result["heading"]), str(result["text"])
                ])
                matching = any(word in _plain(source_text) for word in word_set)
                safety = "ATENTIONARI-SI-CONTRAINDICATII" in str(result["source_relative_path"])
                if (result.get("lexical_rank") is not None and matching) or safety:
                    accepted.append(result)
            if accepted:
                batches.append(accepted)

        evidence: dict[str, dict[str, str]] = {}
        for result in self._topic_coverage_chunks(topic_words):
            if len(evidence) >= MAX_EVIDENCE:
                break
            token = f"C{result['chunk_id']}"
            evidence[token] = {
                "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                "text": self._context(result)[:EVIDENCE_CONTEXT_CHARS],
            }
        for result in self._dedicated_document_chunks(topic_words):
            if len(evidence) >= MAX_EVIDENCE:
                break
            token = f"C{result['chunk_id']}"
            evidence[token] = {
                "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                "text": self._context(result)[:EVIDENCE_CONTEXT_CHARS],
            }
        positions = [0] * len(batches)
        while len(evidence) < MAX_EVIDENCE:
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
                        "text": self._context(result)[:EVIDENCE_CONTEXT_CHARS],
                    }
                    progressed = True
                    break
                if len(evidence) >= MAX_EVIDENCE:
                    break
            if not progressed:
                break

        return evidence
