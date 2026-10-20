"""Content invariants shared by source conversion and PostgreSQL readers."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence

from backend.ai.conditions import _normalize
from backend.ai.herbs import (
    BOTANICAL_CATEGORY,
    FIELDS,
    Herb,
    SourceHerb,
    parse_herbs,
)
from backend.core.herb_categories import HERB_CATEGORIES, PRODUCT_CATEGORIES

SLUG = re.compile(r"[a-z]+(-[a-z]+)+")
LATIN = re.compile(r"[A-Z][a-z]+ (x )?[a-z]+(-[a-z]+)?( (subsp|var)\. [a-z]+(-[a-z]+)?)?")
LOWER_LATIN = re.compile(LATIN.pattern.replace("[A-Z]", "[a-z]"))
ALIASES = ("ro_regional", "latin_synonyms", "en_alt")


def catalog_problems(items: Sequence[SourceHerb | Herb], *, source: bool) -> list[str]:
    problems: list[str] = []
    if not items:
        return ["herb catalogue is empty"]
    owners: dict[str, str | int] = {}
    products: dict[str, str | int] = {}
    for number, herb in enumerate(items, 1):
        category = herb.category if isinstance(herb, Herb) else BOTANICAL_CATEGORY
        product = not source and category in PRODUCT_CATEGORIES
        if not source and category not in HERB_CATEGORIES:
            problems.append(f"line {number}: unknown category")
        where = f"line {number} ({herb.latin})"
        strings = [
            herb.ro,
            herb.latin,
            herb.en,
            herb.family,
            *herb.ro_regional,
            *herb.latin_synonyms,
            *herb.en_alt,
        ]
        if source:
            if not isinstance(herb.id, str) or not SLUG.fullmatch(herb.id):
                problems.append(f"{where}: id is not a slug")
            if not herb.ro[:1].isupper():
                problems.append(f"{where}: ro does not start with a capital")
        else:
            if type(herb.id) is not int or herb.id <= 0:
                problems.append(f"{where}: id must be a positive integer")
            lowercase = [herb.family, *herb.ro_regional, *herb.latin_synonyms, *herb.en_alt]
            if not product:
                lowercase.extend((herb.ro, herb.latin, herb.en))
            if any(value != value.lower() for value in lowercase):
                problems.append(f"{where}: names and family must be lowercase")
        if not all(value.isascii() for value in strings):
            problems.append(f"{where}: non-ASCII text")
        names = [
            herb.ro,
            herb.latin,
            herb.en,
            *herb.ro_regional,
            *herb.latin_synonyms,
            *herb.en_alt,
        ]
        if any("," in value for value in (names if product else strings)):
            problems.append(f"{where}: a name holds a comma")
        if any(value != " ".join(value.split()) for value in strings):
            problems.append(f"{where}: stray spaces")
        if (
            not herb.ro
            or (not product and not herb.latin)
            or (not product and not herb.family)
            or any(not value for key in ALIASES for value in getattr(herb, key))
        ):
            problems.append(f"{where}: empty required name")
        if product:
            if herb.family:
                problems.append(f"{where}: products must not have a botanical family")
            if herb.latin or herb.latin_synonyms:
                problems.append(f"{where}: products must not have Latin species names")
            if not herb.en:
                problems.append(f"{where}: product must have an English name")
            key = _normalize(herb.ro)
            if key in products:
                problems.append(
                    f"{where}: product name belongs to both {products[key]} and {herb.id}"
                )
            products.setdefault(key, herb.id)
        for latin in () if product else (herb.latin, *herb.latin_synonyms):
            if not (LATIN if source else LOWER_LATIN).fullmatch(latin):
                problems.append(f"{where}: {latin!r} is not a Latin species name without author")
            key = _normalize(latin)
            if key in owners:
                problems.append(f"{latin!r} belongs to both {owners[key]!r} and {herb.id!r}")
            owners.setdefault(key, herb.id)
        if not product and not herb.family.endswith("aceae"):
            problems.append(f"{where}: family does not end in -aceae")
        for main, aliases in (("ro", "ro_regional"), ("en", "en_alt")):
            if getattr(herb, main) and _normalize(getattr(herb, main)) in {
                _normalize(name) for name in getattr(herb, aliases)
            }:
                problems.append(f"{where}: {main} repeated in {aliases}")
        if not herb.en and herb.en_alt:
            problems.append(f"{where}: en_alt without en")
        for key in ALIASES:
            keys = [_normalize(name) for name in getattr(herb, key)]
            if len(keys) != len(set(keys)):
                problems.append(f"{where}: duplicates in {key}")
    order = [(_normalize(herb.ro), _normalize(herb.latin)) for herb in items]
    if order != sorted(order):
        problems.append("lines are not sorted by ro, then latin")
    problems.extend(
        f"id {key!r} repeated" for key, count in Counter(h.id for h in items).items() if count > 1
    )
    return problems


def content_problems(text: str) -> list[str]:
    items = parse_herbs(text)
    problems = catalog_problems(items, source=True)
    for number, raw in enumerate((line for line in text.splitlines() if line.strip()), 1):
        if list(json.loads(raw)) != list(FIELDS):
            problems.append(f"line {number}: keys out of order")
    return problems


def convert_source(items: Sequence[SourceHerb]) -> tuple[Herb, ...]:
    problems = catalog_problems(items, source=True)
    if problems:
        raise ValueError("\n".join(problems))
    converted = tuple(
        Herb(
            id=number,
            category=BOTANICAL_CATEGORY,
            ro=item.ro.lower(),
            ro_regional=tuple(value.lower() for value in item.ro_regional),
            latin=item.latin.lower(),
            latin_synonyms=tuple(value.lower() for value in item.latin_synonyms),
            en=item.en.lower(),
            en_alt=tuple(value.lower() for value in item.en_alt),
            family=item.family.lower(),
        )
        for number, item in enumerate(items, 1)
    )
    problems = catalog_problems(converted, source=False)
    if problems:
        raise ValueError("\n".join(problems))
    return converted
