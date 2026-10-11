"""Local-only retrieval over the existing hybrid index."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai.categories import CategoryTree, category_selection, load_category_tree
from backend.ai.condition_ai import resolved_for
from backend.ai.index_state import index_reader
from backend.ai.query_terms import GENERIC_QUERY_WORDS_PATH
from backend.ai.query_terms import meaningful_words as _meaningful_words
from backend.ai.search import (
    ALL_SIGNALS,
    EVIDENCE_HEADING_PREFIX,
    EVIDENCE_HEADING_SEPARATOR,
    effective_signals,
    max_score,
    rank,
)
from backend.core.contracts import Evidence, EvidenceItem
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
        self._category_snapshot: tuple[CategoryTree | None, str] | None = None
        # Categories/count are read in the same generation as each search.

    @property
    def category_tree(self):
        return self.categories_snapshot()[0]

    @property
    def document_count(self):
        tree, _generation = self.categories_snapshot()
        return tree.nodes[tree.root_id].total_documents if tree else 0

    def categories_snapshot(self) -> tuple[CategoryTree | None, str]:
        with index_reader() as (_connection, metadata):
            with self._snapshot_lock:
                cached = self._category_snapshot
                if cached is None or cached[1] != metadata.index_generation:
                    cached = (load_category_tree(), metadata.index_generation)
                    self._category_snapshot = cached
                return cached

    # The fragment's text as indexed, prefixed with its heading path.
    @staticmethod
    def _context(result: dict[str, Any]) -> str:
        text = str(result["text"])
        heading = str(result.get("heading") or "").strip()
        if not heading:
            return text
        return f"{EVIDENCE_HEADING_PREFIX}{heading}{EVIDENCE_HEADING_SEPARATOR}{text}"

    # Run hybrid retrieval and assemble a deduplicated, prioritized evidence inventory.
    # max_chars is the evidence budget for the active AI provider; None means
    # no budget (rank() returns every fragment).
    def collect(
        self, session: SessionData | SessionSnapshot, max_chars: int | None = None
    ) -> Evidence:
        with index_reader() as (_connection, metadata):
            tree, _generation = self.categories_snapshot()
            return self._collect(session, max_chars, tree, metadata.index_generation)

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
        # sum of the chosen signals, never above max_score(signals));
        # relevance_percent is that score as a percentage of the ceiling OF THAT
        # COMBINATION, computed here once and never again. rank() applies the
        # only limit there is, the provider's context budget over the evidence
        # text, by cutting whole fragments from the end of the score-ordered
        # list, so every fragment it returns becomes evidence, below.
        # The message resolved as the chat saw it: the dictionary's conditions plus
        # the ones the AI identified. Without any condition the conditions signal
        # cannot contribute, so the percentages are relative to the rest.
        resolved = resolved_for(profile)
        candidates = rank(
            query,
            category_ids=category_ids,
            max_chars=max_chars,
            signals=signals,
            resolved=resolved,
        )
        ceiling = max_score(effective_signals(signals, resolved))

        # Each fragment is one piece of evidence, exactly as indexed (fragments
        # are whole sections, see ai/fragmenter.py), best score first.
        evidence = EvidenceSnapshot(generation, removed)
        for best in candidates:
            evidence[f"C{best['chunk_id']}"] = {
                "source": (
                    f"documents/{best['source_relative_path']}:{best['line_start']}-{best['line_end']}"
                ),
                "text": self._context(best),
                # Every consumer (the UI panel, the AI-context budget trimming)
                # reads these fields directly and formats/orders from them.
                "score": best["score"],
                "relevance_percent": best["score"] / ceiling * 100.0,
                # The components of the score, informational only: L (None when
                # the query did not match the fragment lexically), V, and the raw
                # cosine similarity behind V. Each is None when its signal is off.
                "lexical_score": best.get("lexical_score"),
                "semantic_score": best.get("semantic_score"),
                "semantic_similarity": best.get("semantic_similarity"),
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
