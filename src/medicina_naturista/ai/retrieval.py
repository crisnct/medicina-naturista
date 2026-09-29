"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
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
        with get_pool().connection() as connection:
            self.document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        # None when no document has been synced yet — collect() then never
        # filters, which is the same as every category being selected.
        self.category_tree: CategoryTree | None = load_category_tree()
        self._known_category_ids: frozenset[str] = (
            self.category_tree.known_ids() if self.category_tree is not None else frozenset()
        )
        logger.info(
            "retriever_initialized document_count=%s category_count=%s",
            self.document_count,
            len(self._known_category_ids),
        )

    # The fragment's text as indexed, prefixed with its heading path.
    @staticmethod
    def _context(result: dict[str, Any]) -> str:
        text = str(result["text"])
        heading = str(result.get("heading") or "").strip()
        return f"Secțiune: {heading}\n\n{text}" if heading else text

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
        # returned (across every query) becomes evidence, below. The only
        # place a fragment is ever dropped now is fit_evidence_to_context()'s
        # MAX_CONTEXT_CHARS budget cut (see medicina_naturista.ai.client), applied
        # once, downstream, by the caller — not here.
        query_count = len(search_queries)
        relevance_percent = {
            chunk_id: total / query_count / RRF_MAX_SCORE * 100.0
            for chunk_id, total in score_sums.items()
        }

        # Each fragment is one piece of evidence, exactly as indexed (fragments
        # are whole sections, see ai/fragmenter.py), best score first.
        evidence: dict[str, dict[str, Any]] = {}
        for chunk_id in sorted(score_sums, key=score_sums.__getitem__, reverse=True):
            best = chunks[chunk_id]
            best_id, best_sum = chunk_id, score_sums[chunk_id]
            evidence[f"C{best_id}"] = {
                "source": (
                    f"documents/{best['source_relative_path']}:{best['line_start']}-{best['line_end']}"
                ),
                "text": self._context(best),
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best_sum / query_count,
                "relevance_percent": relevance_percent[best_id],
                "priority": best.get("priority"),
                "conditions": best.get("conditions", []),
                # Whether any query matched a member's exact phrase, for the UI.
                # A future selective signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": found_by_lexical[chunk_id],
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
