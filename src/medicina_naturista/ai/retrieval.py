"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from medicina_naturista.ai.search import RRF_MAX_SCORE, rank
from medicina_naturista.config import settings
from medicina_naturista.core.models import SessionData

logger = logging.getLogger("naturist.retrieval")

GENERIC_QUERY_WORDS_PATH = (
    Path(__file__).resolve().parent / "resources" / "generic_query_words.txt"
)
GENERIC_QUERY_WORDS = frozenset(
    GENERIC_QUERY_WORDS_PATH.read_text(encoding="utf-8").split()
)

# Fragments of the same file whose line ranges overlap or lie at most this many
# lines apart are merged into a single evidence fragment.
NEIGHBOR_LINE_GAP = 5

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
        self.min_relevance_percent = settings.min_relevance_percent
        if not (self.index_dir / "index.sqlite3").is_file():
            raise FileNotFoundError("Local retrieval index is missing.")
        connection = sqlite3.connect(self.index_dir / "index.sqlite3")
        try:
            self.document_count = connection.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            connection.close()
        logger.info(
            "retriever_initialized index=%s min_relevance_percent=%s document_count=%s",
            self.index_dir,
            self.min_relevance_percent,
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

    # Text of a merged group: the source lines of its whole (united) line range,
    # or the members' own texts in file order when the source file is unavailable.
    def _group_context(self, group: dict[str, Any], chunks: dict[int, dict[str, Any]], heading: str) -> str:
        path = (self.documents_dir / str(group["path"])).resolve()
        context = ""
        if path.is_relative_to(self.documents_dir) and path.is_file():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                context = "\n".join(lines[max(0, group["start"] - 1):group["end"]])
            except OSError:
                context = ""
        if not context:
            context = "\n\n".join(str(chunks[chunk_id]["text"]) for chunk_id in group["members"])
        heading = heading.strip()
        return f"Secțiune: {heading}\n\n{context}" if heading else context

    # Group fragments of the same file whose line ranges overlap or are at most
    # NEIGHBOR_LINE_GAP lines apart. Each group keeps its members' chunk ids
    # (in file order) and the united line range.
    @staticmethod
    def _merge_adjacent(chunks: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        by_file: dict[str, list[int]] = defaultdict(list)
        for chunk_id, result in chunks.items():
            by_file[str(result["source_relative_path"])].append(chunk_id)
        groups: list[dict[str, Any]] = []
        for path, chunk_ids in by_file.items():
            chunk_ids.sort(key=lambda item: (chunks[item]["line_start"], chunks[item]["line_end"]))
            current: dict[str, Any] | None = None
            for chunk_id in chunk_ids:
                result = chunks[chunk_id]
                start, end = int(result["line_start"]), int(result["line_end"])
                if current is not None and start <= current["end"] + NEIGHBOR_LINE_GAP:
                    current["members"].append(chunk_id)
                    current["end"] = max(current["end"], end)
                else:
                    current = {"path": path, "start": start, "end": end, "members": [chunk_id]}
                    groups.append(current)
        return groups

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
        for query in queries:
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
        # Per chunk: the sum of its hybrid_score over every query. rank() returns
        # every fragment of the index for each query, so no fragment is dropped here.
        score_sums: dict[int, float] = {}
        chunks: dict[int, dict[str, Any]] = {}
        found_by_lexical: dict[int, bool] = {}
        for query_number, search_query in enumerate(search_queries, start=1):
            candidates = rank(self.index_dir, search_query)
            total_candidates += len(candidates)
            for result in candidates:
                chunk_id = int(result["chunk_id"])
                score_sums[chunk_id] = score_sums.get(chunk_id, 0.0) + result["hybrid_score"]
                chunks.setdefault(chunk_id, result)
                found_by_lexical[chunk_id] = found_by_lexical.get(chunk_id, False) or result["found_by_lexical"]
            logger.info(
                "retrieval_query_completed number=%s candidates=%s",
                query_number,
                len(candidates),
            )

        # Multi-query RRF: a chunk's score is the sum of its per-query hybrid_score
        # (which itself fuses the semantic and lexical ranks, see ai/search.py)
        # divided by the number of queries run, so the ceiling stays RRF_MAX_SCORE.
        # Its relevance_percent is that score as a percentage of the ceiling. Only
        # fragments at or above MIN_RELEVANCE_PERCENT are kept: this is the single
        # selection rule, shared by the UI panel and the request sent to the AI.
        query_count = len(search_queries)
        relevance_percent = {
            chunk_id: total / query_count / RRF_MAX_SCORE * 100.0
            for chunk_id, total in score_sums.items()
        }
        kept = {
            chunk_id: result for chunk_id, result in chunks.items()
            if relevance_percent[chunk_id] >= self.min_relevance_percent
        }

        # Neighbouring kept fragments of the same file are then merged into one
        # evidence fragment. The merged fragment takes the id, heading, score and
        # relevance_percent of its best-scored member (the maximum, so a document
        # split into many pieces does not outrank a single strong one) and is
        # found_by_lexical if any member is.
        evidence: dict[str, dict[str, Any]] = {}
        merged: list[tuple[float, int, dict[str, Any]]] = []
        for group in self._merge_adjacent(kept):
            best_id = max(group["members"], key=score_sums.__getitem__)
            merged.append((score_sums[best_id], best_id, group))
        merged.sort(key=lambda item: item[0], reverse=True)
        for best_sum, best_id, group in merged:
            best = kept[best_id]
            if len(group["members"]) == 1:
                text = self._context(best)
            else:
                text = self._group_context(group, kept, str(best.get("heading") or ""))
            evidence[f"C{best_id}"] = {
                "source": f"documents/{group['path']}:{group['start']}-{group['end']}",
                "text": text,
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best_sum / query_count,
                "relevance_percent": relevance_percent[best_id],
                # Whether any query matched a member's exact phrase, for the UI.
                # A future selective signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": any(found_by_lexical[chunk_id] for chunk_id in group["members"]),
            }

        logger.info(
            "retrieval_completed queries=%s search_candidates=%s above_threshold=%s "
            "min_relevance_percent=%s evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(search_queries),
            total_candidates,
            len(kept),
            self.min_relevance_percent,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence
