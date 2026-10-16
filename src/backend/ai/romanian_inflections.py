"""Catalog-scoped Romanian inflections from the bundled Hunspell dictionary."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from importlib.resources import files

from backend.ai.query_terms import plain

logger = logging.getLogger("naturist.herbs")
# Noun and adjective flags in bundled ro_RO.aff. Verb conjugations and proper
# names are excluded so a homograph cannot introduce unrelated verb forms.
_NOMINAL_FLAGS = frozenset("tenrRsuafFACcMPzDSqQLl")


def _related_nominal_bases(word: str) -> set[str]:
    """Nominal gender endings and the last-vowel a/ă -> e plural alternation.

    These are candidates only: a base and every inferred form must also exist
    in the dictionary. This connects incomplete/unflagged nominal entries and
    tree/fruit forms without a list of plant-specific exceptions.
    """
    bases = {word}
    if len(word) >= 3:
        bases.add(word + "ă")
        if word.endswith("i"):
            bases.add(word + "e")
        match = re.search(r"ă([^aeiouăâî]+)$", word)
        if match:
            plural_base = word[: match.start()] + "e" + match[1]
            bases.add(plural_base + "e")
    return bases


def _article_forms(word: str) -> set[str]:
    forms = {word + suffix for suffix in ("ul", "ului", "le", "lor")}
    if word.endswith("ă"):
        forms.add(word[:-1] + "a")
    if word.endswith("ie"):
        forms.add(word[:-1] + "a")
    return forms


def _suffix_forms(stem: str, rules: list[tuple[str, str, re.Pattern[str]]]) -> set[str]:
    forms = {stem}
    for strip, addition, condition in rules:
        if (strip and not stem.endswith(strip)) or not condition.search(stem):
            continue
        form = stem[: len(stem) - len(strip)] + addition
        if form.isalpha():
            forms.add(form)
    return forms


@lru_cache(maxsize=4)
def word_variants(words: frozenset[str]) -> dict[str, frozenset[str]]:
    """Expand only dictionary paradigms containing a catalog word.

    Apply suffixes to dictionary entries, never to arbitrary user input.
    For entries without flags, accept only forms also listed in the dictionary.
    Prefix derivations are excluded: a related word need not name the same plant.
    Keep only single-word forms so clitics cannot consume extra query words.
    """
    variants = {word: {word} for word in words}
    stem_variants: dict[str, set[str]] = {}
    if not words:
        return {}
    dictionary = files("scripts").joinpath("dictionaires").joinpath("ro")
    try:
        affixes = dictionary.joinpath("ro_RO.aff").read_text(encoding="utf-8")
        entries = dictionary.joinpath("ro_RO.dic").read_text(encoding="utf-8")
    except OSError:
        logger.warning("herb_inflections_unavailable: bundled Romanian dictionary is missing")
        return {word: frozenset(forms) for word, forms in variants.items()}

    suffixes: dict[str, list[tuple[str, str, re.Pattern[str]]]] = {}
    for line in affixes.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "SFX" or parts[1] not in _NOMINAL_FLAGS:
            continue
        _, flag, strip, addition, condition = parts[:5]
        strip = "" if strip == "0" else strip
        addition = addition.split("/")[0]
        addition = "" if addition == "0" else addition
        suffixes.setdefault(flag, []).append((strip, addition, re.compile(condition + "$")))

    records = []
    for line in entries.splitlines()[1:]:
        stem, _, flags = line.partition("/")
        stem = stem.strip()
        if len(stem) >= 3 and stem.isalpha() and stem.islower():
            records.append((stem, plain(stem), flags))
    lexicon = {stem for stem, _, _ in records}
    related: dict[str, set[str]] = {}
    for stem, key, _ in records:
        if key in words:
            for base in _related_nominal_bases(stem) & lexicon:
                related.setdefault(base, set()).add(key)
    # Invert suffix spelling to preselect possible dictionary entries. Actual
    # flags/conditions are still checked below; unrelated paradigms are not built.
    possible_stems = set(words)
    endings = {(plain(strip), plain(add)) for rules in suffixes.values() for strip, add, _ in rules}
    for word in words:
        for strip, addition in endings:
            if word.endswith(addition):
                base = word[: len(word) - len(addition)] + strip
                possible_stems.add(base)
    for stem, key, flags in records:
        if key not in possible_stems and stem not in related:
            continue
        rules = [rule for flag in flags for rule in suffixes.get(flag, ())]
        forms = {plain(form) for form in _suffix_forms(stem, rules)}
        if stem in related:
            forms.update(plain(form) for form in _article_forms(stem) & lexicon)
        if key in words:
            stem_variants.setdefault(key, set()).update(forms)
        for word in forms & words:
            variants[word].update(forms)
        for word in related.get(stem, ()):
            stem_variants.setdefault(word, set()).update(forms)
    # Prefer a dictionary headword's own paradigm to homographs generated by
    # another lemma ("mei" must not inherit "meu/mea/mele" from an adjective).
    variants.update(stem_variants)
    return {word: frozenset(forms) for word, forms in variants.items()}
