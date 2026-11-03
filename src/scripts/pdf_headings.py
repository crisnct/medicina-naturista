"""Give the headings of vision-transcribed pages the same levels across the whole book.

The vision model only sees one page, so a page that holds nothing but small headings makes it label
them as its main headings, which splits a section from its own parts. The printed size of each
heading, read from the PDF's text layer, decides the level instead, and text that the model
wrongly made a heading is turned back into a paragraph.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from statistics import median

import pymupdf

if __package__:
    from .script_logging import log_call
else:
    from script_logging import log_call


HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Decorative rules between blocks carry no text.
RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
# A heading is a short title; a long line, or a label followed by a whole sentence, is a paragraph.
RUN_IN_LENGTH = 100
RUN_IN_REST = 20
RUN_IN_LABEL = 80
LOWERCASE_START_LENGTH = 40
# Heading text is matched to layer lines on letters and digits only.
MATCH_SCORE = 0.75
# The first line of a heading that wraps over two printed lines.
MIN_FIRST_LINE = 10
FIRST_LINE_SCORE = 0.9
# The layer estimates sizes in whole points, so half a point is already finer than its noise.
SIZE_STEP = 0.5
# Evidence for the size that separates sections from smaller headings.
MIN_SAMPLES = 3
MIN_GAP = 1.0
LABEL_MARGIN = 1.5
SECTION = 0
PART = 1

# A numbered book states its hierarchy itself: "2." is a chapter, "2.1." a section of it and
# "2.1.1." a part of that. The book counts as numbered when most of its headings carry a number.
NUMBERED_WITH_DOT = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3})*)\.(?:\s|$)")
NUMBERED_MULTI = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3})+)\s")
MIN_NUMBERED = 8
NUMBERED_SHARE = 0.4
MAX_DEPTH_RANK = 3

# [printed size or None, ends in a colon, level in the Markdown, depth of its number or 0]
Measured = list[float | bool | int | None]


def _key(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain.lower())


def _is_label(heading: str) -> bool:
    return re.sub(r"[*_`\s]+$", "", heading).endswith(":")


# Whitespace left by removed lines never grows into more than one blank line.
def _squeeze(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return out


def drop_rules(markdown: str) -> str:
    return "\n".join(
        _squeeze([line for line in markdown.splitlines() if not RULE_LINE.match(line)])
    )


# A label followed by its text on the same printed line is a run-in head, not a heading.
def _is_run_in(text: str) -> bool:
    if len(text) > RUN_IN_LENGTH:
        return True
    if text[:1].islower() and len(text) > LOWERCASE_START_LENGTH:
        return True
    label, separator, rest = text.partition(": ")
    return (
        bool(separator) and len(rest) >= RUN_IN_REST and rest.rstrip("*").endswith((".", ",", ";"))
    )


@log_call
def demote_run_in(markdown: str, min_level: int) -> str:
    """Turn headings of at least `min_level` that are really paragraphs into paragraphs."""
    out = []
    for line in markdown.splitlines():
        match = HEADING_LINE.match(line)
        if match is None or len(match.group(1)) < min_level or not _is_run_in(match.group(2)):
            out.append(line)
            continue
        label, separator, rest = match.group(2).partition(": ")
        if separator and len(label) <= RUN_IN_LABEL:
            out.append(f"**{label}:** {rest}")
        else:
            out.append(match.group(2))
    return "\n".join(out)


def heading_entries(lines: list[str], min_level: int) -> list[tuple[int, int, str]]:
    """(line index, level, text) of each heading of at least `min_level`."""
    entries = []
    for index, line in enumerate(lines):
        match = HEADING_LINE.match(line)
        if match and len(match.group(1)) >= min_level:
            entries.append((index, len(match.group(1)), match.group(2)))
    return entries


def _layer_lines(page: pymupdf.Page) -> list[tuple[str, float]]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [span for span in line["spans"] if span["text"].strip()]
            if spans:
                text = _key(" ".join(span["text"] for span in spans))
                lines.append((text, max(span["size"] for span in spans)))
    return lines


# Size of the printed line that carries the heading, or None when the layer has no such line.
def _size_of(heading: str, lines: list[tuple[str, float]]) -> float | None:
    wanted = _key(heading)
    best_score, best_size = 0.0, None
    for text, size in lines:
        if not text or not wanted:
            continue
        score = difflib.SequenceMatcher(None, wanted, text).ratio()
        if len(text) >= MIN_FIRST_LINE and wanted.startswith(text):
            score = max(score, FIRST_LINE_SCORE)
        if score >= MATCH_SCORE and score > best_score:
            best_score, best_size = score, round(size / SIZE_STEP) * SIZE_STEP
    return best_size


# Number of parts in a heading's own number ("2.1.1." is 3), 0 when it has none.
def numbering_depth(heading: str) -> int:
    match = NUMBERED_WITH_DOT.match(heading) or NUMBERED_MULTI.match(heading)
    return match.group(1).count(".") + 1 if match else 0


@log_call
def measure_headings(page: pymupdf.Page, entries: list[tuple[int, int, str]]) -> list[Measured]:
    """For each heading: printed size, whether it ends in a colon, its Markdown level and the
    depth of its number."""
    if not entries:
        return []
    layer = _layer_lines(page)
    return [
        [_size_of(text, layer), _is_label(text), level, numbering_depth(text)]
        for _, level, text in entries
    ]


@log_call
def numbered_book(pages: list[list[Measured]]) -> bool:
    """True when enough of the headings carry a number to take their levels from it."""
    depths = [item[3] for page in pages for item in page]
    numbered = sum(bool(depth) for depth in depths)
    return numbered >= MIN_NUMBERED and numbered >= NUMBERED_SHARE * len(depths)


@log_call
def section_size(pages: list[list[Measured]]) -> float | None:
    """Smallest size that counts as a section heading, or None without enough evidence.

    A page where the model itself saw two heading styles shows which size belongs to which; a
    heading that ends in a colon is a part wherever it stands."""
    sections: list[float] = []
    parts: list[float] = []
    labels: list[float] = []
    for page in pages:
        known = [(size, label, level) for size, label, level, _ in page if isinstance(size, float)]
        labels += [size for size, label, _ in known if label]
        plain = [(size, level) for size, label, level in known if not label]
        top = min((level for _, level in plain), default=0)
        if any(level != top for _, level in plain):
            sections += [size for size, level in plain if level == top]
            parts += [size for size, level in plain if level != top]
    parts += labels
    if len(sections) >= MIN_SAMPLES and len(parts) >= MIN_SAMPLES:
        if median(sections) - median(parts) >= MIN_GAP:
            return float(median(sections) + median(parts)) / 2
    if len(labels) >= MIN_SAMPLES:
        return float(median(labels)) + LABEL_MARGIN
    return None


@log_call
def ranks(measured: list[Measured], threshold: float | None, numbered: bool = False) -> list[int]:
    """How many levels below the section level each heading of one page goes: 0 or 1, or the
    depth of its own number minus one in a numbered book."""
    top = min((level for _, label, level, _ in measured if not label), default=0)
    out = []
    for size, label, level, depth in measured:
        if numbered and isinstance(depth, int) and depth:
            out.append(min(depth - 1, MAX_DEPTH_RANK))
        elif label:
            out.append(PART)
        elif threshold is not None and isinstance(size, float):
            out.append(SECTION if size >= threshold else PART)
        else:
            # Without a measured size only the page itself can say which heading is the larger.
            out.append(SECTION if level == top else PART)
    return out


def apply_ranks(
    lines: list[str], entries: list[tuple[int, int, str]], ranking: list[int], section_level: int
) -> list[str]:
    """Rewrite the heading lines: sections at `section_level`, parts one level deeper."""
    out = list(lines)
    for (index, _, text), rank in zip(entries, ranking, strict=True):
        out[index] = "#" * (section_level + rank) + " " + text
    return out
