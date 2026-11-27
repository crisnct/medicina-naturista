"""Local-only retrieval over the existing hybrid index."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai import fragment_highlights
from backend.ai.categories import CategoryTree, category_selection, load_category_tree
from backend.ai.condition_ai import resolved_for
from backend.ai.index_state import index_reader
from backend.ai.query_terms import GENERIC_QUERY_WORDS_PATH
from backend.ai.query_terms import meaningful_words as _meaningful_words
from backend.ai.search import (
    ALL_SIGNALS,
    EVIDENCE_HEADING_SEPARATOR,
    effective_signals,
    evidence_heading_prefix,
    fragment_ceiling,
    rank,
)
from backend.core.contracts import (
    Evidence,
    EvidenceItem,
)
from backend.core.language import current_language, language_scope
from backend.core.models import SessionData, SessionSnapshot

__all__ = ["Retriever", "consultation_query", "GENERIC_QUERY_WORDS_PATH", "_meaningful_words"]

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
        self._snapshot_lock = threading.Lock()
        self._category_snapshots: dict[str, tuple[CategoryTree | None, str]] = {}
        # Categories/count are read in the same generation as each search.

    @property
    def category_tree(self):
        return self.categories_snapshot()[0]

    @property
    def document_count(self):
        tree, _generation = self.categories_snapshot()
        return tree.nodes[tree.root_id].total_documents if tree else 0

    # The document count per language of the snapshots already loaded, without
    # touching the index; a language is missing until its snapshot has been loaded.
    def cached_document_counts(self) -> dict[str, int]:
        with self._snapshot_lock:
            snapshots = dict(self._category_snapshots)
        return {
            language: tree.nodes[tree.root_id].total_documents
            for language, (tree, _generation) in snapshots.items()
            if tree is not None
        }

    def categories_snapshot(self) -> tuple[CategoryTree | None, str]:
        with index_reader() as (_connection, metadata):
            with self._snapshot_lock:
                cached = self._category_snapshots.get(current_language())
                if cached is None or cached[1] != metadata.index_generation:
                    cached = (load_category_tree(), metadata.index_generation)
                    self._category_snapshots[current_language()] = cached
                return cached

    # The fragment's text as indexed, prefixed with its heading path.
    @staticmethod
    def _context(result: dict[str, Any]) -> str:
        text = str(result["text"])
        heading = str(result.get("heading") or "").strip()
        if not heading:
            return text
        return f"{evidence_heading_prefix()}{heading}{EVIDENCE_HEADING_SEPARATOR}{text}"

    # Run hybrid retrieval and assemble a deduplicated, prioritized evidence inventory.
    # max_chars bounds the fragment text (the same characters the report batches count).
    def collect(
        self,
        session: SessionData | SessionSnapshot,
        max_chars: int | None = None,
    ) -> Evidence:
        with (
            language_scope(getattr(session, "language", current_language())),
            index_reader() as (connection, metadata),
        ):
            tree, _generation = self.categories_snapshot()
            evidence = self._collect(session, max_chars, tree, metadata.index_generation)
            fragment_highlights.apply(evidence, connection)
            return evidence

    def _collect(self, session, max_chars, tree, generation):
        profile = session.profile
        query = consultation_query(profile)
        if not query:
            logger.info("retrieval_completed evidence_entries=0 reason=no_query")
            return EvidenceSnapshot(generation, [])
        # None is explicitly unrestricted; an empty or stale selection never widens.
        requested = getattr(session, "selected_categories", None)
        requested_categories = frozenset(requested) if requested is not None else None
        category_ids, removed = category_selection(requested, tree)
        # The signals the patient switched on for this search (getattr, like
        # selected_categories above); every one is on by default.
        signals = getattr(session, "search_signals", ALL_SIGNALS)
        logger.info(
            "retrieval_started requested_categories=%s applied_categories=%s signals=%s",
            len(requested_categories) if requested_categories is not None else 0,
            len(category_ids) if category_ids else 0,
            signals.code,
        )
        # The fragment's score is rank()'s score (ai/search.py: the weighted
        # sum of the chosen signals);
        # relevance_percent is that score as a percentage of the ceiling OF THAT
        # FRAGMENT (fragment_ceiling(): the formula with its own P1 / P2 and ranks 1),
        # computed here once and never again. rank() cuts a whole-fragment
        # prefix by characters.
        # The message resolved as the chat saw it: the dictionary's conditions plus
        # the ones the AI identified. Without any condition the conditions signal
        # cannot contribute, so the percentages are relative to the rest.
        resolved = resolved_for(profile)
        candidates: list[dict[str, Any]] = rank(
            query,
            category_ids=category_ids,
            max_chars=max_chars,
            signals=signals,
            resolved=resolved,
            language=getattr(session, "language", current_language()),
        )
        effective = effective_signals(signals, resolved)

        # Each fragment is one piece of evidence, exactly as indexed (fragments
        # are whole sections, see ai/fragmenter.py), best score first.
        evidence = EvidenceSnapshot(generation, removed)
        # What the highlights of the fragments are computed from (see fragment_highlights.py).
        evidence.resolved = resolved
        evidence.signals = effective
        # The BM25 of a fragment as a percentage of the best BM25 of this search (the panel
        # filters by it); BM25 has no fixed scale, so only the ratio to the best means anything.
        best_bm25 = max(
            (c["lexical_bm25"] for c in candidates if c.get("lexical_bm25")), default=None
        )
        for best in candidates:
            evidence_id = f"C{best['chunk_id']}"
            ceiling = fragment_ceiling(
                effective, bool(best["condition_in_title"]), bool(best["condition_in_text"])
            )
            item: EvidenceItem = {
                "source": (
                    f"documents/{best['source_relative_path']}:{best['line_start']}-{best['line_end']}"
                ),
                "text": self._context(best),
                "language": getattr(session, "language", current_language()),
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best["score"],
                "relevance_percent": best["score"] / ceiling * 100.0,
                # The components of the score, informational only: the ranks L (by
                # BM25) and V (by cosine similarity) the score formula uses, which the
                # panel shows, and the raw cosine similarity behind V (the panel
                # filters by it). Each is None when its signal is off (or the
                # fragment has no rank).
                "lexical_rank": best.get("lexical_rank"),
                "semantic_rank": best.get("semantic_rank"),
                "semantic_similarity": best.get("semantic_similarity"),
                "lexical_percent": (
                    best["lexical_bm25"] / best_bm25 * 100.0
                    if best_bm25 and best.get("lexical_bm25") is not None
                    else None
                ),
                # P1 / P2: the searched condition is in the fragment's title / text
                # (None when the conditions signal is off).
                "condition_in_title": best["condition_in_title"],
                "condition_in_text": best["condition_in_text"],
                "business_category": best.get("business_category"),
                "primary_medical_conditions": best.get("primary_medical_conditions", []),
                "secondary_medical_conditions": best.get("secondary_medical_conditions", []),
                # Whether the query matched the fragment lexically, for the UI.
                # A future selective signal adds its own "found_by_<signal>" flag here.
                "found_by_lexical": best["found_by_lexical"],
            }
            evidence[evidence_id] = item

        logger.info(
            "retrieval_completed search_candidates=%s "
            "evidence_entries=%s evidence_chars=%s unique_sources=%s",
            len(candidates),
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
            len({item["source"].split(":", 1)[0] for item in evidence.values()}),
        )
        return evidence


class EvidenceSnapshot(dict[str, EvidenceItem]):
    def __init__(self, generation: str, removed: list[str]):
        super().__init__()
        self.index_generation = generation
        self.removed_category_ids = removed
