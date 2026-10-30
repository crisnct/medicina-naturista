"""Catalog-scoped British English noun forms from the bundled Hunspell dictionary."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from importlib.resources import files

from backend.ai.query_terms import plain

logger = logging.getLogger("naturist.herbs")
Rule = tuple[str, str, re.Pattern[str]]


def _read_data() -> tuple[list[Rule], list[str]]:
    dictionary = files("scripts").joinpath("dictionaires").joinpath("en")
    affixes = dictionary.joinpath("en_GB.aff").read_text(encoding="utf-8-sig")
    entries = dictionary.joinpath("en_GB.dic").read_text(encoding="utf-8-sig")
    rules: list[Rule] = []
    for line in affixes.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[:2] != ["SFX", "S"]:
            continue
        strip = "" if parts[2] == "0" else parts[2]
        addition = parts[3].split("/")[0]
        addition = "" if addition == "0" else addition
        rules.append((strip, addition, re.compile(parts[4] + "$")))
    return rules, entries.splitlines()[1:]


def _forms(stem: str, flags: str, rules: list[Rule]) -> set[str]:
    forms = {stem}
    if "S" in flags:
        for strip, addition, condition in rules:
            if (strip and not stem.endswith(strip)) or not condition.search(stem):
                continue
            form = stem[: len(stem) - len(strip)] + addition
            if form.isalpha():
                forms.add(form)
    return forms


# Avoid expanding every derivation/prefix merely to restore an unambiguous display accent.
def spelling_variants() -> dict[str, set[str]]:
    try:
        rules, entries = _read_data()
    except OSError:
        return {}
    variants: dict[str, set[str]] = {}
    for line in entries:
        stem, _, flags = line.partition("/")
        if stem.isalpha() and stem.islower():
            for form in _forms(stem, flags, rules):
                variants.setdefault(plain(form), set()).add(form)
    return variants


# The bundled en_GB S flag describes plurals; derivations and verb flags change meaning.
@lru_cache(maxsize=4)
def word_variants(words: frozenset[str]) -> dict[str, frozenset[str]]:
    variants = {word: {word} for word in words}
    if not words:
        return {}
    try:
        rules, entries = _read_data()
    except OSError:
        logger.warning(
            "herb_inflections_unavailable: bundled British English dictionary is missing"
        )
        return {word: frozenset(forms) for word, forms in variants.items()}

    possible = set(words)
    for word in words:
        for strip, addition, _ in rules:
            if addition and word.endswith(plain(addition)):
                possible.add(word[: -len(addition)] + plain(strip))
    headwords: dict[str, set[str]] = {}
    for line in entries:
        stem, _, flags = line.partition("/")
        if not stem.isalpha() or not stem.islower() or plain(stem) not in possible:
            continue
        key = plain(stem)
        forms = {plain(form) for form in _forms(stem, flags, rules)}
        if key in words:
            headwords.setdefault(key, set()).update(forms)
        for word in forms & words:
            variants[word].update(forms)
    # An explicit headword takes precedence over an inflection of another lemma.
    variants.update(headwords)
    return {word: frozenset(forms) for word, forms in variants.items()}
