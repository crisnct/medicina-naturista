"""Medical-condition matching over an ordered PostgreSQL catalog snapshot."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import get_close_matches

from backend.ai.query_terms import plain

# Typo tolerance (difflib ratio, 0-1): strict when the whole query is compared
# to a term, looser as a last resort when nothing else matched.
TYPO_CUTOFF = 0.9
FUZZY_CUTOFF = 0.84
# At most this many conditions are recognised in one comma-separated segment.
MAX_MATCHED_CONDITIONS = 2


@dataclass(frozen=True)
class Condition:
    name: str
    terms: tuple[str, ...]  # canonical name + synonyms, original spelling, no duplicates


# One comma-separated expression of a message: the conditions it names and the
# words of it that are NOT part of a condition's name ("copii" in "gripa la
# copii"). With no condition, `remainder` is the whole text. When the whole
# segment is (a near spelling of) one condition, `remainder` is empty.
# `whole_condition` tells that the expression IS the condition (an exact term
# or a near-identical spelling of one, rules 1 and 2 of _match()), not merely a
# text that contains a condition's name or resembles one: only then do the
# condition's synonyms stand for the expression in the lexical search.
@dataclass(frozen=True)
class QuerySegment:
    text: str
    conditions: tuple[Condition, ...]
    remainder: str
    whole_condition: bool = False


# A message split into its comma-separated segments, each with its conditions.
@dataclass(frozen=True)
class ResolvedQuery:
    segments: tuple[QuerySegment, ...] = ()

    # Every condition named by the message, without duplicates, in order of
    # appearance.
    @property
    def conditions(self) -> tuple[Condition, ...]:
        found = {
            condition.name: condition
            for segment in self.segments
            for condition in segment.conditions
        }
        return tuple(found.values())

    # Canonical names of those conditions — exactly what the indexer writes to
    # chunks.primary_medical_conditions / secondary_medical_conditions.
    @property
    def condition_names(self) -> tuple[str, ...]:
        return tuple(condition.name for condition in self.conditions)


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", plain(value), flags=re.UNICODE))


def make_condition(name: str, synonyms: Iterable[str] = ()) -> Condition:
    """Construct effective terms using the original normalization/dedup rules."""
    if not isinstance(name, str) or not _normalize(name):
        raise ValueError("Condition name must be a non-empty string")
    if isinstance(synonyms, (str, bytes)):
        raise ValueError("Synonyms must be an iterable of strings")
    terms: list[str] = []
    seen: set[str] = set()
    for part in (name, *synonyms):
        if not isinstance(part, str):
            raise ValueError("Synonyms must be strings")
        part = " ".join(part.split())
        key = _normalize(part)
        if key and key not in seen:
            seen.add(key)
            terms.append(part)
    return Condition(name=terms[0], terms=tuple(terms))


# Romanian inflection endings folded away by _fold_word(), longest first, each
# with what replaces it ("anemii" -> "anemi", like "anemie" -> "anemi").
_INFLECTION_SUFFIXES = (
    ("ului", ""),
    ("ilor", ""),
    ("elor", ""),
    ("ile", ""),
    ("ele", ""),
    ("ei", ""),
    ("ii", "i"),
    ("ul", ""),
    ("a", ""),
    ("e", ""),
    ("i", ""),
)
# A word is folded only if it stays at least this long afterwards.
_MIN_FOLDED_CHARS = 3


# Fold the common Romanian case/number endings so "gripa", "gripei" and "gripe"
# compare equal. Both dictionary terms and scanned text go through it.
def _fold_word(word: str) -> str:
    if len(word) < 4:
        return word
    for suffix, replacement in _INFLECTION_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_FOLDED_CHARS:
            return word[: len(word) - len(suffix)] + replacement
    return word


# Folded words of a text, in order (diacritics and case ignored).
def _folded_words(text: str) -> list[str]:
    return [_fold_word(word) for word in re.findall(r"[^\W_]+", plain(text), flags=re.UNICODE)]


class ConditionDictionary:
    def __init__(self, conditions: Iterable[Condition]) -> None:
        self.conditions = tuple(conditions)
        # normalized term -> indexes of the conditions that carry it
        self._by_term: dict[str, list[int]] = {}
        # Phrase index for find(): first folded word -> [(folded words, condition indexes)],
        # longest phrase first so the most specific term wins at a position.
        self._phrases: dict[str, list[tuple[tuple[str, ...], list[int]]]] = {}
        for index, condition in enumerate(self.conditions):
            for term in condition.terms:
                self._by_term.setdefault(_normalize(term), []).append(index)
        self._terms = list(self._by_term)
        for term, indexes in self._by_term.items():
            words = tuple(_fold_word(word) for word in term.split())
            self._phrases.setdefault(words[0], []).append((words, indexes))
        for candidates in self._phrases.values():
            candidates.sort(key=lambda item: len(item[0]), reverse=True)

    # Every condition named in `text`, in order of first appearance. A term must
    # appear as whole words (endings folded, see _fold_word), whatever its
    # length; where several terms start at the same word
    # only the longest counts ("adenom colonic" hides "adenom"), and matched
    # words are not scanned again.
    def find(self, text: str) -> list[Condition]:
        words = _folded_words(text)
        found: list[int] = []
        position = 0
        while position < len(words):
            matched = 0
            for phrase, indexes in self._phrases.get(words[position], ()):
                if tuple(words[position : position + len(phrase)]) == phrase:
                    found.extend(indexes)
                    matched = len(phrase)
                    break
            position += matched or 1
        return [self.conditions[index] for index in dict.fromkeys(found)]

    def _contained_indexes(self, normalized: str) -> list[int]:
        """Prefer longer overlapping terms; retain separate mentions in text order."""
        padded = f" {normalized} "
        matches: list[tuple[int, int, str]] = []
        for term in self._terms:
            start = padded.find(f" {term} ")
            while start >= 0:
                matches.append((start + 1, start + 1 + len(term), term))
                start = padded.find(f" {term} ", start + 1)
        selected: list[tuple[int, int, str]] = []
        for start, end, term in sorted(matches, key=lambda match: (match[0] - match[1], match[0])):
            if not any(
                start < other_end and other_start < end for other_start, other_end, _ in selected
            ):
                selected.append((start, end, term))
        return self._pick(
            [index for _, _, term in sorted(selected) for index in self._by_term[term]]
        )

    # The conditions the query names, best match first (at most
    # MAX_MATCHED_CONDITIONS), and whether the query IS the condition as a whole.
    # In order: 1. the whole query equals a term; 2. it is a near-identical
    # spelling of one (typo) — both are "whole" matches; 3. terms appearing as
    # whole words inside the query, keeping separate mentions and preferring
    # longer terms only where they overlap ("adenom de prostata" beats "adenom"
    # at that position); 4. otherwise the closest term by spelling, to
    # absorb typos.
    def _match(self, query: str) -> tuple[list[int], bool]:
        normalized = _normalize(query)
        if not normalized:
            return [], False
        if normalized in self._by_term:
            return self._pick(self._by_term[normalized]), True
        # A near-identical spelling of a whole term is a typo, and beats a
        # shorter term merely contained in the query ("artrita gutosa" is
        # "artrita gutoasa", not just "artrita").
        typo = get_close_matches(
            normalized, self._terms, n=MAX_MATCHED_CONDITIONS, cutoff=TYPO_CUTOFF
        )
        if typo:
            return self._pick([index for term in typo for index in self._by_term[term]]), True
        contained = self._contained_indexes(normalized)
        if contained:
            return contained, False
        close = get_close_matches(
            normalized, self._terms, n=MAX_MATCHED_CONDITIONS, cutoff=FUZZY_CUTOFF
        )
        return self._pick([index for term in close for index in self._by_term[term]]), False

    def match(self, query: str) -> list[Condition]:
        return [self.conditions[index] for index in self._match(query)[0]]

    # The first condition that has one of `terms` as an exact term (case and
    # diacritics ignored, no typo tolerance), trying the terms in order; None
    # when none of them is in the dictionary.
    def exact(self, terms: Iterable[str]) -> Condition | None:
        for term in terms:
            indexes = self._by_term.get(_normalize(term))
            if indexes:
                return self.conditions[indexes[0]]
        return None

    # Ranking filters must preserve ambiguous aliases and never discard qualifiers.
    def exact_matches(self, query: str) -> list[Condition]:
        normalized = _normalize(query)
        matches = [self.conditions[index] for index in self._by_term.get(normalized, ())]
        canonical = [condition for condition in matches if _normalize(condition.name) == normalized]
        return canonical or list(dict.fromkeys(matches))

    @staticmethod
    def _pick(indexes: list[int]) -> list[int]:
        return list(dict.fromkeys(indexes))[:MAX_MATCHED_CONDITIONS]

    # The words of `text` that are not part of the name of one of the conditions
    # `indexes` (plain form, no diacritics). When none of the names appears as
    # words (the segment is a typo or near spelling of the condition as a
    # whole) the segment is the condition, so nothing is left over.
    def _remainder(self, text: str, indexes: list[int]) -> str:
        words = re.findall(r"[^\W_]+", plain(text), flags=re.UNICODE)
        folded = [_fold_word(word) for word in words]
        targets = set(indexes)
        consumed: set[int] = set()
        position = 0
        while position < len(folded):
            length = 0
            for phrase, owners in self._phrases.get(folded[position], ()):
                if (
                    targets.intersection(owners)
                    and tuple(folded[position : position + len(phrase)]) == phrase
                ):
                    length = len(phrase)
                    break
            consumed.update(range(position, position + length))
            position += length or 1
        if not consumed:
            return ""
        return " ".join(word for index, word in enumerate(words) if index not in consumed)

    # Split a message at commas into segments and recognise the conditions of
    # each one on its own, so "gripa, tuse" names both conditions.
    def resolve(self, query: str) -> ResolvedQuery:
        segments: list[QuerySegment] = []
        for part in query.split(","):
            text = " ".join(part.split())
            if not _normalize(text):
                continue
            indexes, whole = self._match(text)
            if indexes:
                segments.append(
                    QuerySegment(
                        text=text,
                        conditions=tuple(self.conditions[index] for index in indexes),
                        remainder=self._remainder(text, indexes),
                        whole_condition=whole,
                    )
                )
            else:
                segments.append(QuerySegment(text=text, conditions=(), remainder=text))
        return ResolvedQuery(tuple(segments))


def load_dictionary() -> ConditionDictionary:
    from backend.ai.index_state import active_dictionary, dictionary_snapshot

    snapshot = active_dictionary()
    if snapshot is not None:
        return snapshot
    return dictionary_snapshot()[1]


# Conditions named in a text, using the configured dictionary.
def find_conditions(text: str, dictionary: ConditionDictionary | None = None) -> list[Condition]:
    return (dictionary or load_dictionary()).find(text)


# A message split into segments with the conditions they name, using the
# configured dictionary.
def resolve_query(query: str) -> ResolvedQuery:
    return load_dictionary().resolve(query)
