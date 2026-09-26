"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from medicina_naturista.ai.search import rank
from medicina_naturista.config import settings
from medicina_naturista.core.models import SessionData

logger = logging.getLogger("naturist.retrieval")

GENERIC_QUERY_WORDS_PATH = (
    Path(__file__).resolve().parent / "resources" / "generic_query_words.txt"
)
GENERIC_QUERY_WORDS = frozenset(
    GENERIC_QUERY_WORDS_PATH.read_text(encoding="utf-8").split()
)

# Normalize text for case-insensitive and diacritic-insensitive comparisons.
def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


# Extract searchable words while excluding short and generic terms.
def _meaningful_words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"\w+", _plain(value))
        if len(word) >= 4 and word not in GENERIC_QUERY_WORDS
    }


# Build the search queries from the consultation profile.
def consultation_queries(profile: Any) -> list[str]:
    """Use the whole health problem as a single query. Conversation history
    (profile.transcript, profile.health_context) is intentionally excluded:
    it steered retrieval away from the actual topic being searched."""
    problem = " ".join((profile.health_problem or "").split())
    return [problem] if problem else []


class Retriever:
    # Configure retrieval limits and verify that the local index is available.
    def __init__(self, index_dir: Path, documents_dir: Path) -> None:
        self.index_dir = index_dir.resolve()
        self.documents_dir = documents_dir.resolve()
        self.search_candidates = settings.retrieval_candidates
        self.evidence_context_chars = settings.evidence_context_chars
        if not (self.index_dir / "index.sqlite3").is_file():
            raise FileNotFoundError("Local retrieval index is missing.")
        connection = sqlite3.connect(self.index_dir / "index.sqlite3")
        try:
            self.document_count = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            connection.close()
        logger.info(
            "retriever_initialized index=%s candidates=%s "
            "context_chars=%s document_count=%s",
            self.index_dir,
            self.search_candidates,
            self.evidence_context_chars,
            self.document_count,
        )

    # Expand short indexed excerpts with nearby source lines when the file is available.
    def _context(self, result: dict[str, Any]) -> str:
        """Add its semantic heading and expand short excerpts with nearby source lines."""
        text = str(result["text"])
        heading = str(result.get("heading") or "").strip()
        relative = Path(str(result["source_relative_path"]))
        path = (self.documents_dir / relative).resolve()
        if not path.is_relative_to(self.documents_dir) or not path.is_file():
            context = text
        elif len(text) >= 600:
            context = text
        else:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(0, int(result["line_start"]) - 5)
                end = min(len(lines), int(result["line_end"]) + 4)
                context = "\n".join(lines[start:end])[:1800]
            except (OSError, ValueError):
                context = text
        return f"Secțiune: {heading}\n\n{context}" if heading else context

    # Run hybrid retrieval and assemble a deduplicated, prioritized evidence inventory.
    def collect(self, session: SessionData) -> dict[str, dict[str, Any]]:
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
                candidates=self.search_candidates,
            ))
            total_candidates += len(candidates)
            for result in candidates:
                source_text = " ".join([
                    str(result["source_relative_path"]), str(result["heading"]), str(result["text"])
                ])
                # Word-overlap guards against embedding drift, so it only applies
                # to semantic-only hits. A lexical hit already contains the exact
                # query phrase, so it is accepted without this check.
                if result["found_by_lexical"] or any(
                    word in _plain(source_text) for word in word_set
                ):
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

        # Every accepted chunk (including exact-phrase matches on the topic, which
        # now surface here too via the phrase-based lexical query) carries its
        # hybrid_score from rank(): a single, consistent relevance measure for the
        # whole evidence set, with no separate scoring path or label.
        evidence: dict[str, dict[str, Any]] = {}
        positions = [0] * len(batches)
        while True:
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
                        # Raw hybrid_score from rank() — the single relevance
                        # value for this fragment. Every consumer (the UI
                        # panel, the AI-context budget trimming) reads this
                        # field directly and formats/orders from it; nothing
                        # keeps a separate pre-formatted copy that could drift.
                        "score": result["hybrid_score"],
                        # Independent per-signal flags straight from rank(),
                        # for the UI to show alongside the score. A future
                        # signal adds its own "found_by_<signal>" flag here
                        # without touching these two.
                        "found_by_lexical": result["found_by_lexical"],
                        "found_by_semantic": result["found_by_semantic"],
                    }
                    progressed = True
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
