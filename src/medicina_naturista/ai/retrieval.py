"""Local-only retrieval over the existing hybrid index."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from medicina_naturista.ai.conditions import condition_names_for, expansions_for
from medicina_naturista.ai.categories import CategoryTree, load_category_tree
from medicina_naturista.ai.db import get_pool
from medicina_naturista.ai.query_terms import GENERIC_QUERY_WORDS_PATH, meaningful_words as _meaningful_words
from medicina_naturista.ai.search import RRF_MAX_SCORE, rank
from medicina_naturista.config import settings
from medicina_naturista.core.models import SessionData

logger = logging.getLogger("naturist.retrieval")

# The search query of a consultation: the whole health problem, spaces normalized.
def consultation_query(profile: Any) -> str:
    """Conversation history (profile.transcript, profile.health_context) is
    intentionally excluded: it steered retrieval away from the actual topic
    being searched. An empty string means there is nothing to search."""
    return " ".join((profile.health_problem or "").split())


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
        query = consultation_query(profile)
        if not query:
            logger.info("retrieval_completed evidence_entries=0 reason=no_query")
            return {}
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
        expansions = expansions_for(query)
        logger.info(
            "retrieval_started requested_categories=%s applied_categories=%s expansions=%s",
            len(requested_categories),
            len(category_ids) if category_ids else 0,
            len(expansions),
        )
        # The fragment's score is its hybrid_score (see ai/search.py: RRF of the
        # semantic, lexical and heading signals times the priority weight), which
        # never exceeds RRF_MAX_SCORE. relevance_percent is that score as a
        # percentage of the ceiling. There is one query, so nothing is combined.
        #
        # No relevance_percent threshold is applied here — every candidate rank()
        # returned becomes evidence, below. The only place a fragment is ever
        # dropped now is fit_evidence_to_context()'s MAX_CONTEXT_CHARS budget cut
        # (see medicina_naturista.ai.client), applied once, downstream, by the
        # caller — not here.
        candidates = rank(
            query,
            category_ids=category_ids,
            expansions=expansions,
            condition_names=condition_names_for(query),
        )

        # Each fragment is one piece of evidence, exactly as indexed (fragments
        # are whole sections, see ai/fragmenter.py), best score first.
        evidence: dict[str, dict[str, Any]] = {}
        for best in sorted(candidates, key=lambda result: result["hybrid_score"], reverse=True):
            evidence[f"C{best['chunk_id']}"] = {
                "source": (
                    f"documents/{best['source_relative_path']}:{best['line_start']}-{best['line_end']}"
                ),
                "text": self._context(best),
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best["hybrid_score"],
                "relevance_percent": best["hybrid_score"] / RRF_MAX_SCORE * 100.0,
                # Raw scores of the query (lexical is None when it did not match
                # the fragment lexically); informational only.
                "semantic_similarity": best.get("semantic_similarity"),
                "lexical_score": best.get("lexical_score"),
                "priority": best.get("priority"),
                "business_category": best.get("business_category"),
                "primary_medical_conditions": best.get("primary_medical_conditions", []),
                "secondary_medical_conditions": best.get("secondary_medical_conditions", []),
                # Whether the query matched the fragment lexically, for the UI.
                # A future selective signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": best["found_by_lexical"],
            }

        logger.info(
            "retrieval_completed search_candidates=%s "
            "evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(candidates),
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence
