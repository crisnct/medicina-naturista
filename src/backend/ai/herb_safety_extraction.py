"""Inventory product safety independently of disease scope, preserving original source offsets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.ai.herb_association_rules import NameMatcher, content_hash
from backend.ai.herb_index_catalog import normalize_herb_name
from backend.core.operation_context import checkpoint

EXTRACTION_VERSION = 2
CITATION_ANCHOR_CHARS = 64
SUMMARY_MAX_CHARS = 240
SUMMARY_MAX_WORDS = 40
_PARAGRAPH_BREAK = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")
_STATEMENT_END = re.compile(r";(?=\s)|[.!?](?=\s*(?:[A-ZĂÂÎȘŞȚŢ]|$))")
_ENUMERATION = re.compile(r"\b(?:oricare|urmatoar\w*|lista|printre)\b")
_COLLECTIVE_SUBJECT = re.compile(
    r"\b(?:laxativele|purgativele|plantele|produsele|medicamentele|suplimentele|preparatele)\b"
)
_ANAPHORA = re.compile(r"^(?:aceasta|acesta|acest|ea|el|planta|produsul)\b")
_NEGATED_RISK = re.compile(
    r"\b(?:nu(?: poate| se)? (?:produce|provoaca|cauzeaza|determina)|"
    r"(?:nu (?:este|e|sunt|are|au)|fara) (?:\w+ ){0,2}"
    r"(?:toxic\w*|efect\w* advers\w*|react\w* advers\w*|interactiuni))\b"
)
_EXPLICIT_RESTRICTION = re.compile(
    r"\b(?:interzis\w*|contraindicat\w*|evit\w*|nu (?:se )?"
    r"(?:administr\w*|consum\w*|asoci\w*|folos\w*|recomand\w*|utiliz\w*))\b"
)
WARNING_KINDS = (
    "high_dose",
    "adverse_effect",
    "drug_interaction",
    "product_interaction",
    "administration",
    "population",
)
WARNING_TERMS = re.compile(
    r"\b(?:contraindicat\w*|interact\w*|supradoz\w*|toxic\w*|precaut\w*|"
    r"atention\w*|efecte secundare|reactii adverse|doze mari|in exces|"
    r"nu (?:se )?(?:administreaza|asociaza|consuma|recomanda)|"
    r"a nu se|evitati|de evitat|prudenta|doza maxima|maxim(?:um)?(?: de)? \d+|nu depasi\w*)\b"
)


@dataclass(frozen=True)
class SafetyTarget:
    chunk_id: int
    herb_id: int
    name: str
    document: str
    source_hash: str
    text_hash: str
    heading: str
    text: str
    mentions: tuple[tuple[int, int], ...]
    foreign_mentions: tuple[tuple[int, int], ...] = ()
    heading_owned: bool = False
    certain: bool = True
    catalog_hash: str = ""

    @property
    def identity(self) -> str:
        return content_hash([self.chunk_id, self.herb_id])

    def cache_key(self, semantic: dict[str, Any], digest: str) -> str:
        return content_hash(
            [
                self.herb_id,
                self.name,
                self.heading,
                self.text,
                self.mentions,
                self.foreign_mentions,
                self.heading_owned,
                self.certain,
                self.catalog_hash,
                semantic,
                digest,
            ]
        )


# Stable source paragraphs are references, never model-authored quotations or truncated excerpts.
def source_passages(target: SafetyTarget) -> dict[str, tuple[int, int]]:
    passages: dict[str, tuple[int, int]] = {}
    start = 0
    for separator in _PARAGRAPH_BREAK.finditer(target.text):
        if target.text[start : separator.start()].strip():
            passages[f"c{target.chunk_id}p{len(passages)}"] = (start, separator.start())
        start = separator.end()
    if target.text[start:].strip():
        passages[f"c{target.chunk_id}p{len(passages)}"] = (start, len(target.text))
    return passages


# Anchors identify complete source paragraphs without duplicating full fragments in the prompt.
def citation_index(target: SafetyTarget) -> dict[str, dict[str, int | str]]:
    return _span_index(target, source_passages(target))


# Short anchors are metadata; complete evidence is always sliced from the unchanged source.
def _span_index(
    target: SafetyTarget, spans: dict[str, tuple[int, int]]
) -> dict[str, dict[str, int | str]]:
    index: dict[str, dict[str, int | str]] = {}
    for identifier, (start, end) in spans.items():
        passage = target.text[start:end]
        entry: dict[str, int | str] = {
            "start": start,
            "end": end,
            "begins_with": passage[:CITATION_ANCHOR_CHARS],
        }
        if len(passage) > CITATION_ANCHOR_CHARS:
            entry["ends_with"] = passage[
                max(CITATION_ANCHOR_CHARS, len(passage) - CITATION_ANCHOR_CHARS) :
            ]
        index[identifier] = entry
    return index


# Statements separate a product's warning from unrelated advice elsewhere in an OCR paragraph.
def warning_statements(target: SafetyTarget) -> dict[str, tuple[int, int]]:
    statements: dict[str, tuple[int, int]] = {}
    for passage_id, (start, end) in source_passages(target).items():
        cursor = start
        ordinal = 0
        endings = [match.end() for match in _STATEMENT_END.finditer(target.text, start, end)]
        for stop in (*endings, end):
            left, right = cursor, stop
            while left < right and target.text[left].isspace():
                left += 1
            while right > left and target.text[right - 1].isspace():
                right -= 1
            if left < right:
                statements[f"{passage_id}s{ordinal}"] = (left, right)
                ordinal += 1
            cursor = stop
    return statements


# Category membership and a name in an earlier enumeration cannot establish product-specific risk.
def supports_warning_statement(target: SafetyTarget, start: int, end: int) -> bool:
    if not target.certain or not 0 <= start < end <= len(target.text):
        return False
    statement = normalize_herb_name(target.text[start:end])
    if _NEGATED_RISK.search(statement) and not _EXPLICIT_RESTRICTION.search(statement):
        return False
    own = any(start <= a < b <= end for a, b in target.mentions)
    foreign = any(start <= a < b <= end for a, b in target.foreign_mentions)
    if own:
        listing = foreign or _ENUMERATION.search(statement) is not None
        warning_cue = WARNING_TERMS.search(statement) is not None or re.search(
            r"\b(?:provoc\w*|cauz\w*|produc\w*|irit\w*|interzis\w*|evit\w*|asoci\w*|efect\w*|potent\w*)\b",
            statement,
        )
        return not listing or bool(warning_cue)
    if _COLLECTIVE_SUBJECT.search(statement):
        return False
    if foreign:
        first_foreign = min(a for a, b in target.foreign_mentions if start <= a < b <= end)
        prefix = normalize_herb_name(target.text[start:first_foreign])
        if not re.search(r"\b(?:cu|efectul|efectele|actiunea)(?: al| ale| a)?$", prefix):
            return False
    if target.heading_owned and supports_quote(target, start, end):
        return True
    preceding = start - 1
    while preceding >= 0 and target.text[preceding].isspace():
        preceding -= 1
    if not _ANAPHORA.match(statement) and (preceding < 0 or target.text[preceding] != ";"):
        return False
    previous = next(
        (span for span in reversed(warning_statements(target).values()) if span[1] <= start),
        None,
    )
    if previous is not None and not _PARAGRAPH_BREAK.search(target.text, previous[1], start):
        a, b = previous
        return (
            any(a <= left < right <= b for left, right in target.mentions)
            and not any(a <= left < right <= b for left, right in target.foreign_mentions)
            and supports_warning_statement(target, a, b)
        )
    return False


def eligible_warning_statements(target: SafetyTarget) -> dict[str, tuple[int, int]]:
    if not target.certain:
        return {}
    return {
        identifier: span
        for identifier, span in warning_statements(target).items()
        if supports_warning_statement(target, *span)
    }


# One sentence may express several distinct warnings; its words also bound transport capacity.
def warning_source_word_count(target: SafetyTarget) -> int:
    return sum(
        len(re.findall(r"\w+", target.text[start:end]))
        for start, end in eligible_warning_statements(target).values()
    )


# Source-only recovery removes list formatting, never clinical words or qualifiers.
def statement_summary(text: str) -> str:
    return " ".join(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text).split())


# An inherited product heading is valid only within its own Markdown section.
def supports_quote(target: SafetyTarget, start: int, end: int) -> bool:
    if not target.certain or not 0 <= start < end <= len(target.text):
        return False
    if any(start <= a < b <= end for a, b in target.mentions):
        return True
    paragraph = 0
    for boundary in _PARAGRAPH_BREAK.finditer(target.text, 0, start):
        paragraph = boundary.end()
    references = [(a, True) for a, b in target.mentions if paragraph <= a < b <= start]
    references.extend((a, False) for a, b in target.foreign_mentions if paragraph <= a < b <= start)
    if references:
        return max(references)[1]
    if target.heading_owned:
        owned = True
        product_depth: int | None = None
        for heading in re.finditer(r"(?m)^(#{1,6})\s+.+$", target.text[:start]):
            depth = len(heading.group(1))
            own = any(heading.start() <= a < b <= heading.end() for a, b in target.mentions)
            foreign = any(
                heading.start() <= a < b <= heading.end() for a, b in target.foreign_mentions
            )
            if own and not foreign:
                owned, product_depth = True, depth
            elif foreign or (product_depth is not None and depth <= product_depth):
                owned = False
            elif product_depth is None:
                product_depth = max(0, depth - 1)
        return owned
    return False


def product_matcher(names: tuple[tuple[str, tuple[int, ...]], ...]) -> NameMatcher:
    forms: dict[str, set[int]] = {}
    for name, identifiers in names:
        words = name.split()
        if not words:
            continue
        final = words[-1]
        inflections = (
            (final[:-1] + "ei",)
            if final.endswith("a")
            else (final + "a", final[:-1] + "ii")
            if final.endswith("e")
            else (final + "ul", final + "ului")
        )
        for variant in (name, *(" ".join((*words[:-1], form)) for form in inflections)):
            forms.setdefault(variant, set()).update(identifiers)
    return NameMatcher(tuple((name, tuple(sorted(ids))) for name, ids in forms.items()))


def inventory_targets(
    rows: list[Any], matcher: NameMatcher, names: dict[int, str], catalog_hash: str
) -> tuple[SafetyTarget, ...]:
    targets: list[SafetyTarget] = []
    for chunk_id, document, source_hash, text_hash, heading, text in rows:
        checkpoint()
        text_matches = list(matcher.spans(text))
        heading_matches = list(matcher.spans(heading))
        identifiers = {
            identifier for _, ids in (*text_matches, *heading_matches) for identifier in ids
        }
        owners: set[int] = set()
        for component in reversed(heading.split(" > ")):
            owners = {identifier for _, ids in matcher.spans(component) for identifier in ids}
            if owners:
                break
        for identifier in sorted(identifiers):
            mentions = tuple(span for span, ids in text_matches if ids == (identifier,))
            owned = owners == {identifier}
            targets.append(
                SafetyTarget(
                    chunk_id,
                    identifier,
                    names[identifier],
                    document,
                    source_hash,
                    text_hash,
                    heading,
                    text,
                    mentions,
                    tuple(span for span, ids in text_matches if identifier not in ids),
                    owned,
                    bool(mentions or owned),
                    catalog_hash,
                )
            )
    return tuple(targets)


# Local recovery contributes quotations, never evidence of complete semantic coverage.
def local_warning_items(target: SafetyTarget) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    statements = eligible_warning_statements(target)
    if not statements:
        return items
    for start, end in source_passages(target).values():
        summary = statement_summary(target.text[start:end])
        if len(summary) > SUMMARY_MAX_CHARS or len(summary.split()) > SUMMARY_MAX_WORDS:
            continue
        if any(
            start <= left < right <= end
            and WARNING_TERMS.search(normalize_herb_name(target.text[left:right]))
            for left, right in statements.values()
        ):
            items.append(
                {"kind": "administration", "quote": target.text[start:end], "partners": []}
            )
    return items
