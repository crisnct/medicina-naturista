"""Level 1 of the multilevel knowledge: prompt, output schema, windows, quote location, linking.

Pure functions (the prompt file is the only thing read). A claim survives only when its quote is found
in the fragment, and the quote stored is always the fragment's own text with its offsets, never what
the model wrote.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.ai.herb_index_catalog import normalize_herb_name
from backend.core.language import Language, read_prompt

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "knowledge_l1_system.md"

RELATIONS: tuple[str, ...] = (
    "helps",
    "treats",
    "prevents",
    "contraindicated",
    "interacts",
    "side_effect",
    "causes",
    "caution",
    "dose",
    "preparation",
    "contains",
    "property",
)
MAX_CLAIMS = 25
MAX_QUESTIONS = 5
# A fragment longer than this is sent in windows: the E0 pilot truncated the answer (4096 tokens)
# only on dense fragments of about 8,000 characters, and the corpus has fragments of 1.9 M.
WINDOW_CHARS = 4_000
# A window whose answer is still truncated or not JSON is halved down to this size, then given up.
MIN_WINDOW_CHARS = 1_000
# A tolerant quote match needs this many letters and digits, so a short common word never matches.
MIN_QUOTE_KEY_CHARS = 8
# Bumped when the meaning of the stored output changes, so the cache and the runs start over.
OUTPUT_VERSION = 1

# Models drop Markdown emphasis when they copy a quote (E0: 83% -> 100% exact on qwen3.5:9b), so the
# model sees the fragment without bold/italic markers and the quote is located in that text. Links
# keep only their label: web-scraped sources hold `[tratament](javascript:void(0))` inside sentences.
_MARKUP = re.compile(
    r"\*\*|__|(?P<open>!?\[)(?P<label>[^\[\]\n]*)(?P<close>\]\((?:[^()\s]|\([^()\s]*\))*\))"
)


def _markup_spans(raw: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for marker in _MARKUP.finditer(raw):
        if marker.group("open") is None:
            spans.append(marker.span())
        else:
            spans.extend((marker.span("open"), marker.span("close")))
    return spans


def response_schema() -> dict[str, Any]:
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "maxItems": MAX_CLAIMS,
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": text,
                        "relation": {"type": "string", "enum": list(RELATIONS)},
                        "object": text,
                        "dose": text,
                        "duration": text,
                        "population": text,
                        "statement": text,
                        "quote": text,
                    },
                    "required": [
                        "subject",
                        "relation",
                        "object",
                        "dose",
                        "duration",
                        "population",
                        "statement",
                        "quote",
                    ],
                    "additionalProperties": False,
                },
            },
            "questions": {"type": "array", "maxItems": MAX_QUESTIONS, "items": text},
        },
        "required": ["claims", "questions"],
        "additionalProperties": False,
    }


def system_prompt(language: Language) -> str:
    return read_prompt(PROMPT_PATH, language)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# Everything that changes what the model is asked or how its answer is read; part of every cache key.
def prompt_sha256(language: Language) -> str:
    return sha256_text(
        json.dumps(
            [
                OUTPUT_VERSION,
                system_prompt(language),
                response_schema(),
                WINDOW_CHARS,
                MIN_WINDOW_CHARS,
                MIN_QUOTE_KEY_CHARS,
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
    )


# The Merkle key of one model input: its L0 parent, the exact message, the prompt and the model.
def input_sha256(text_sha256: str, message: str, prompt_sha: str, model: str) -> str:
    return sha256_text(json.dumps([text_sha256, message, prompt_sha, model], ensure_ascii=False))


@dataclass(frozen=True)
class ModelText:
    """The fragment as the model sees it, with the position in the original text of every character
    (plus one past the end), so a located quote maps back to the stored fragment."""

    text: str
    raw_positions: tuple[int, ...]

    def raw_span(self, start: int, end: int) -> tuple[int, int]:
        return self.raw_positions[start], self.raw_positions[end - 1] + 1


def model_text(raw: str) -> ModelText:
    kept: list[str] = []
    positions: list[int] = []
    cursor = 0
    for start, end in _markup_spans(raw):
        kept.append(raw[cursor:start])
        positions.extend(range(cursor, start))
        cursor = end
    kept.append(raw[cursor:])
    positions.extend(range(cursor, len(raw)))
    positions.append(len(raw))
    return ModelText("".join(kept), tuple(positions))


@dataclass(frozen=True)
class Window:
    start: int
    end: int


# The best cut in text[low:high]: after a blank line, then a line break, then a space; else `high`.
def _cut(text: str, low: int, high: int) -> int:
    for separator in ("\n\n", "\n", " "):
        position = text.rfind(separator, low, high)
        if position > low:
            return position + len(separator)
    return high


# Consecutive windows of at most `limit` characters covering text[start:end], cut at paragraph or
# line boundaries where possible. They do not overlap: a claim's quote must sit inside one window.
def split_windows(
    text: str, start: int = 0, end: int | None = None, limit: int = WINDOW_CHARS
) -> list[Window]:
    stop = len(text) if end is None else end
    windows = []
    cursor = start
    while stop - cursor > limit:
        cut = _cut(text, cursor + limit // 2, cursor + limit)
        windows.append(Window(cursor, cut))
        cursor = cut
    if stop > cursor:
        windows.append(Window(cursor, stop))
    return windows


# Two halves of a window whose answer did not fit, or None when it is already the smallest size.
def halve(text: str, window: Window) -> tuple[Window, Window] | None:
    length = window.end - window.start
    if length < 2 * MIN_WINDOW_CHARS:
        return None
    middle = window.start + length // 2
    cut = _cut(text, window.start + MIN_WINDOW_CHARS, middle + MIN_WINDOW_CHARS // 2)
    return Window(window.start, cut), Window(cut, window.end)


def user_message(heading: str, text: str, part: int, parts: int) -> str:
    position = f" (part {part} of {parts} of a longer text)" if parts > 1 else ""
    return f"Section path: {heading or '-'}\n\nFragment{position}:\n<<<\n{text}\n>>>"


# Letters and digits only, lower case, without diacritics, each with its position in `text`: OCR line
# breaks, broken words ("galac-tagoge") and spacing then no longer decide whether a quote is found.
def _match_key(text: str) -> tuple[str, list[int]]:
    letters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(text):
        for part in unicodedata.normalize("NFKD", character):
            if unicodedata.combining(part):
                continue
            for folded in part.casefold():
                if folded.isalnum():
                    letters.append(folded)
                    positions.append(index)
    return "".join(letters), positions


# Where the model's quote is in `text`: (start, end, "exact" | "tolerant"), or None when it is not
# there even after ignoring case, diacritics, spacing and punctuation.
def locate_quote(text: str, quote: str) -> tuple[int, int, str] | None:
    stripped = quote.strip()
    if not stripped:
        return None
    position = text.find(stripped)
    if position >= 0:
        return position, position + len(stripped), "exact"
    wanted, _ = _match_key(stripped)
    if len(wanted) < MIN_QUOTE_KEY_CHARS:
        return None
    haystack, positions = _match_key(text)
    found = haystack.find(wanted)
    if found < 0:
        return None
    return positions[found], positions[found + len(wanted) - 1] + 1, "tolerant"


_FIELDS = ("subject", "relation", "object", "dose", "duration", "population", "statement", "quote")


@dataclass(frozen=True)
class Extraction:
    """The validated answer for one window, in fragment coordinates (raw offsets), ready for the
    cache. `rejected` keeps every dropped claim with its reason, for the counters and the review."""

    claims: tuple[dict[str, Any], ...] = ()
    questions: tuple[str, ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    failed: bool = False
    splits: int = field(default=0, compare=False)

    def as_output(self) -> dict[str, Any]:
        return {
            "claims": list(self.claims),
            "questions": list(self.questions),
            "rejected": list(self.rejected),
            "failed": self.failed,
        }


def extraction_from_output(output: Mapping[str, Any]) -> Extraction:
    return Extraction(
        tuple(output.get("claims") or ()),
        tuple(output.get("questions") or ()),
        tuple(output.get("rejected") or ()),
        bool(output.get("failed")),
    )


def merge(parts: Iterable[Extraction]) -> Extraction:
    items = list(parts)
    return Extraction(
        tuple(claim for part in items for claim in part.claims),
        unique_questions(question for part in items for question in part.questions),
        tuple(rejected for part in items for rejected in part.rejected),
        any(part.failed for part in items),
        sum(part.splits for part in items),
    )


def unique_questions(questions: Iterable[str], limit: int | None = None) -> tuple[str, ...]:
    seen: set[str] = set()
    kept: list[str] = []
    for question in questions:
        key = " ".join(question.casefold().split())
        if key and key not in seen:
            seen.add(key)
            kept.append(question)
    return tuple(kept[:limit] if limit is not None else kept)


def _text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


# The model's answer for text[window] checked against the fragment, or None when it is not the
# promised JSON object (the caller then halves the window).
def parse_response(
    content: str, fragment: ModelText, raw: str, window: Window
) -> Extraction | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("claims"), list)
        or not isinstance(data.get("questions"), list)
    ):
        return None
    excerpt = fragment.text[window.start : window.end]
    claims: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in data["claims"][:MAX_CLAIMS]:
        if not isinstance(item, dict):
            rejected.append({"reason": "invalid_shape"})
            continue
        values = {name: _text(item.get(name)) for name in _FIELDS}
        quote = item.get("quote")
        values["quote"] = quote if isinstance(quote, str) else ""
        reason = None
        if values["relation"] not in RELATIONS:
            reason = "unknown_relation"
        elif not (values["subject"] and values["object"] and values["statement"]):
            reason = "missing_field"
        located = locate_quote(excerpt, values["quote"]) if reason is None else None
        if reason is None and located is None:
            reason = "quote_not_found"
        if reason is not None or located is None:
            rejected.append({"reason": reason or "quote_not_found", **values})
            continue
        start, end = fragment.raw_span(window.start + located[0], window.start + located[1])
        claims.append(
            {
                **values,
                "quote": raw[start:end],
                "quote_start": start,
                "quote_end": end,
                "quote_match": located[2],
            }
        )
    questions = unique_questions(
        (_text(question) for question in data["questions"] if _text(question)), MAX_QUESTIONS
    )
    return Extraction(tuple(claims), questions, tuple(rejected))


@dataclass(frozen=True)
class CatalogLinker:
    """Normalized catalog names (herbs with aliases, conditions with synonyms) to entity keys
    (`herb:<name>`, `condition:<canonical name>`). A canonical name wins over other entities' aliases
    ("musetel" is one herb's name and another's regional alias); any other shared name links to
    none."""

    terms: Mapping[str, str]

    @classmethod
    def build(
        cls,
        herbs: Iterable[tuple[str, Iterable[str]]],
        conditions: Iterable[tuple[str, Iterable[str]]],
    ) -> CatalogLinker:
        # owners[term] = (keys owning it as canonical name, keys owning it as an alias)
        owners: dict[str, tuple[set[str], set[str]]] = {}
        for prefix, entities in (("herb", herbs), ("condition", conditions)):
            for name, aliases in entities:
                key = f"{prefix}:{name}"
                for tier, term in [(0, name), *((1, alias) for alias in aliases)]:
                    normalized = normalize_herb_name(term or "")
                    if normalized:
                        owners.setdefault(normalized, (set(), set()))[tier].add(key)
        terms = {}
        for term, (canonical, aliases) in owners.items():
            keys = canonical or aliases
            if len(keys) == 1:
                terms[term] = next(iter(keys))
        return cls(terms)

    def link(self, name: str) -> str | None:
        return self.terms.get(normalize_herb_name(name))


# Catalog keys of a claim's subject and object; the item is filed under the subject when it is a
# catalog entity, else under the object.
def claim_keys(claim: Mapping[str, Any], linker: CatalogLinker) -> tuple[str | None, str | None]:
    return linker.link(str(claim.get("subject", ""))), linker.link(str(claim.get("object", "")))
