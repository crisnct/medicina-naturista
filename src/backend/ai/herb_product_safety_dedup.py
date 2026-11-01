"""Merge bilingual stage answers into one list per product, once, without duplicates."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from backend.ai.herb_product_safety import SEVERITY, BilingualMessage, BilingualResult


@dataclass(frozen=True)
class Candidate:
    rank: int  # source priority: earlier stages win between sources
    position: int
    message: BilingualMessage


@dataclass(frozen=True)
class RemovedPair:
    kept: BilingualMessage
    removed: BilingualMessage
    reason: Literal["exact", "model"]

    def payload(self) -> dict[str, Any]:
        def entry(message: BilingualMessage) -> dict[str, str]:
            return {
                "message_type": message.message_type,
                "problem_en": message.problem_en,
                "problem_ro": message.problem_ro,
            }

        return {"reason": self.reason, "kept": entry(self.kept), "removed": entry(self.removed)}


@dataclass(frozen=True)
class MergeOutcome:
    status: Literal["complete", "uncertain"]
    messages: tuple[BilingualMessage, ...]
    removed: tuple[RemovedPair, ...]

    def removed_by_type(self) -> dict[str, int]:
        return dict(Counter(pair.removed.message_type for pair in self.removed))


# The deterministic half of the merge: what is left is what the local model must still group.
@dataclass(frozen=True)
class ExactMerge:
    candidates: tuple[Candidate, ...]
    removed: tuple[RemovedPair, ...]
    complete: bool


# Lower case, no diacritics, punctuation as single spaces.
def normalize(text: str) -> str:
    stripped = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^0-9a-z]+", " ", stripped.casefold()).split())


# Within one source the more severe type survives; between sources the higher-priority one does,
# without changing its type.
def _replaces(new: Candidate, old: Candidate) -> bool:
    return (
        new.rank == old.rank
        and SEVERITY[new.message.message_type] < SEVERITY[old.message.message_type]
    )


# An exact pair, or either text alone, counts as the same message so that the Romanian and the
# English lists stay injective after projection.
def _exact_match(kept: Sequence[Candidate], new: Candidate) -> int | None:
    ro, en = normalize(new.message.problem_ro), normalize(new.message.problem_en)
    for index, old in enumerate(kept):
        if normalize(old.message.problem_ro) == ro or normalize(old.message.problem_en) == en:
            return index
    return None


# Answers arrive in source priority order, best first; the status is complete only if every stage said complete.
def exact_merge(answers: Sequence[BilingualResult]) -> ExactMerge:
    kept: list[Candidate] = []
    removed: list[RemovedPair] = []
    for rank, answer in enumerate(answers):
        for position, message in enumerate(answer.messages):
            candidate = Candidate(rank, position, message)
            index = _exact_match(kept, candidate)
            if index is None:
                kept.append(candidate)
                continue
            old = kept[index]
            if _replaces(candidate, old):
                kept[index] = candidate
                removed.append(RemovedPair(candidate.message, old.message, "exact"))
            else:
                removed.append(RemovedPair(old.message, candidate.message, "exact"))
    return ExactMerge(
        tuple(kept), tuple(removed), all(answer.status == "complete" for answer in answers)
    )


# The model's groups pick one survivor each: the best source, then the most severe type, then the
# earliest. Other messages of a group are dropped with both of their texts.
def finish_merge(merged: ExactMerge, groups: Sequence[Sequence[int]]) -> MergeOutcome:
    dropped: set[int] = set()
    removed = list(merged.removed)
    for group in groups:
        winner = min(
            group,
            key=lambda index: (
                merged.candidates[index].rank,
                SEVERITY[merged.candidates[index].message.message_type],
                merged.candidates[index].position,
            ),
        )
        for index in group:
            if index != winner:
                dropped.add(index)
                removed.append(
                    RemovedPair(
                        merged.candidates[winner].message,
                        merged.candidates[index].message,
                        "model",
                    )
                )
    survivors = sorted(
        (item for index, item in enumerate(merged.candidates) if index not in dropped),
        key=lambda item: (item.rank, item.position),
    )
    return MergeOutcome(
        "complete" if merged.complete else "uncertain",
        tuple(item.message for item in survivors),
        tuple(removed),
    )
