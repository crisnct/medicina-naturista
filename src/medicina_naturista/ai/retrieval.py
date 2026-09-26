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
        search_queries: list[str] = []
        seen_queries: set[str] = set()
        for query in queries + [f"{query} contraindicații interacțiuni atenționări" for query in queries]:
            key = " ".join(query.split()).casefold()
            if key not in seen_queries:
                seen_queries.add(key)
                search_queries.append(query)
        logger.info(
            "retrieval_started base_queries=%s search_queries=%s topic_words=%s",
            len(queries),
            len(search_queries),
            len(topic_words),
        )
        total_candidates = 0
        total_accepted = 0
        # Per chunk: the sum of its hybrid_score over every query that accepted it.
        score_sums: dict[int, float] = {}
        chunks: dict[int, dict[str, Any]] = {}
        found_by_lexical: dict[int, bool] = {}
        found_by_semantic: dict[int, bool] = {}
        for query_number, search_query in enumerate(search_queries, start=1):
            word_set = _meaningful_words(search_query)
            accepted = 0
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
                if not (result["found_by_lexical"] or any(
                    word in _plain(source_text) for word in word_set
                )):
                    continue
                chunk_id = int(result["chunk_id"])
                score_sums[chunk_id] = score_sums.get(chunk_id, 0.0) + result["hybrid_score"]
                chunks.setdefault(chunk_id, result)
                found_by_lexical[chunk_id] = found_by_lexical.get(chunk_id, False) or result["found_by_lexical"]
                found_by_semantic[chunk_id] = found_by_semantic.get(chunk_id, False) or result["found_by_semantic"]
                accepted += 1
            total_accepted += accepted
            logger.info(
                "retrieval_query_completed number=%s candidates=%s accepted=%s",
                query_number,
                len(candidates),
                accepted,
            )

        # Multi-query RRF: a chunk's score is the sum of its per-query hybrid_score
        # (which itself fuses the semantic and lexical ranks, see ai/search.py)
        # divided by the number of queries run. A query that did not accept the
        # chunk contributes 0, so the ceiling stays RRF_MAX_SCORE (top-ranked by
        # both signals in every query) and a chunk found by more queries scores
        # higher. This is the single relevance value for the whole evidence set.
        evidence: dict[str, dict[str, Any]] = {}
        for chunk_id in sorted(score_sums, key=score_sums.__getitem__, reverse=True):
            result = chunks[chunk_id]
            evidence[f"C{chunk_id}"] = {
                "source": f"documents/{result['source_relative_path']}:{result['line_start']}-{result['line_end']}",
                "text": self._context(result)[: self.evidence_context_chars],
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads this field directly and formats/orders from it.
                "score": score_sums[chunk_id] / len(search_queries),
                # Independent per-signal flags, OR-ed across queries, for the UI.
                # A future signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": found_by_lexical[chunk_id],
                "found_by_semantic": found_by_semantic[chunk_id],
            }

        logger.info(
            "retrieval_completed queries=%s search_candidates=%s search_accepted=%s "
            "evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(search_queries),
            total_candidates,
            total_accepted,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence
