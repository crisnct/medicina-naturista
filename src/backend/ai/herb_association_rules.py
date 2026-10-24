"""Conservative source-polarity rules over unchanged indexed text and primary conditions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from backend.ai.herb_index_catalog import normalize_herb_name

POSITIVE_RANKING_VERSION = 1
RULES_VERSION = 4
SCHEMA_VERSION = 5
Label = Literal["positive", "caution", "mixed", "unclear"]
LABELS = ("positive", "caution", "mixed", "unclear")
Span = tuple[int, int]
NEGATIVE = re.compile(
    r"\b(contraindicatii|precautii|alimente interzise|de evitat|nu se recomanda|"
    r"nu este recomandat\w*|este contraindicat\w*|sunt contraindicat\w*|se recomanda evitarea)\b"
)
POSITIVE = re.compile(
    r"\b(se recomanda|indicat\w* pentru|util\w* in|alimente recomandate|"
    r"plante recomandate|produse recomandate|uleiuri(?: esentiale| volatile)? recomandate)\b"
)
EXCEPTION = re.compile(r"\b(dar|insa|exceptie|exceptand|numai|doar|daca|sarcina|doza|nu)\b")


def content_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class IndexedPassage:
    chunk_id: int
    document: str
    source_hash: str
    text_hash: str
    heading: str
    text: str
    primary: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    herb_id: int
    condition_id: int
    mention: Span
    mentions: tuple[Span, ...] = ()


@dataclass(frozen=True)
class Unit:
    passage: IndexedPassage
    start: int
    end: int
    headings: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    certain_context: bool
    scope: tuple[Span, ...] = ()
    scope_conditions: tuple[int, ...] = ()
    table_header: Span | None = None
    condition_mentions: tuple[tuple[int, Span], ...] = ()
    heading_aliases: tuple[str, ...] = ()
    product_categories: tuple[tuple[int, str], ...] = ()

    @property
    def text(self) -> str:
        return self.passage.text[self.start : self.end]

    @property
    def identity(self) -> str:
        return content_hash([self.passage.chunk_id, self.start, self.end])


@dataclass(frozen=True)
class Decision:
    label: Label
    origin: Literal["rule", "model"]
    rule: str
    quotes: tuple[Span, ...] = ()


# Compile each catalog once per snapshot, preserving original-text offsets during matching.
class NameMatcher:
    def __init__(
        self, names: tuple[tuple[str, tuple[int, ...]], ...], *, product_forms: bool = False
    ) -> None:
        # Expand this explicit catalog paradigm only for products, never condition aliases.
        owners = {identifier for name, ids in names if name == "rosie" for identifier in ids}
        if product_forms and len(owners) == 1:
            existing = {name for name, _ in names}
            names = (
                *names,
                *(
                    (form, tuple(sorted(owners)))
                    for form in ("rosii", "rosiile", "rosia", "rosiei", "rosiilor")
                    if form not in existing
                ),
            )
        self.names = names
        self.by_first: dict[str, list[tuple[list[str], tuple[int, ...]]]] = {}
        self.exact: dict[str, set[int]] = {}
        for name, identifiers in names:
            self.exact.setdefault(name, set()).update(identifiers)
            words = name.split()
            if words:
                self.by_first.setdefault(words[0], []).append((words, identifiers))

    def spans(self, text: str) -> Iterator[tuple[Span, tuple[int, ...]]]:
        tokens = list(re.finditer(r"\w+", text))
        normalized = [normalize_herb_name(token.group()) for token in tokens]
        for position, word in enumerate(normalized):
            for words, identifiers in self.by_first.get(word, []):
                if normalized[position : position + len(words)] == words:
                    span = (tokens[position].start(), tokens[position + len(words) - 1].end())
                    yield span, identifiers


# A multi-condition fragment needs a local condition heading or an explicit unit mention.
def extract_units(
    passage: IndexedPassage,
    herb_names: NameMatcher | tuple[tuple[str, tuple[int, ...]], ...],
    condition_names: NameMatcher | tuple[tuple[str, tuple[int, ...]], ...],
    *,
    canonical_conditions: dict[str, int] | None = None,
    herb_categories: dict[int, str] | None = None,
) -> tuple[Unit, ...]:
    herb_matcher = (
        herb_names
        if isinstance(herb_names, NameMatcher)
        else NameMatcher(herb_names, product_forms=True)
    )
    condition_matcher = (
        condition_names
        if isinstance(condition_names, NameMatcher)
        else NameMatcher(condition_names)
    )
    exact_condition_names = condition_matcher.exact
    primary_names = {normalize_herb_name(name) for name in passage.primary}
    if canonical_conditions is not None:
        allowed = {
            canonical_conditions[name] for name in primary_names if name in canonical_conditions
        }
    else:
        allowed = {
            identifier
            for name, identifiers in condition_matcher.names
            if name in primary_names
            for identifier in identifiers
        }
    if not allowed:
        return ()
    headings: list[tuple[int, str]] = [(0, passage.heading)]
    result = []
    offset = 0
    # Paragraphs, list items and table rows retain their complete local discourse context.
    blocks: list[tuple[int, int, tuple[str, ...], bool, tuple[Span, ...], Span | None]] = []
    paragraph_start: int | None = None
    paragraph_end = 0
    introduction: Span | None = None
    table_header: Span | None = None
    previous_row: Span | None = None

    def flush() -> None:
        nonlocal paragraph_start, introduction
        if paragraph_start is not None:
            blocks.append(
                (
                    paragraph_start,
                    paragraph_end,
                    tuple(h for _, h in headings),
                    len(headings) > 1,
                    (),
                    None,
                )
            )
            paragraph = passage.text[paragraph_start:paragraph_end].strip()
            introduction = (
                (paragraph_start, paragraph_end)
                if paragraph.endswith(":") and len(paragraph) <= 600
                else None
            )
            paragraph_start = None

    for line in passage.text.splitlines(keepends=True):
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        separate = bool(re.match(r"\s*(?:[-*+] |\d+[.)] |\|)", line))
        if heading or not line.strip() or separate:
            flush()
        if heading:
            introduction = table_header = previous_row = None
            level = len(heading[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading[2]))
        elif not line.strip():
            table_header = previous_row = None
        elif line.strip():
            if separate:
                row = (offset, offset + len(line))
                if re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", line):
                    table_header = previous_row
                if line.lstrip().startswith("|"):
                    previous_row = row
                else:
                    table_header = previous_row = None
                blocks.append(
                    (
                        *row,
                        tuple(h for _, h in headings),
                        len(headings) > 1,
                        (introduction,) if introduction else (),
                        table_header,
                    )
                )
            else:
                table_header = previous_row = None
                paragraph_start = offset if paragraph_start is None else paragraph_start
                paragraph_end = offset + len(line)
        offset += len(line)
    flush()
    for start, end, context, reconstructed, scope, header in blocks:
        body = passage.text[start:end]
        condition_mentions = tuple(
            (identifier, span)
            for span, identifiers in condition_matcher.spans(body)
            for identifier in identifiers
        )
        named_conditions = {identifier for identifier, _ in condition_mentions}
        inherited_conditions = {
            identifier
            for a, b in (*scope, *((header,) if header else ()))
            for _, identifiers in condition_matcher.spans(passage.text[a:b])
            for identifier in identifiers
        }
        named_conditions |= inherited_conditions
        conditions = named_conditions & allowed
        foreign_heading = False
        if not conditions:
            for heading_text in reversed(context):
                heading_conditions = {
                    i for _, ids in condition_matcher.spans(heading_text) for i in ids
                }
                if heading_conditions:
                    conditions = heading_conditions & allowed
                    foreign_heading = not conditions
                    break
        if foreign_heading:
            continue
        explicit_scope = bool(conditions)
        if not conditions and len(allowed) == 1:
            conditions = allowed
        if not conditions:
            continue
        candidates = tuple(
            sorted(
                {
                    Candidate(herb_id, condition_id, span)
                    for span, identifiers in herb_matcher.spans(body)
                    for herb_id in identifiers
                    for condition_id in conditions
                },
                key=lambda c: (c.mention, c.herb_id, c.condition_id),
            )
        )
        if candidates:
            result.append(
                Unit(
                    passage,
                    start,
                    end,
                    context,
                    candidates,
                    reconstructed
                    and explicit_scope
                    and len(conditions) == 1
                    and not (named_conditions - allowed),
                    scope,
                    tuple(sorted(conditions)) if explicit_scope else (),
                    header,
                    condition_mentions,
                    tuple(
                        h
                        for heading_text in context
                        if set(
                            exact_condition_names.get(
                                h := normalize_herb_name(heading_text.rsplit(">", 1)[-1]), ()
                            )
                        )
                        == allowed
                        and len(allowed) == 1
                    ),
                    tuple(
                        sorted(
                            (identifier, herb_categories[identifier])
                            for identifier in {c.herb_id for c in candidates}
                            if herb_categories and identifier in herb_categories
                        )
                    ),
                )
            )
    return tuple(result)


# Flattened OCR headers may precede a paragraph, but never cross an explicit section boundary.
@lru_cache(maxsize=8192)
def table_header_text(unit: Unit) -> str | None:
    if unit.table_header:
        return unit.passage.text[slice(*unit.table_header)]
    first = min((c.mention[0] for c in unit.candidates), default=0)
    prefix = unit.passage.text[: unit.start + first]
    matches = list(
        re.finditer(
            r"(?im)^[ \t]*SUPLIMENT[ \t\n]+DOZ[AĂ][ \t]*RECOMANDAT[AĂ]"
            r"(?:[ \t\n]+OBSERVA[TȚŢ]II)?[^\S\n]*(?:\n|$)",
            prefix,
        )
    )
    if not matches:
        return None
    header = matches[-1]
    for line in prefix[header.end() :].splitlines():
        normalized = normalize_herb_name(line)
        if re.match(r"^\s*#{1,6}\s", line) or normalized in {
            "plante",
            "recomandari",
            "observatii",
            "contraindicatii",
            "bibliografie",
        }:
            return None
        letters = "".join(c for c in line if c.isalpha())
        if (
            len(letters) >= 6
            and letters.isupper()
            and normalized not in {"esential", "important", "util", "foarte important"}
        ):
            return None
    return header.group()


# Context contains only material actually available in this indexed passage.
def source_context(unit: Unit) -> dict[str, object]:
    return {
        "headings": unit.headings,
        "introductions": [unit.passage.text[a:b] for a, b in unit.scope],
        "table_header": table_header_text(unit),
        "scope_conditions": unit.scope_conditions,
        "certain_context": unit.certain_context,
        "conditions_in_text": [
            {"condition_id": identifier, "start": a, "end": b, "text": unit.text[a:b]}
            for identifier, (a, b) in unit.condition_mentions
            if len(normalize_herb_name(unit.text[a:b])) >= 4
            or (len(unit.text[a:b]) >= 3 and unit.text[a:b].isupper())
        ],
    }


LIST_POSITIVE = re.compile(
    r"\b(?:(?:alimente|plante|produse|suplimente|uleiuri)(?:le)? "
    r"(?:naturiste |medicinale |esentiale |volatile )?recomandat\w*|"
    r"recomandari(?: naturiste)?|se recomanda|consumati|mancati|beti|luati|aplicati)\b"
)
LIST_NEGATIVE = re.compile(
    r"\b(?:(?:alimente|plante|produse)(?:le)? (?:nerecomandat\w*|interzis\w*)|"
    r"contraindicat\w*|a se evita|de evitat|evitati|eliminati din dieta)\b"
)
PROHIBITION_COMMAND = re.compile(
    r"(?:(?:(?:este|sunt|e) )?(?:interzis(?:a|e|i)?|contraindicat(?:a|e|i)?)|"
    r"nu (?:este|sunt|e) permis(?:a|e|i)?|nu se (?:permite|admite))"
    r"(?: (?:consumul|consumarea|administrarea)(?: de)?|"
    r" (?:a |sa )?se (?:consuma|consume|administra|administreze)|"
    r" sa (?:consumati|mancati))?\b"
)


# Only the nearest section or actual list introduction supplies a shared instruction.
def _list_instruction(unit: Unit) -> str:
    for a, b in reversed(unit.scope):
        text = normalize_herb_name(unit.passage.text[a:b])
        if (
            LIST_POSITIVE.search(text)
            or LIST_NEGATIVE.search(text)
            or NEGATIVE.search(text)
            or PROHIBITION_COMMAND.fullmatch(text)
        ):
            return text
    for heading in reversed(unit.headings):
        text = normalize_herb_name(heading.rsplit(">", 1)[-1])
        if (
            LIST_POSITIVE.search(text)
            or LIST_NEGATIVE.search(text)
            or NEGATIVE.search(text)
            or PROHIBITION_COMMAND.fullmatch(text)
        ):
            return text
        if text not in {"uz intern", "uz extern", "nutrienti", "plante"}:
            break
    return ""


# Fully parsed bans bind named products, not nearby descriptions or conditional restrictions.
@lru_cache(maxsize=8192)
def _prohibition_spans(unit: Unit) -> tuple[tuple[Span, tuple[Span, ...]], ...]:
    if not _verified_primary_heading(unit) or len(unit.scope_conditions) != 1 or "|" in unit.text:
        return ()
    allowed = {
        "de",
        "din",
        "si",
        "sau",
        "ceai",
        "infuzie",
        "decoct",
        "ulei",
        "tinctura",
        "extract",
        "suc",
        "frunze",
        "flori",
        "seminte",
        "radacina",
        "radacini",
        "pulbere",
        "crud",
        "cruda",
        "crude",
        "cruzi",
        "proaspat",
        "proaspata",
        "proaspete",
        "proaspeti",
    }
    inherited = PROHIBITION_COMMAND.fullmatch(_list_instruction(unit)) is not None
    result = []
    for sentence in re.finditer(r".+?(?:(?<![.!?])[.!?](?![.!?])(?=\s|$)|$)", unit.text, re.DOTALL):
        start, end = sentence.span()
        mentions = tuple(
            sorted(
                {c.mention for c in unit.candidates if start <= c.mention[0] < c.mention[1] <= end}
            )
        )
        if not mentions:
            continue
        text = sentence.group()
        for a, b in reversed(mentions):
            text = text[: a - start] + " " * (b - a) + text[b - start :]
        text = normalize_herb_name(text)
        text = re.sub(r"^[qoui] ", "", text)
        command = PROHIBITION_COMMAND.match(text)
        if command is None and not inherited:
            continue
        residual = text[command.end() :] if command else text
        if set(residual.split()) - allowed:
            continue
        result.append(((start, end), mentions))
    return tuple(result)


def _explicit_prohibition(
    unit: Unit, candidate: Candidate, *, whole_unit: bool = False
) -> Decision | None:
    if candidate.condition_id not in unit.scope_conditions:
        return None
    for span, products in _prohibition_spans(unit):
        if whole_unit and (unit.text[: span[0]].strip() or unit.text[span[1] :].strip()):
            continue
        if any(
            mention in products
            and _identity_decision(
                unit, Candidate(candidate.herb_id, candidate.condition_id, mention)
            )
            is None
            for mention in (candidate.mentions or (candidate.mention,))
        ):
            return Decision("caution", "rule", "explicit_consumption_prohibition_v3", (span,))
    return None


# A completely parsed instruction covers all its named products; partial parses stay semantic.
@lru_cache(maxsize=8192)
def _atomic_instruction(unit: Unit) -> Label | None:
    if not _verified_primary_heading(unit) or not unit.scope_conditions or "|" in unit.text:
        return None
    text = unit.text
    for a, b in sorted({c.mention for c in unit.candidates}, reverse=True):
        text = text[:a] + " " * (b - a) + text[b:]
    text = normalize_herb_name(re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text))
    command = re.match(
        r"^(?:[qoui] )?(?P<negative>nu (?:consumati|mancati|beti|luati|folositi)|"
        r"evitati|eliminati din dieta)\b|"
        r"^(?:[qoui] )?(?:consumati|mancati|beti|luati|aplicati|folositi|"
        r"se (?:consuma|mananca|bea|beau|ia|iau|foloseste|aplica|administreaza))\b",
        text,
    )
    if command is None:
        return None
    words = text[command.end() :].split()
    allowed = {
        "de",
        "din",
        "si",
        "sau",
        "cu",
        "o",
        "un",
        "ceai",
        "infuzie",
        "decoct",
        "ulei",
        "tinctura",
        "extract",
        "suc",
        "frunze",
        "flori",
        "seminte",
        "radacina",
        "radacini",
        "pulbere",
        "crud",
        "crude",
        "proaspat",
        "proaspete",
        "proaspata",
        "proaspeti",
        "integral",
        "integrale",
        "capsula",
        "capsule",
        "tableta",
        "tablete",
        "comprimat",
        "comprimate",
        "mg",
        "g",
        "ml",
        "mcg",
        "lingura",
        "linguri",
        "lingurita",
        "lingurite",
        "cana",
        "cani",
        "pahar",
        "pahare",
        "ori",
        "pe",
        "zi",
        "zilnic",
        "mai",
        "mult",
        "multa",
        "multe",
        "multi",
    }
    if any(not word.isdigit() and word not in allowed for word in words):
        return None
    if command["negative"] is not None:
        # Quantity/frequency limits constrain administration, not the target disease.
        if any(
            w.isdigit() or w in {"mai", "mult", "multa", "multe", "multi", "zilnic", "ori"}
            for w in words
        ):
            return None
        return "caution"
    return "positive"


# A preparation is therapeutic only with verified disease scope and an explicit intake step.
@lru_cache(maxsize=8192)
def _administered_recipe(unit: Unit) -> bool:
    if not _verified_primary_heading(unit) or not unit.scope_conditions or "|" in unit.text:
        return False
    text = normalize_herb_name(unit.text)
    if not re.match(
        r"^(?:se (?:amesteca|combina|prepara)|amestec (?:din|de))\b", text
    ) or re.search(
        r"\b(?:nu|dar|insa|except\w*|numai|doar|daca|sarcina|"
        r"precaut\w*|atentie|evit\w*|contraindicat\w*|interzis\w*|"
        r"nerecomand\w*|toxic\w*|risc\w*|alerg\w*|consult\w*|"
        r"supraveghere|sfatul medicului|interacti\w*|agrav\w*|inrautat\w*|"
        r"intrerup\w*|opriti|limit\w*|nuse|nuluati|in loc de|decat)\b",
        text,
    ):
        return False
    if any(
        identifier not in unit.scope_conditions and len(normalize_herb_name(unit.text[a:b])) >= 4
        for identifier, (a, b) in unit.condition_mentions
    ):
        return False
    administration = re.search(
        r"\b(?:se (?:bea|beau|consuma|ia|iau|inghite|administreaza|aplica)|"
        r"beti|luati|aplicati)\b",
        unit.text,
        re.IGNORECASE,
    )
    first_sentence = re.search(r"[.!?](?=\s|$)", unit.text)
    return bool(
        administration
        and first_sentence
        and all(
            c.mention[1] <= min(administration.start(), first_sentence.end())
            for c in unit.candidates
        )
    )


# These complete source constructions describe composition, not a separate therapeutic use.
def _descriptive_mention(unit: Unit, candidate: Candidate) -> bool:
    a, b = candidate.mention
    before_mention = normalize_herb_name(unit.text[max(0, a - 65) : a])
    after_mention = normalize_herb_name(unit.text[b : b + 80])
    if re.search(r"\b(?:rachiu|alcool|vodca) (?:de|din)$", before_mention) or (
        re.search(r"\b(?:adauga|adaugati|indulceste|indulciti)\b", before_mention)
        and re.match(r"^(?:dupa gust|pentru (?:gust|indulcire))\b", after_mention)
    ):
        return True
    if re.search(r"\bcu \d[\d ]* (?:mg|mcg)(?: de)?$", before_mention) and re.search(
        r"\bpentru (?:o ?)?absorbtie mai buna\b", after_mention
    ):
        return True
    if (
        re.match(r"^\s*[-*+]?\s*legume\s*\(", unit.text, re.IGNORECASE)
        and re.search(r"\)\s*fierte\b", unit.text, re.IGNORECASE)
        and not any(LIST_POSITIVE.search(normalize_herb_name(h)) for h in unit.headings)
        and not re.search(
            r"\b(?:se consuma|se mananca|consumati|mancati|recomand\w*)\b",
            normalize_herb_name(unit.text),
        )
    ):
        return True
    for sentence in re.finditer(r"[^.!?]+(?:[.!?]|$)", unit.text):
        if not sentence.start() <= a < b <= sentence.end():
            continue
        text = sentence.group()
        outside_parentheses = normalize_herb_name(re.sub(r"\([^)]*\)", "", text))
        active = re.search(
            r"\b(?:consumati|luati|mancati|beti|folositi|administrati|recomand\w*|"
            r"ajuta|benefic\w*|amelioreaz\w*|trateaz\w*|vindec\w*|combate|calmeaz\w*|"
            r"stimuleaz\w*|creste|imbunatat\w*|sustine|favorizeaz\w*|reduce|scade|previne|"
            r"terapeutic\w*)\b",
            outside_parentheses,
        )
        for parenthetical in re.finditer(r"\([^)]*\)", text):
            if parenthetical.start() <= a - sentence.start() < parenthetical.end() and re.search(
                r"\b(?:consumati|luati|mancati|beti|folositi|administrati|recomand\w*)\b",
                normalize_herb_name(parenthetical.group()),
            ):
                return False
        if active:
            continue
        before = normalize_herb_name(unit.text[sentence.start() : a])
        if re.search(
            r"\b(?:carenta|deficitul|deficit|deficienta|nivel(?:ul|uri|urile)? scazut\w*) "
            r"(?:de|in)$",
            before,
        ):
            return True
        if re.match(
            r"^(?:[qoui] )?(?:urmatoarele alimente au\b.*?\bcontinut\b|"
            r"alimente cu continut\b)",
            outside_parentheses,
        ):
            return True
        contains = re.search(r"\bcontin(?:e)?\b", text, re.IGNORECASE)
        if contains and sentence.start() + contains.end() <= a:
            objects = text[contains.end() :].strip().rstrip(".,!?")
            if (
                "," in objects
                and re.fullmatch(r"[\w\s,()\-]+", objects)
                and not re.search(
                    r"\b(?:care|pentru|necesar\w*|benefic\w*|efect\w*)\b",
                    normalize_herb_name(objects),
                )
            ):
                return True
    # An unfinished observation cannot supply a missing therapeutic assertion.
    if not any(c.herb_id != candidate.herb_id and c.mention[0] > a for c in unit.candidates):
        tail = normalize_herb_name(unit.text[b:])
        remainder = re.sub(
            r"\b(?:\d+|mg|mcg|ui|zilnic|de|ori|pe|zi|in|doze|impartite|cu)\b", " ", tail
        )
        if " ".join(remainder.split()) in {
            "apara impotriva efectelor daunatoare",
            "apara impotriva",
            "pentru refacerea",
            "pentru vindecarea",
            "pentru tratarea",
            "necesar pentru",
        }:
            return True
        ending = re.search(r"\b(?:pentru (?:refacerea|vindecarea|tratarea)|necesar pentru)$", tail)
        if ending:
            dosage = tail[: ending.start()].split()
            if all(
                word.isdigit()
                or word
                in {"mg", "mcg", "ui", "zilnic", "de", "ori", "pe", "zi", "in", "doze", "impartite"}
                for word in dosage
            ):
                return True
    near = normalize_herb_name(unit.text[max(0, a - 55) : min(len(unit.text), b + 70)])
    if (
        re.search(r"\bnecesar(?:a)? echilibrului cu\b", near)
        and re.search(r"\b(?:mg|mcg|zilnic)\b", near)
        and not re.search(r"\b(?:luati|consumati|recomand\w*|trat\w*)\b", near)
    ):
        return True
    return False


# A dictionary alias in an unrelated title cannot establish the primary disease's scope.
@lru_cache(maxsize=8192)
def _verified_primary_heading(unit: Unit) -> bool:
    if len(unit.passage.primary) != 1:
        return False
    primary = normalize_herb_name(unit.passage.primary[0])
    neutral = {
        "alimente recomandate",
        "plante recomandate",
        "produse recomandate",
        "suplimente recomandate",
        "uleiuri recomandate",
        "uleiuri esentiale recomandate",
        "uleiuri volatile recomandate",
        "recomandari",
        "recomandari naturiste",
        "nutrienti",
        "plante",
        "uz intern",
        "uz extern",
        "tratamente",
        "contraindicatii",
    }
    for heading in reversed(unit.headings):
        text = normalize_herb_name(heading.rsplit(">", 1)[-1])
        if (
            text in neutral
            or re.fullmatch(r"tabel \d+", text)
            or PROHIBITION_COMMAND.fullmatch(text)
        ):
            continue
        return text in unit.heading_aliases or bool(
            re.search(r"\b" + re.escape(primary) + r"\b", text)
        )
    return False


# Index dose-row ownership once; observation mentions do not inherit another product's row.
@lru_cache(maxsize=8192)
def _dose_row_bounds(unit: Unit) -> dict[Span, Span]:
    owners: dict[Span, int] = {}
    for candidate in unit.candidates:
        a, b = candidate.mention
        start = unit.text.rfind("\n", 0, a) + 1
        if normalize_herb_name(unit.text[start:a]) not in {"", "l"}:
            continue
        if re.match(
            r"^(?:\d[\d ]* (?:mg|mcg|g|ui|capsul\w*|comprimat\w*)\b|"
            r"conform indicatiilor\b)",
            normalize_herb_name(re.sub(r"(?<=\d)(?=[A-Za-z])", " ", unit.text[b : b + 100])),
        ):
            owners[candidate.mention] = start
    boundaries = sorted(
        {
            *owners.values(),
            *(
                match.start()
                for match in re.finditer(
                    r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?"
                    r"(?:Plante|Recomandari|Observatii|Contraindicatii)[ \t]*$",
                    unit.text,
                )
            ),
            len(unit.text),
        }
    )
    ends = dict(zip(boundaries, boundaries[1:]))
    return {mention: (start, ends[start]) for mention, start in owners.items()}


# A real recommendation plus a fully parsed dose limit is not a disease contraindication.
def _explicit_dose_row(unit: Unit, candidate: Candidate) -> Span | None:
    if (
        len(unit.passage.primary) != 1
        or not _verified_primary_heading(unit)
        or candidate.condition_id not in unit.scope_conditions
        or not re.search(
            r"\bdoza recomandata\b", normalize_herb_name(table_header_text(unit) or "")
        )
    ):
        return None
    if _collective_warning(unit) is not None:
        return None
    span = _dose_row_bounds(unit).get(candidate.mention)
    if span is None:
        return None
    text = normalize_herb_name(re.sub(r"(?<=\d)(?=[A-Za-z])", " ", unit.text[slice(*span)]))
    # Remove only bounded administration constraints; every unparsed exception remains semantic.
    quantity = r"\d[\d ,.]* (?:mg|mcg|g|ui|ml)\b"
    dose_limit = rf"nu depasiti (?:doza de )?(?:{quantity}|aceasta (?:cantitate|doza))"
    text = re.sub(rf"\bdaca sunteti insarcinata {dose_limit}(?: zilnic)?\b", " ", text)
    text = re.sub(rf"\b{dose_limit}", " ", text)
    text = re.sub(r"\bnu luati cu lapte\b", " ", text)
    text = re.sub(
        r"\bnu luati (?:acest supliment |lizina )?mai mult ?de "
        r"(?:\d+|sase) (?:zile|saptamani|luni)(?: la rand)?\b",
        " ",
        text,
    )
    if EXCEPTION.search(text) or re.search(
        r"\b(?:precaut\w*|contraindicat\w*|interzis\w*|evit\w*|risc\w*|"
        r"supraveghere|consult\w*|agrav\w*)\b",
        text,
    ):
        return None
    # An observation about another benefit does not cancel an explicit recommended-dose row.
    # Restrictive clauses were checked above; an unparsed restriction still goes to the model.
    return span


# Lexicalized condition names do not establish the shorter constituent diagnosis.
def _condition_homonym(unit: Unit, candidate: Candidate) -> bool:
    if tuple(map(normalize_herb_name, unit.passage.primary)) != ("febra",):
        return False
    pattern = r"\bfebr(?:a|ei)(?: a)? fanului\b|\bherpes(?:ul)? de febr(?:a|ei)\b"
    if not re.search(pattern, normalize_herb_name(" ".join(unit.headings))):
        return False
    compounds = [m.span() for m in re.finditer(pattern, unit.text, re.IGNORECASE)]
    evidence = [
        span for identifier, span in unit.condition_mentions if identifier == candidate.condition_id
    ]
    evidence.extend(m.span() for m in re.finditer(r"\bfebr(?:a|ei)\b", unit.text, re.IGNORECASE))
    return all(any(x <= a < b <= y for x, y in compounds) for a, b in evidence)


# Identity checks also protect independently retained prohibition evidence.
def _identity_decision(unit: Unit, candidate: Candidate) -> Decision | None:
    mention = normalize_herb_name(unit.text[slice(*candidate.mention)])
    before = normalize_herb_name(
        unit.text[max(0, candidate.mention[0] - 45) : candidate.mention[0]]
    )
    after = normalize_herb_name(unit.text[candidate.mention[1] : candidate.mention[1] + 45])
    a, b = candidate.mention
    if any(
        other.herb_id != candidate.herb_id
        and other.mention[0] == a
        and other.mention[1] > b
        and not re.search(
            r"\b(?:de|din|cu|si|pentru)\b",
            normalize_herb_name(unit.text[b : other.mention[1]]),
        )
        for other in unit.candidates
    ):
        return Decision("unclear", "rule", "qualified_catalog_identity_v3")
    if mention == "salata" and any(
        other.herb_id != candidate.herb_id
        and b < other.mention[0] <= b + 8
        and normalize_herb_name(unit.text[b : other.mention[0]]) in {"de", "din"}
        for other in unit.candidates
    ):
        return Decision("unclear", "rule", "preparation_nonentity_v3")
    if (
        mention == "bine"
        and (
            re.search(
                r"\b(mai|foarte|fel de|destul de|tolereaza|presand|presandu se|presa|strecoara|"
                r"udati|face|imbiba|este|functioneaza|se|amesteca|amestecati|combina|combinati|"
                r"prepara|preparati|spala|spalati)$",
                before,
            )
            or re.match(r"(?:cunoscut\w*|mestecat\w*|facut\w*|plantele|ca|sa)\b", after)
        )
    ) or (mention == "same" and re.match(r"(?:species|method|time)\b", after)):
        return Decision("unclear", "rule", "grammatical_nonentity_v3")
    if len(mention) == 1 and not re.search(r"\bvitamina$", before):
        return Decision("unclear", "rule", "isolated_letter_v3")
    if mention in {
        "rosie",
        "rosii",
        "rosu",
        "rosia",
        "rosiile",
        "rosiei",
        "rosiilor",
    } and re.search(
        r"\b(carne|carn|sange|globule|ochi|vin|prune|drojdie|sfecla|boabe|"
        r"ardei|varza|ceap|fasol)\w*$",
        before,
    ):
        return Decision("unclear", "rule", "colour_nonentity_v3")
    if mention == "calciu" and re.search(r"\boxalat de$", before):
        return Decision("unclear", "rule", "chemical_constituent_v3")
    if mention == "sica" and before.endswith("nervilor") and re.match(r"sa\b", after):
        return Decision("unclear", "rule", "grammatical_nonentity_v3")
    if mention == "hepatica" and re.search(r"\b(ciroza|insuficienta|colica|functie)$", before):
        return Decision("unclear", "rule", "condition_adjective_v3")
    if (
        mention == "date"
        and re.search(
            r"\b(?:sunt|fost|fi|erau|neplacute|probleme|simptome|manifestari|reactii)$", before
        )
        and re.match(r"^de\b", after)
    ):
        return Decision("unclear", "rule", "grammatical_nonentity_v3")
    if re.search(r"\bmiere de$", before):
        return Decision("unclear", "rule", "honey_botanical_origin_v3")
    if any(
        other.mention == candidate.mention and other.herb_id != candidate.herb_id
        for other in unit.candidates
    ):
        return Decision("unclear", "rule", "ambiguous_identity_v2")
    return None


# Lexical identity precedes bounded structural rules; unresolved discourse stays semantic.
def classify_rule(unit: Unit, candidate: Candidate) -> Decision | None:
    identity = _identity_decision(unit, candidate)
    if identity is not None:
        return identity
    prohibition = _explicit_prohibition(unit, candidate, whole_unit=True)
    if prohibition is not None:
        return prohibition
    if _condition_homonym(unit, candidate):
        return Decision("unclear", "rule", "compound_condition_homonym_v3")
    dose_row = _explicit_dose_row(unit, candidate)
    if dose_row is not None:
        return Decision("positive", "rule", "indexed_recommended_dose_v3", (dose_row,))
    if _descriptive_mention(unit, candidate):
        return Decision("unclear", "rule", "explicit_composition_v3")
    instruction = _atomic_instruction(unit)
    if instruction is not None:
        return Decision(
            instruction, "rule", "complete_administration_instruction_v3", ((0, len(unit.text)),)
        )
    if _administered_recipe(unit):
        return Decision(
            "positive", "rule", "explicit_recipe_administration_v3", ((0, len(unit.text)),)
        )
    if (
        not unit.certain_context
        or candidate.condition_id not in unit.scope_conditions
        or not _verified_primary_heading(unit)
    ):
        return _classify_adjacent(unit, candidate)
    text = normalize_herb_name(unit.text)
    # Mixed polarity, exceptions and restrictions always keep their full context for the model.
    if (
        len(unit.text) > 600
        or EXCEPTION.search(text)
        or re.search(r"\b(gravide|copii|alaptare|doze|sarcina|hipertensiune|hipotensiune)\b", text)
    ):
        return _classify_adjacent(unit, candidate)
    positive, negative = bool(LIST_POSITIVE.search(text)), bool(LIST_NEGATIVE.search(text))
    if positive and re.search(
        r"\b(agrav\w*|inrautat\w*|nerecomandat\w*|interzis\w*|toxic\w*|"
        r"precautii|atentie|risc\w*|nociv\w*)\b",
        text,
    ):
        return None
    scope = _list_instruction(unit)
    if "|" in unit.text:
        if unit.table_header:
            residual = unit.text
            for span in sorted({c.mention for c in unit.candidates}, reverse=True):
                residual = residual[: span[0]] + " " + residual[span[1] :]
            if re.search(r"\w", residual):
                return None
            headers = unit.passage.text[slice(*unit.table_header)].strip().strip("|").split("|")
            cells = list(re.finditer(r"(?<=\|)[^|]*(?=\|)", unit.text))
            index = next(
                (
                    i
                    for i, cell in enumerate(cells)
                    if cell.start() <= candidate.mention[0] < cell.end()
                ),
                None,
            )
            if index is not None and index < len(headers):
                header = normalize_herb_name(headers[index])
                p, n = bool(LIST_POSITIVE.search(header)), bool(LIST_NEGATIVE.search(header))
                if p != n and not (positive or negative):
                    return Decision(
                        "positive" if p else "caution",
                        "rule",
                        "explicit_table_column_v3",
                        ((0, len(unit.text)),),
                    )
        return None
    # A list introduction scopes bare entries, but never turns an arbitrary paragraph positive.
    outside = unit.text
    for span in sorted({c.mention for c in unit.candidates}, reverse=True):
        outside = outside[: span[0]] + " " + outside[span[1] :]
    bare_words = normalize_herb_name(outside).split()
    bare = all(
        word.isdigit()
        or word
        in {
            "ceai",
            "tinctura",
            "infuzie",
            "decoct",
            "pulbere",
            "extract",
            "ulei",
            "suc",
            "de",
            "din",
            "si",
            "cu",
            "frunze",
            "flori",
            "seminte",
            "radacina",
            "radacini",
            "lingura",
            "linguri",
            "lingurita",
            "lingurite",
            "parte",
            "parti",
            "g",
            "mg",
            "ml",
        }
        for word in bare_words
    )
    first = min(c.mention[0] for c in unit.candidates)
    prefix = normalize_herb_name(unit.text[:first])
    p_scope, n_scope = bool(LIST_POSITIVE.search(scope)), bool(LIST_NEGATIVE.search(scope))
    if bare and p_scope != n_scope and not (positive or negative):
        return Decision(
            "positive" if p_scope else "caution",
            "rule",
            "explicit_list_scope_v3",
            ((0, len(unit.text)),),
        )
    if (
        positive != negative
        and (LIST_POSITIVE.search(prefix) or LIST_NEGATIVE.search(prefix))
        and len(re.findall(r"[.!?](?:\s|$)", unit.text.strip())) <= 1
    ):
        # Shared list recommendations require an explicit list, not a distant verb in prose.
        if ":" in unit.text[:first] or re.match(
            r"^(?:alimente|plante|produse|suplimente)\b", prefix
        ):
            return Decision(
                "positive" if positive else "caution",
                "rule",
                "explicit_common_list_v3",
                ((0, len(unit.text)),),
            )
    return _classify_adjacent(unit, candidate)


# Adjacent grammatical templates remain a fallback for unambiguous single-product statements.
def _classify_adjacent(unit: Unit, candidate: Candidate) -> Decision | None:
    if unit.headings and normalize_herb_name(unit.headings[-1]) in {
        "works cited",
        "references",
        "bibliografie",
        "surse bibliografice",
        "referinte",
    }:
        return Decision("unclear", "rule", "bibliography_only_v2")
    # A shared alias cannot establish which catalog identity the source means.
    if any(
        other.mention == candidate.mention and other.herb_id != candidate.herb_id
        for other in unit.candidates
    ):
        return Decision("unclear", "rule", "ambiguous_identity_v2")
    text = normalize_herb_name(unit.text)
    if not unit.certain_context or len({c.herb_id for c in unit.candidates}) != 1:
        return None
    negative = bool(NEGATIVE.search(text))
    positive = bool(POSITIVE.search(NEGATIVE.sub("", text)))
    stripped = NEGATIVE.sub("", text)
    if (
        EXCEPTION.search(stripped)
        or "|" in unit.text
        or re.search(
            r"\b(evit\w*|interzis\w*|contraindicat\w*|agrav\w*|in loc de|fara)\b", stripped
        )
        or len(re.findall(r"[.!?](?:\s|$)", unit.text.strip())) > 1
    ):
        return None
    # Other named conditions or physiological restrictions need relation-aware adjudication.
    if len(unit.passage.primary) != 1 or re.search(
        r"\b(gravide|copii|alaptare|hipertensiune|hipotensiune|sarcina|doze)\b", text
    ):
        return None
    if not _verified_primary_heading(unit) and not re.search(
        r"\b" + re.escape(normalize_herb_name(unit.passage.primary[0])) + r"\b", text
    ):
        return None
    heading = normalize_herb_name(unit.headings[-1]) if unit.headings else ""
    heading_negative, heading_positive = (
        bool(NEGATIVE.fullmatch(heading)),
        bool(POSITIVE.fullmatch(heading)),
    )
    if (positive and heading_negative) or (negative and heading_positive):
        return None
    if not negative and not positive:
        # Inherited list scope is safe only for bare entries, not arbitrary prose or table columns.
        outside_mention = unit.text[: candidate.mention[0]] + unit.text[candidate.mention[1] :]
        outside_mention = re.sub(r"^\s*(?:[-*+] |\d+[.)] )", "", outside_mention)
        if re.search(r"\w", outside_mention):
            return None
        negative, positive = heading_negative, heading_positive
    else:
        mention_start = len(normalize_herb_name(unit.text[: candidate.mention[0]]))
        if mention_start:
            mention_start += 1
        mention_end = mention_start + len(normalize_herb_name(unit.text[slice(*candidate.mention)]))
        # Rules cover adjacent grammatical templates; distant cues require semantic classification.
        positive_text = NEGATIVE.sub(lambda match: " " * len(match.group()), text)
        cues = [*NEGATIVE.finditer(text), *POSITIVE.finditer(positive_text)]
        connectors = {
            "un",
            "o",
            "ceai",
            "infuzie",
            "decoct",
            "ulei",
            "tinctura",
            "de",
            "din",
            "cu",
            "planta",
            "produsul",
            "folosirea",
            "consumul",
            "este",
            "sunt",
        }
        if not all(
            len(
                gap := (
                    text[cue.end() : mention_start]
                    if cue.end() <= mention_start
                    else text[mention_end : cue.start()]
                    if mention_end <= cue.start()
                    else ""
                )
            )
            <= 60
            and set(gap.split()) <= connectors
            for cue in cues
        ):
            return None
    # Unrecognized condition names in a warning are not assumed to match the title.
    if negative and re.search(r"\b(in|pentru|la)\b", stripped):
        primary = normalize_herb_name(unit.passage.primary[0])
        if primary not in text:
            return None
    if not (negative or positive):
        return None
    label: Label = "mixed" if negative and positive else "caution" if negative else "positive"
    # Quotes are original unit offsets; the heading remains separate contextual provenance.
    return Decision(label, "rule", "explicit_scope_v1", ((0, len(unit.text)),))


# A source class restriction binds only catalog members and an explicitly named target.
@lru_cache(maxsize=8192)
def _collective_warning(unit: Unit) -> Span | None:
    if len(unit.passage.primary) != 1 or not _verified_primary_heading(unit):
        return None
    primary = normalize_herb_name(unit.passage.primary[0])
    boundaries = sorted(
        {0, len(unit.text), *(m.start() for m in re.finditer(r"(?m)^[ \t]*[QOU] ", unit.text))}
    )
    for start, end in zip(boundaries, boundaries[1:]):
        # Soft-wrapped OCR verbs keep their meaning; provenance always uses untouched source.
        text = normalize_herb_name(
            re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", unit.text[start:end])
        )
        if not re.search(r"\b" + re.escape(primary) + r"\b", text):
            continue
        if any(
            identifier not in unit.scope_conditions
            and start <= a < b <= end
            and len(normalize_herb_name(unit.text[a:b])) >= 4
            for identifier, (a, b) in unit.condition_mentions
        ) or re.search(
            r"\b(?:se credea|in trecut|mit|fals|nu descurajeaz\w*|nu evitati|"
            r"nu sunt contraindicat\w*|fara contraindicatii|nu depasiti|mai mult de|"
            r"numai|doar|except\w*|sarcina|insarcinat\w*|alapt\w*)\b",
            text,
        ):
            continue
        supplement = r"supliment(?:e|ele|elor)(?: alimentare)?\b"
        if re.search(
            rf"\b(?:evitati|nu (?:luati|folositi|administrati|utilizati))\b.{{0,100}}\b{supplement}|"
            rf"\b{supplement}.{{0,100}}\b(?:contraindicat\w*|nerecomandat\w*|interzis\w*)\b|"
            rf"\bdescurajeaz\w*\b.{{0,100}}\butiliz\w*\b.{{0,80}}\b{supplement}",
            text,
        ):
            return start, end
    return None


# Only an explicit target/product or verified product-class warning constrains model decisions.
def scoped_warning(unit: Unit, candidate: Candidate) -> Decision | None:
    mentions = candidate.mentions or (candidate.mention,)
    if all(
        any(c.herb_id != candidate.herb_id and c.mention == span for c in unit.candidates)
        for span in mentions
    ):
        return None
    prohibition = _explicit_prohibition(unit, candidate)
    if prohibition is not None:
        return prohibition
    collective = _collective_warning(unit)
    if collective is not None and dict(unit.product_categories).get(candidate.herb_id) in {
        "suplimente",
        "aminoacizi",
        "vitamine",
        "minerale",
    }:
        return Decision(
            "caution", "rule", "explicit_supplement_class_restriction_v3", (collective,)
        )
    for sentence in re.finditer(r"[^.!?]+(?:[.!?]|$)", unit.text):
        a, b = sentence.span()
        product_spans = [span for span in mentions if a <= span[0] < span[1] <= b]
        if not product_spans:
            for start, end in mentions:
                lemma = unit.text[start:end]
                if re.fullmatch(r"[^\W\d_]{4,}", lemma) and lemma[-1].lower() not in "aeiou":
                    product_spans.extend(
                        (a + match.start(), a + match.end())
                        for match in re.finditer(
                            rf"\b{re.escape(lemma)}(?:ul|ului)\b", sentence.group(), re.IGNORECASE
                        )
                    )
        text = normalize_herb_name(sentence.group())
        foreign_condition = any(
            identifier != candidate.condition_id
            and a <= span[0] < span[1] <= b
            and len(normalize_herb_name(unit.text[slice(*span)])) >= 4
            for identifier, span in unit.condition_mentions
        )
        if (
            product_spans
            and candidate.condition_id in unit.scope_conditions
            and not foreign_condition
        ):
            avoid = re.match(
                r"^(?:[qoui] )?(?:evitati|eliminati|nu (?:luati|mancati|consumati|folositi))\b",
                text,
            )
            limited = re.search(
                r"\b(doza|doze|mg|mcg|zilnic|impreuna|separat|sarcina|copii|gravide)\b|"
                r"\b(?:mai mult|in acelasi timp|daca|numai|doar)\b",
                text,
            )
            supervised = re.search(
                r"\b(?:urmati|cereti) sfatul (?:medicului|nutritionistului)\b|"
                r"\b(?:numai|doar) sub supraveghere medicala\b",
                text,
            )
            negated = re.search(r"\bnu (?:urmati|cereti|evitati|eliminati)\b", text)
            if not negated and ((avoid and not limited) or supervised):
                return Decision("caution", "rule", "explicit_scoped_restriction_v3", ((a, b),))
        target_spans = [
            span
            for identifier, span in unit.condition_mentions
            if identifier == candidate.condition_id
            and a <= span[0] < span[1] <= b
            and len(normalize_herb_name(unit.text[slice(*span)])) >= 4
        ]
        if not product_spans or not target_spans:
            continue
        if re.search(r"\b(nu|fara|except\w*|nici|altceva|exclus\w*)\b", text):
            continue
        warning = re.search(
            r"\b(?:daca|cand) (?:aveti|suferiti de) .{0,100}?"
            r"\b(?:consultati|intrebati) (?:medicul|un medic)\b.*?"
            r"\binainte\b.{0,100}?\b(?:lua|luati|folosi|utiliza|administra)\b",
            text,
        )
        if warning is None:
            continue
        consultation = re.search(r"\b(?:consultati|intrebati)\b", text)
        assert consultation is not None
        if any(
            identifier != candidate.condition_id
            and a <= span[0] < b
            and len(normalize_herb_name(unit.text[a : span[0]])) < consultation.start()
            for identifier, span in unit.condition_mentions
        ) or any(
            other.herb_id != candidate.herb_id and a <= other.mention[0] < b
            for other in unit.candidates
        ):
            continue
        if any(
            len(normalize_herb_name(unit.text[a : span[1]])) <= consultation.start()
            for span in target_spans
        ) and any(
            len(normalize_herb_name(unit.text[a : span[0]])) >= consultation.end()
            for span in product_spans
        ):
            return Decision("caution", "rule", "explicit_target_consultation_v3", ((a, b),))
    return None


# Canonical evidence remains bounded while no established polarity can disappear.
def combine_decisions(decisions: list[Decision]) -> Decision:
    label = pair_state([decision.label for decision in decisions])
    mixed = next((decision for decision in decisions if decision.label == "mixed"), None)
    if label == "mixed" and mixed is not None:
        quotes = mixed.quotes
    else:
        quotes = tuple(
            dict.fromkeys(
                decision.quotes[0]
                for polarity in (("positive", "caution") if label == "mixed" else (label,))
                for decision in [next(d for d in decisions if d.label == polarity)]
                if decision.quotes
            )
        )
    return Decision(
        label,
        "model" if any(d.origin == "model" for d in decisions) else "rule",
        decisions[0].rule if len({d.rule for d in decisions}) == 1 else "combined_unit_rules_v3",
        quotes,
    )


def pair_state(labels: list[str]) -> Label:
    positive = any(label in {"positive", "mixed"} for label in labels)
    caution = any(label in {"caution", "mixed"} for label in labels)
    return (
        "mixed"
        if positive and caution
        else "positive"
        if positive
        else "caution"
        if caution
        else "unclear"
    )
