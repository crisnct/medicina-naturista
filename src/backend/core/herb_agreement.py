"""Romanian product-name agreement, using local noun paradigms and explicit display rules."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from importlib.resources import files
from typing import Literal

from backend.core.language import current_language
from backend.core.operation_context import checkpoint

HerbAgreement = Literal["masculine", "feminine", "plural"]
_FEMININE = frozenset("AFfRrsuCcMPzn")
_MASCULINE = frozenset("Ll")
_PLURAL_HEADS = frozenset(
    "patlagele gutui seminte flori frunze radacini fructe boabe muguri tulpini "
    "uleiuri vitamine minerale suplimente aminoacizi alge tarate cereale legume "
    "cepe mere pere prune cirese visine caise piersici capsuni dude mure afine "
    "coacaze smochine masline stafide nuci alune migdale fisticuri".split()
)


def _plain(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.casefold())
        if not unicodedata.combining(char)
    )


# Reuse the already shipped dictionary data, without importing operator CLI code.
@lru_cache(maxsize=1)
def _noun_forms() -> tuple[dict[str, HerbAgreement], dict[str, HerbAgreement]]:
    dictionary = files("scripts").joinpath("dictionaires").joinpath("ro")
    suffixes: dict[str, list[tuple[str, str, re.Pattern[str], HerbAgreement]]] = {}
    for line in dictionary.joinpath("ro_RO.aff").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] != "SFX" or parts[1] not in _FEMININE | _MASCULINE:
            continue
        grammar = re.search(r"s\.\s*([mfn])\.\s*(sg|pl)\.", " ".join(parts[5:]))
        if grammar is None:
            continue
        gender, number = grammar.groups()
        form: HerbAgreement = (
            "plural" if number == "pl" else "masculine" if gender == "m" else "feminine"
        )
        strip, addition = parts[2:4]
        suffixes.setdefault(parts[1], []).append(
            (
                "" if strip == "0" else strip,
                "" if addition == "0" else addition.split("/")[0],
                re.compile(parts[4] + "$"),
                form,
            )
        )
    stems: dict[str, HerbAgreement] = {}
    forms: dict[str, HerbAgreement] = {}
    for position, line in enumerate(
        dictionary.joinpath("ro_RO.dic").read_text(encoding="utf-8").splitlines()[1:]
    ):
        if position % 1024 == 0:
            checkpoint()
        stem, _, flags = line.partition("/")
        if not stem.isalpha() or not stem.islower():
            continue
        nominal = set(flags) & (_FEMININE | _MASCULINE)
        if not nominal:
            continue
        stem_form: HerbAgreement = "masculine" if nominal & _MASCULINE else "feminine"
        stems[stem] = stem_form
        # Prefer the actual ASCII noun over a diacritic-folded homograph (soc / șoc).
        stems.setdefault(_plain(stem), stem_form)
        for flag in sorted(nominal):
            for strip, addition, condition, form in suffixes.get(flag, []):
                if (strip and not stem.endswith(strip)) or not condition.search(stem):
                    continue
                inflected = stem[: len(stem) - len(strip)] + addition
                if inflected.isalpha():
                    forms[inflected] = form
                    forms.setdefault(_plain(inflected), form)
    return stems, forms


@lru_cache(maxsize=4096)
def _romanian_agreement(name: str) -> HerbAgreement:
    normalized = re.sub(r"^(?:[dl]-)+", "", _plain(name).strip())
    words = re.findall(r"[a-z]+", normalized)
    if not words:
        return "feminine"
    head = words[0]
    # Gutui is ambiguous (tree or fruits); the requested product wording is plural.
    if head in _PLURAL_HEADS:
        return "plural"
    stems, inflections = _noun_forms()
    original_words = re.findall(r"[^\W\d_]+", re.sub(r"^(?:[dl]-)+", "", name.casefold()))
    original_head = unicodedata.normalize("NFC", original_words[0]) if original_words else head
    for candidate in (original_head, head):
        if candidate in stems:
            return stems[candidate]
        if candidate in inflections:
            return inflections[candidate]
    if head.endswith(("uri", "ii")):
        return "plural"
    return "feminine" if head.endswith(("a", "e")) else "masculine"


def herb_agreement(name: str) -> HerbAgreement:
    # English "useful" is invariant; cached Romanian gender must not leak into English.
    return "feminine" if current_language() == "en" else _romanian_agreement(name)
