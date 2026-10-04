"""Splits one document into fragments, each with a business category and the
medical conditions (data/medical_conditions.txt) it is about. How relevant a
fragment is to a search (its priority) is decided at search time, not here (see
ai/search.py).

A chapter is a Markdown heading (page markers such as "Pagina 3" are not
headings). Neither the file name nor the folders are compared with the
conditions. Steps, in this order:

1. R1 - a heading whose own title names a condition. Headings are visited from
   the deepest up, so a sub-chapter is always its own fragment and its parent
   keeps only what is left of its subtree. The fragment starts with the
   heading itself, without the headings of its ancestors. A heading left with
   no text produces no fragment.
2. The lines of the R1 fragments are excluded from what follows.
3. R2 - among the remaining headings, one whose own text (up to the next
   heading of any level) mentions a condition. The fragment is the heading and
   that text; several conditions in one section make one fragment.
4. R1 and R2 fragments get primary_conditions (the conditions of their title)
   and secondary_conditions (those of their text, title excluded).
5. The lines of the R2 fragments are excluded from what follows.
6. D1 - the remaining text (also text that sits under no heading, and whole
   documents without headings), one continuous stretch at a time, is cut into
   pieces of about D1_TARGET_CHARS with at most D1_MAX_OVERLAP_CHARS shared
   between consecutive pieces. D1 fragments have no conditions.

R1 and R2 fragments have no size limit. `path` is the chain of headings down to
the fragment's own heading ("Carte > Plante > Musetel") and is metadata only: it
is never used to find conditions and is not part of the fragment text."""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from enum import StrEnum

from backend.ai.conditions import Condition, ConditionDictionary, load_dictionary

# D1 pieces aim for this many characters...
D1_TARGET_CHARS = 1800
# ...and are cut at the best boundary between these two sizes.
D1_MIN_CHARS = 1500
D1_MAX_CHARS = 2100
# Consecutive D1 pieces share at most this many characters.
D1_MAX_OVERLAP_CHARS = 270
# A cut never leaves less new text than this for the next piece.
D1_MIN_TAIL_CHARS = 300

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_PAGE_HEADING_RE = re.compile(r"(?:pagina|page)\s+\d+(?:\s+(?:din|of)\s+\d+)?", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?…][\"'”’)\]]*(?=\s|$)")
_PARAGRAPH_RE = re.compile(r"\n[ \t]*\n\s*")
_NEWLINE_RE = re.compile(r"\n")
_SPACE_RE = re.compile(r" ")


class BusinessCategory(StrEnum):
    R1 = "R1"  # the title of the chapter names a condition
    R2 = "R2"  # the text of the chapter mentions a condition
    D1 = "D1"  # everything else


@dataclass(frozen=True)
class Fragment:
    text: str
    line_start: int  # 1-based, inclusive
    line_end: int
    path: str  # chain of headings ("Carte > Gripa"), "" when there is none
    business_category: BusinessCategory
    primary_conditions: tuple[str, ...] = ()  # conditions named in the fragment's title
    secondary_conditions: tuple[str, ...] = ()  # conditions named in its text, title excluded


@dataclass(frozen=True)
class _Heading:
    line: int  # 0-based index into the document's lines
    level: int
    title: str
    raw: str
    ancestors: tuple[int, ...]  # indexes into the headings list, outermost first
    subtree_end: int  # first line index after this heading's whole subtree
    body_end: int  # first line index after this heading's own text (next heading of any level)


# Lines with their 1-based numbers; lines that were dropped (page markers) leave gaps.
_Span = list[tuple[int, str]]


def _is_page_marker(title: str) -> bool:
    return bool(_PAGE_HEADING_RE.fullmatch(title.strip()))


def _is_page_marker_line(line: str) -> bool:
    match = _HEADING_RE.match(line)
    return bool(match and _is_page_marker(match.group(2)))


# Headings of the document, skipping generated page markers ("Pagina 3").
def _parse_headings(lines: list[str]) -> list[_Heading]:
    found: list[tuple[int, int, str, str]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and not _is_page_marker(match.group(2)):
            found.append((index, len(match.group(1)), match.group(2).strip(), line.strip()))

    headings: list[_Heading] = []
    stack: list[int] = []  # indexes of the currently open headings
    for position, (index, level, title, raw) in enumerate(found):
        while stack and found[stack[-1]][1] >= level:
            stack.pop()
        subtree_end = len(lines)
        for later_index, later_level, _, _ in found[position + 1:]:
            if later_level <= level:
                subtree_end = later_index
                break
        body_end = found[position + 1][0] if position + 1 < len(found) else len(lines)
        headings.append(_Heading(index, level, title, raw, tuple(stack), subtree_end, body_end))
        stack.append(position)
    return headings


# Numbered lines at the given indexes, without the page markers.
def _numbered(lines: list[str], indexes: list[int]) -> _Span:
    return [(index + 1, lines[index]) for index in indexes if not _is_page_marker_line(lines[index])]


# The span without the blank lines at both ends, as (text, first line, last line);
# None when nothing is left.
def _trimmed(span: _Span) -> tuple[str, int, int] | None:
    filled = [position for position, (_, line) in enumerate(span) if line.strip()]
    if not filled:
        return None
    kept = span[filled[0]:filled[-1] + 1]
    return "\n".join(line for _, line in kept).strip(), kept[0][0], kept[-1][0]


def _names(conditions: list[Condition]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(condition.name for condition in conditions))


# Cut positions of `pattern` (the index right after each match) inside [low, high].
def _cut_candidates(pattern: re.Pattern[str], text: str, low: int, high: int) -> list[int]:
    found: list[int] = []
    for match in pattern.finditer(text, max(0, low - 8)):
        if match.end() > high:
            break
        if match.end() >= low:
            found.append(match.end())
    return found


# Where the D1 piece starting at `start` ends: the boundary closest to the target
# size inside [D1_MIN_CHARS, D1_MAX_CHARS], preferring a paragraph break, then a
# sentence end, a line break and a space; a hard cut when there is none. It always
# leaves at least D1_MIN_TAIL_CHARS of text for the rest.
def _d1_cut(text: str, start: int, remaining: int) -> int:
    low = start + D1_MIN_CHARS
    high = start + min(D1_MAX_CHARS, remaining - D1_MIN_TAIL_CHARS)
    target = start + D1_TARGET_CHARS
    for pattern in (_PARAGRAPH_RE, _SENTENCE_END_RE, _NEWLINE_RE, _SPACE_RE):
        candidates = _cut_candidates(pattern, text, low, high)
        if candidates:
            return min(candidates, key=lambda position: abs(position - target))
    return high


# Where the piece after a cut at `cut` begins: the start of the earliest sentence
# within the last D1_MAX_OVERLAP_CHARS before the cut, otherwise the earliest line
# start there, otherwise the earliest word start, otherwise the cut itself (no
# overlap).
def _d1_next_start(text: str, cut: int) -> int:
    window_start = max(0, cut - D1_MAX_OVERLAP_CHARS)
    for match in _SENTENCE_END_RE.finditer(text, window_start, cut):
        position = match.end()
        while position < cut and text[position].isspace():
            position += 1
        if position < cut:
            return position
    for boundary in (r"\n", r"\s+"):
        for match in re.finditer(boundary, text[window_start:cut]):
            position = window_start + match.end()
            if position < cut:
                return position
    return cut


# Cut one continuous stretch of remaining text into D1 pieces, as
# (text, first line, last line).
def _d1_pieces(span: _Span) -> list[tuple[str, int, int]]:
    text = "\n".join(line for _, line in span)
    starts: list[int] = []
    offset = 0
    for _, line in span:
        starts.append(offset)
        offset += len(line) + 1

    def line_number(char_index: int) -> int:
        return span[bisect_right(starts, char_index) - 1][0]

    pieces: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        remaining = len(text) - start
        cut = len(text) if remaining <= D1_MAX_CHARS else _d1_cut(text, start, remaining)
        raw = text[start:cut]
        body = raw.strip()
        if body:
            first = start + (len(raw) - len(raw.lstrip()))
            pieces.append((body, line_number(first), line_number(first + len(body) - 1)))
        if cut >= len(text):
            break
        start = _d1_next_start(text, cut)
    return pieces


# Split one already-normalized document into R1, R2 and D1 fragments, in document order.
def fragment_document(text: str, dictionary: ConditionDictionary | None = None) -> list[Fragment]:
    dictionary = dictionary if dictionary is not None else load_dictionary()
    lines = text.split("\n")
    headings = _parse_headings(lines)
    heading_lines = {heading.line for heading in headings}
    consumed = [False] * len(lines)

    # A line that carries real text: not blank, not a heading, not a page marker.
    def is_text(index: int) -> bool:
        return (
            index not in heading_lines
            and bool(lines[index].strip())
            and not _is_page_marker_line(lines[index])
        )

    def path_of(position: int) -> str:
        heading = headings[position]
        return " > ".join(headings[i].title for i in (*heading.ancestors, position))

    def make(
        category: BusinessCategory, span: _Span, position: int, own_text: str | None = None,
    ) -> Fragment | None:
        trimmed = _trimmed(span)
        if trimmed is None:
            return None
        body, first, last = trimmed
        # Conditions of the text: everything but the fragment's own title line.
        if own_text is None:
            own_text = "\n".join(body.split("\n")[1:])
        return Fragment(
            body, first, last, path_of(position), category,
            primary_conditions=_names(dictionary.find(headings[position].title)),
            secondary_conditions=_names(dictionary.find(own_text)),
        )

    fragments: list[Fragment] = []

    # Steps 1-2: R1, the deepest headings first, so a parent keeps only what is left.
    by_depth = sorted(range(len(headings)), key=lambda i: (-len(headings[i].ancestors), headings[i].line))
    for position in by_depth:
        heading = headings[position]
        if not dictionary.find(heading.title):
            continue
        taken = [
            index for index in range(heading.line, heading.subtree_end) if not consumed[index]
        ]
        for index in taken:
            consumed[index] = True
        if not any(is_text(index) for index in taken):
            continue
        fragment = make(BusinessCategory.R1, _numbered(lines, taken), position)
        if fragment:
            fragments.append(fragment)

    # Steps 3-5: R2, the own text of each heading that is still free.
    for position, heading in enumerate(headings):
        if consumed[heading.line]:
            continue
        body_indexes = list(range(heading.line + 1, heading.body_end))
        body_span = _numbered(lines, body_indexes)
        own_text = "\n".join(line for _, line in body_span).strip()
        if not own_text or not dictionary.find(own_text):
            continue
        for index in (heading.line, *body_indexes):
            consumed[index] = True
        fragment = make(
            BusinessCategory.R2, _numbered(lines, [heading.line, *body_indexes]), position, own_text,
        )
        if fragment:
            fragments.append(fragment)

    # Step 6: D1, each continuous run of lines nobody took.
    heading_starts = [heading.line for heading in headings]
    run: list[int] = []
    for index in range(len(lines) + 1):
        if index < len(lines) and not consumed[index]:
            run.append(index)
            continue
        if any(is_text(i) for i in run):
            for body, first, last in _d1_pieces(_numbered(lines, run)):
                owner = bisect_right(heading_starts, first - 1) - 1
                fragments.append(Fragment(
                    body, first, last, path_of(owner) if owner >= 0 else "", BusinessCategory.D1,
                ))
        run = []

    fragments.sort(key=lambda fragment: (fragment.line_start, fragment.line_end))
    return fragments
