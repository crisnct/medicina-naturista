"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from medicina_naturista.ai.conditions import expansions_for
from medicina_naturista.ai.categories import CategoryTree, load_category_tree
from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.query_terms import GENERIC_QUERY_WORDS_PATH, meaningful_words as _meaningful_words
from medicina_naturista.ai.search import RRF_MAX_SCORE, rank
from medicina_naturista.config import settings
from medicina_naturista.core.models import SessionData

logger = logging.getLogger("naturist.retrieval")

# Fragments of the same file whose line ranges overlap or lie at most this many
# lines apart are merged into a single evidence fragment.
NEIGHBOR_LINE_GAP = 5

# Some source documents (e.g. a spreadsheet converted to one blank-line-free
# Markdown table) are parsed as a single oversized block, so every chunk split
# out of it is stamped with that block's whole (conservative) line range —
# possibly thousands of lines. Reading that range back from disk to expand or
# merge such a chunk would pull in most of the document as "one fragment" and
# starve every other source of the context budget. Past this many lines, skip
# the disk read and fall back to the chunk's own (already bounded) text.
MAX_SOURCE_EXPANSION_LINES = 200

# Source lines of one document, cached per (path, mtime): a single search reads
# the same large file once per evidence fragment otherwise (the Balch book is
# several MB), and the file is only re-read when it changes on disk.
@lru_cache(maxsize=128)
def _cached_lines(path: str, mtime_ns: int) -> tuple[str, ...]:
    return tuple(Path(path).read_text(encoding="utf-8", errors="replace").splitlines())


def _read_lines(path: Path) -> tuple[str, ...]:
    return _cached_lines(str(path), path.stat().st_mtime_ns)


# Build the search queries from the consultation profile.
def consultation_queries(profile: Any) -> list[str]:
    """Use the whole health problem as a single query. Conversation history
    (profile.transcript, profile.health_context) is intentionally excluded:
    it steered retrieval away from the actual topic being searched."""
    problem = " ".join((profile.health_problem or "").split())
    return [problem] if problem else []


class Retriever:
    # Configure retrieval limits and verify that the Postgres index is reachable.
    def __init__(self, documents_dir: Path) -> None:
        self.documents_dir = documents_dir.resolve()
        self.merge_max_percent_diff = settings.merge_max_percent_diff
        with get_pool().connection() as connection:
            self.document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        # None when no document has been synced yet — collect() then never
        # filters, which is the same as every category being selected.
        self.category_tree: CategoryTree | None = load_category_tree()
        self._known_category_ids: frozenset[str] = (
            self.category_tree.known_ids() if self.category_tree is not None else frozenset()
        )
        logger.info(
            "retriever_initialized merge_max_percent_diff=%s document_count=%s category_count=%s",
            self.merge_max_percent_diff,
            self.document_count,
            len(self._known_category_ids),
        )

    # The existing source file for a relative path, or None when it is missing or
    # resolves outside documents_dir. An existing file is resolved once and
    # remembered: Path.resolve() costs milliseconds on Windows and a search
    # touches the same few files for every one of its evidence fragments.
    def _source_path(self, relative: str) -> Path | None:
        # setdefault (not __init__) so Retriever test doubles built with
        # object.__new__ work without the attribute.
        known: dict[str, Path] = self.__dict__.setdefault("_source_paths", {})
        cached = known.get(relative)
        if cached is not None:
            return cached
        path = (self.documents_dir / relative).resolve()
        if not (path.is_relative_to(self.documents_dir) and path.is_file()):
            return None  # not remembered: the file may appear after the next sync
        known[relative] = path
        return path

    # Expand short indexed excerpts with nearby source lines when the file is available.
    def _context(self, result: dict[str, Any]) -> str:
        """Add its semantic heading and expand short excerpts with nearby source lines."""
        text = str(result["text"])
        heading = str(result.get("heading") or "").strip()
        path = self._source_path(str(result["source_relative_path"]))
        line_start, line_end = int(result["line_start"]), int(result["line_end"])
        if path is None:
            context = text
        elif len(text) >= 600 or line_end - line_start > MAX_SOURCE_EXPANSION_LINES:
            context = text
        else:
            try:
                lines = _read_lines(path)
                start = max(0, line_start - 5)
                end = min(len(lines), line_end + 4)
                context = "\n".join(lines[start:end])[:1800]
            except (OSError, ValueError):
                context = text
        return f"Secțiune: {heading}\n\n{context}" if heading else context

    # Text of a merged group: the source lines of its whole (united) line range,
    # or the members' own texts in file order when the source file is unavailable
    # or that united range is implausibly large (see MAX_SOURCE_EXPANSION_LINES).
    def _group_context(self, group: dict[str, Any], chunks: dict[int, dict[str, Any]], heading: str) -> str:
        path = self._source_path(str(group["path"]))
        context = ""
        within_bounds = group["end"] - group["start"] <= MAX_SOURCE_EXPANSION_LINES
        if within_bounds and path is not None:
            try:
                lines = _read_lines(path)
                context = "\n".join(lines[max(0, group["start"] - 1):group["end"]])
            except OSError:
                context = ""
        if not context:
            context = "\n\n".join(str(chunks[chunk_id]["text"]) for chunk_id in group["members"])
        heading = heading.strip()
        return f"Secțiune: {heading}\n\n{context}" if heading else context

    # Group fragments of the same file whose line ranges overlap or are at most
    # NEIGHBOR_LINE_GAP lines apart, and only while the spread of their relevance
    # percentages (highest minus lowest in the group, the candidate included) stays
    # strictly below `max_percent_diff`. Each group keeps its members' chunk ids
    # (in file order) and the united line range.
    @staticmethod
    def _merge_adjacent(
        chunks: dict[int, dict[str, Any]],
        relevance_percent: dict[int, float],
        max_percent_diff: float,
    ) -> list[dict[str, Any]]:
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
                percent = relevance_percent[chunk_id]
                if (
                    current is not None
                    and start <= current["end"] + NEIGHBOR_LINE_GAP
                    and max(current["max_percent"], percent) - min(current["min_percent"], percent) < max_percent_diff
                ):
                    current["members"].append(chunk_id)
                    current["end"] = max(current["end"], end)
                    current["min_percent"] = min(current["min_percent"], percent)
                    current["max_percent"] = max(current["max_percent"], percent)
                else:
                    current = {
                        "path": path, "start": start, "end": end, "members": [chunk_id],
                        "min_percent": percent, "max_percent": percent,
                    }
                    groups.append(current)
        return groups

    # Run hybrid retrieval and assemble a deduplicated, prioritized evidence inventory.
    def collect(self, session: SessionData) -> dict[str, dict[str, Any]]:
        profile = session.profile
        queries = consultation_queries(profile)
        if not queries:
            logger.info("retrieval_completed queries=0 evidence_entries=0 reason=no_queries")
            return {}
        search_queries: list[str] = []
        seen_queries: set[str] = set()
        for query in queries:
            key = " ".join(query.split()).casefold()
            if key not in seen_queries:
                seen_queries.add(key)
                search_queries.append(query)
        # session.selected_categories is patient-chosen source folders (see
        # medicina_naturista.ai.categories); getattr guards callers/test doubles
        # that predate this field. Unknown ids (a stale selection from before a
        # reindex renamed/removed a folder) are dropped rather than rejected.
        # The panel now defaults to every category checked (main.py's
        # DEFAULT_CATEGORY_SELECTION and category_filter_panel_html's initial
        # markup both start fully checked; an empty selection is instead
        # rejected before collect() is ever called — see on_find_fragments).
        # Selecting literally every known category is still treated as "no
        # filter" here (category_ids=None) so the common case — nobody having
        # touched the panel — takes rank()'s cheaper unfiltered path instead
        # of a same-result IN(...) query over every category id.
        requested_categories = getattr(session, "selected_categories", None) or ()
        category_ids = frozenset(requested_categories) & self._known_category_ids
        if not category_ids or category_ids == self._known_category_ids:
            category_ids = None
        logger.info(
            "retrieval_started search_queries=%s requested_categories=%s applied_categories=%s",
            len(search_queries),
            len(requested_categories),
            len(category_ids) if category_ids else 0,
        )
        total_candidates = 0
        # Per chunk: the sum of its hybrid_score over every query. rank() returns
        # every fragment of the index for each query, so no fragment is dropped here.
        score_sums: dict[int, float] = {}
        chunks: dict[int, dict[str, Any]] = {}
        found_by_lexical: dict[int, bool] = {}
        for query_number, search_query in enumerate(search_queries, start=1):
            expansions = expansions_for(search_query)
            candidates = rank(search_query, category_ids=category_ids, expansions=expansions)
            total_candidates += len(candidates)
            for result in candidates:
                chunk_id = int(result["chunk_id"])
                score_sums[chunk_id] = score_sums.get(chunk_id, 0.0) + result["hybrid_score"]
                chunks.setdefault(chunk_id, result)
                found_by_lexical[chunk_id] = found_by_lexical.get(chunk_id, False) or result["found_by_lexical"]
            logger.info(
                "retrieval_query_completed number=%s candidates=%s expansions=%s",
                query_number,
                len(candidates),
                len(expansions),
            )

        # Multi-query RRF: a chunk's score is the sum of its per-query hybrid_score
        # (which itself fuses the semantic and lexical ranks, see ai/search.py)
        # divided by the number of queries run, so the ceiling stays RRF_MAX_SCORE.
        # Its relevance_percent is that score as a percentage of the ceiling.
        #
        # No relevance_percent threshold is applied here — every candidate rank()
        # returned (across every query) becomes evidence, merged below. The only
        # place a fragment is ever dropped now is fit_evidence_to_context()'s
        # MAX_CONTEXT_CHARS budget cut (see medicina_naturista.ai.client), applied
        # once, downstream, by the caller — not here.
        query_count = len(search_queries)
        relevance_percent = {
            chunk_id: total / query_count / RRF_MAX_SCORE * 100.0
            for chunk_id, total in score_sums.items()
        }

        # Neighbouring fragments of the same file are then merged into one
        # evidence fragment. The merged fragment takes the id, heading, score and
        # relevance_percent of its best-scored member (the maximum, so a document
        # split into many pieces does not outrank a single strong one) and is
        # found_by_lexical if any member is.
        evidence: dict[str, dict[str, Any]] = {}
        merged: list[tuple[float, int, dict[str, Any]]] = []
        for group in self._merge_adjacent(chunks, relevance_percent, self.merge_max_percent_diff):
            best_id = max(group["members"], key=score_sums.__getitem__)
            merged.append((score_sums[best_id], best_id, group))
        merged.sort(key=lambda item: item[0], reverse=True)
        for best_sum, best_id, group in merged:
            best = chunks[best_id]
            if len(group["members"]) == 1:
                text = self._context(best)
            else:
                text = self._group_context(group, chunks, str(best.get("heading") or ""))
            evidence[f"C{best_id}"] = {
                "source": f"documents/{group['path']}:{group['start']}-{group['end']}",
                "text": text,
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best_sum / query_count,
                "relevance_percent": relevance_percent[best_id],
                "priority": best.get("priority"),
                "conditions": best.get("conditions", []),
                # Whether any query matched a member's exact phrase, for the UI.
                # A future selective signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": any(found_by_lexical[chunk_id] for chunk_id in group["members"]),
            }

        logger.info(
            "retrieval_completed queries=%s search_candidates=%s "
            "evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(search_queries),
            total_candidates,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence
