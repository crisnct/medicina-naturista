"""Medical-condition dictionary (data/medical_conditions.txt): one condition per
line, comma-separated — the canonical name first, then its Romanian and
English synonyms. Used to recognise which condition a query names and to
expand the query with that condition's other names, so "gout" also finds the
sections titled "Gută" / "artrită gutoasă"."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

from medicina_naturista.ai.query_terms import plain
from medicina_naturista.config import settings

logger = logging.getLogger("naturist.conditions")

# Typo tolerance (difflib ratio, 0-1): strict when the whole query is compared
# to a term, looser as a last resort when nothing else matched.
TYPO_CUTOFF = 0.9
FUZZY_CUTOFF = 0.84
# At most this many conditions are used to expand one query.
MAX_MATCHED_CONDITIONS = 2
# Cap on expansion phrases per query, to keep the lexical query small.
MAX_EXPANSION_TERMS = 12


@dataclass(frozen=True)
class Condition:
    name: str
    terms: tuple[str, ...]  # canonical name + synonyms, original spelling, no duplicates


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", plain(value), flags=re.UNICODE))


# Parse the dictionary text. Blank lines and lines starting with '#' are skipped.
def parse_conditions(text: str) -> list[Condition]:
    conditions: list[Condition] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms: list[str] = []
        seen: set[str] = set()
        for part in line.split(","):
            part = " ".join(part.split())
            key = _normalize(part)
            if key and key not in seen:
                seen.add(key)
                terms.append(part)
        if terms:
            conditions.append(Condition(name=terms[0], terms=tuple(terms)))
    return conditions


# Romanian inflection endings folded away by _fold_word(), longest first, each
# with what replaces it ("anemii" -> "anemi", like "anemie" -> "anemi").
_INFLECTION_SUFFIXES = (
    ("ului", ""), ("ilor", ""), ("elor", ""), ("ile", ""), ("ele", ""),
    ("ei", ""), ("ii", "i"), ("ul", ""), ("a", ""), ("e", ""), ("i", ""),
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
    def __init__(self, conditions: list[Condition]) -> None:
        self.conditions = conditions
        # normalized term -> indexes of the conditions that carry it
        self._by_term: dict[str, list[int]] = {}
        # Phrase index for find(): first folded word -> [(folded words, condition indexes)],
        # longest phrase first so the most specific term wins at a position.
        self._phrases: dict[str, list[tuple[tuple[str, ...], list[int]]]] = {}
        for index, condition in enumerate(conditions):
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
                if tuple(words[position:position + len(phrase)]) == phrase:
                    found.extend(indexes)
                    matched = len(phrase)
                    break
            position += matched or 1
        return [self.conditions[index] for index in dict.fromkeys(found)]

    # Conditions the query names, best match first (at most MAX_MATCHED_CONDITIONS):
    # 1. the whole query equals a term; 2. it is a near-identical spelling of one
    # (typo); 3. terms appearing as whole words inside
    # the query, keeping only the longest ones ("adenom de prostata" beats
    # "adenom"); 4. otherwise the closest term by spelling, to absorb typos.
    def match(self, query: str) -> list[Condition]:
        normalized = _normalize(query)
        if not normalized:
            return []
        if normalized in self._by_term:
            return self._pick(self._by_term[normalized])
        # A near-identical spelling of a whole term is a typo, and beats a
        # shorter term merely contained in the query ("artrita gutosa" is
        # "artrita gutoasa", not just "artrita").
        typo = get_close_matches(normalized, self._terms, n=MAX_MATCHED_CONDITIONS, cutoff=TYPO_CUTOFF)
        if typo:
            return self._pick([index for term in typo for index in self._by_term[term]])
        padded = f" {normalized} "
        contained = [term for term in self._terms if f" {term} " in padded]
        if contained:
            longest = max(len(term) for term in contained)
            indexes = [index for term in contained if len(term) == longest for index in self._by_term[term]]
            return self._pick(indexes)
        close = get_close_matches(normalized, self._terms, n=MAX_MATCHED_CONDITIONS, cutoff=FUZZY_CUTOFF)
        return self._pick([index for term in close for index in self._by_term[term]])

    def _pick(self, indexes: list[int]) -> list[Condition]:
        unique = list(dict.fromkeys(indexes))[:MAX_MATCHED_CONDITIONS]
        return [self.conditions[index] for index in unique]

    # Phrases to add to the query for the matched conditions: every name of the
    # condition except the ones the query already is.
    def expansions(self, query: str) -> list[str]:
        normalized = _normalize(query)
        phrases: list[str] = []
        for condition in self.match(query):
            for term in condition.terms:
                if _normalize(term) != normalized and term not in phrases:
                    phrases.append(term)
        return phrases[:MAX_EXPANSION_TERMS]


@lru_cache(maxsize=4)
def _load(path: str, mtime_ns: int) -> ConditionDictionary:
    conditions = parse_conditions(Path(path).read_text(encoding="utf-8"))
    logger.info("conditions_loaded path=%s conditions=%s", path, len(conditions))
    return ConditionDictionary(conditions)


# The dictionary from settings.conditions_file, reloaded when the file changes.
# A missing file yields an empty dictionary (no expansion), never an error.
def load_dictionary(path: Path | None = None) -> ConditionDictionary:
    path = path or settings.conditions_file
    try:
        return _load(str(path), path.stat().st_mtime_ns)
    except OSError:
        logger.warning("conditions_file_unavailable path=%s", path)
        return ConditionDictionary([])


# Conditions named in a text, using the configured dictionary.
def find_conditions(text: str, dictionary: ConditionDictionary | None = None) -> list[Condition]:
    return (dictionary or load_dictionary()).find(text)


# Expansion phrases for a query, using the configured dictionary.
def expansions_for(query: str) -> list[str]:
    return load_dictionary().expansions(query)
