"""Splits one document into fragments, each tagged with a PRIORITY and the
medical conditions (data/medical_conditions.txt) it is about.

Criteria, applied in this order (a lower PRIORITY number ranks higher):

1. PRIORITY 1: the file or a folder name contains a condition -> the whole
   document is one fragment.
2. No real Markdown heading (page markers do not count) -> plain text,
   PRIORITY 5: one fragment up to PLAIN_CHUNK_CHARS, otherwise pieces of about
   that size that end at the first sentence end after it.
3. PRIORITY 1: a heading names a condition -> that heading and everything
   under it is one fragment whose path is the chain of headings down to it.
   Its lines are then taken out of play for the next criteria.
4. PRIORITY 3: in the remaining sections, one that mentions a condition in its
   own text -> one fragment made of the headings of all its ancestors, its own
   heading and its text (never the ancestors' introductions).
5. PRIORITY 5: whatever text is left, section by section, cut as in criterion 2.

Any fragment longer than MAX_FRAGMENT_CHARS is split further; the parts keep
the priority, conditions and path of the fragment they came from."""
from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import PurePosixPath

from medicina_naturista.ai.conditions import Condition, ConditionDictionary, load_dictionary

PRIORITY_DOCUMENT = 1
PRIORITY_SECTION = 3
PRIORITY_PLAIN = 5

# Plain text is cut into pieces of about this many characters, extended to the
# end of the sentence that crosses the limit.
PLAIN_CHUNK_CHARS = 3000
# Text without any sentence end (tables, lists) is cut at a line break before this.
PLAIN_HARD_CAP_CHARS = 4000
# No fragment is longer than this (headings prefix included).
MAX_FRAGMENT_CHARS = 8000

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_PAGE_HEADING_RE = re.compile(r"(?:pagina|page)\s+\d+(?:\s+(?:din|of)\s+\d+)?", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?…][\"'”’)\]]*(?=\s|$)")


@dataclass(frozen=True)
class Fragment:
    text: str
    line_start: int  # 1-based, inclusive
    line_end: int
    path: str  # chain of headings ("Carte > Gripa"), "" when there is none
    priority: int
    conditions: tuple[str, ...]  # canonical names of the conditions the fragment is about


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


# Numbered lines [start, end) without the page markers.
def _span(lines: list[str], start: int, end: int) -> _Span:
    span: _Span = []
    for index in range(start, end):
        match = _HEADING_RE.match(lines[index])
        if match and _is_page_marker(match.group(2)):
            continue
        span.append((index + 1, lines[index]))
    return span


# Last cut position <= `limit` that leaves a readable piece: paragraph break,
# then sentence end, then line break, then space; `limit` itself as a last resort.
def _cut_before(text: str, start: int, limit: int) -> int:
    window_end = start + limit
    floor = start + limit // 2
    paragraph = text.rfind("\n\n", floor, window_end)
    if paragraph >= 0:
        return paragraph + 2
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(text, floor, window_end)]
    if ends:
        return ends[-1]
    newline = text.rfind("\n", floor, window_end)
    if newline >= 0:
        return newline + 1
    space = text.rfind(" ", floor, window_end)
    return space + 1 if space >= 0 else window_end


# First cut position at or after `start + target` that ends a sentence, as long
# as it stays within `hard_cap`; otherwise a line break before the cap.
def _cut_after(text: str, start: int, target: int, hard_cap: int) -> int:
    match = _SENTENCE_END_RE.search(text, start + target - 1, start + hard_cap)
    if match:
        return match.end()
    newline = text.rfind("\n", start + target, start + hard_cap)
    return newline + 1 if newline >= 0 else start + hard_cap


# Cut a span into (text, first line, last line) pieces. "plain" mode makes
# pieces of about PLAIN_CHUNK_CHARS ending on a sentence end; the other mode
# only splits what is longer than `limit`.
def _pieces(span: _Span, *, plain_mode: bool, limit: int) -> list[tuple[str, int, int]]:
    if not span:
        return []
    text = "\n".join(line for _, line in span)
    starts: list[int] = []
    offset = 0
    for _, line in span:
        starts.append(offset)
        offset += len(line) + 1

    def line_number(char_index: int) -> int:
        return span[bisect_right(starts, char_index) - 1][0]

    pieces: list[tuple[str, int, int]] = []
    position = 0
    while position < len(text):
        remaining = len(text) - position
        if plain_mode and remaining > PLAIN_CHUNK_CHARS:
            cut = _cut_after(text, position, PLAIN_CHUNK_CHARS, PLAIN_HARD_CAP_CHARS)
        elif remaining > limit:
            cut = _cut_before(text, position, limit)
        else:
            cut = len(text)
        raw = text[position:cut]
        body = raw.strip()
        if body:
            first = position + (len(raw) - len(raw.lstrip()))
            pieces.append((body, line_number(first), line_number(first + len(body) - 1)))
        position = cut
    return pieces


# Fragments of one span: cut it (see _pieces), put `prefix` before every piece
# and enforce MAX_FRAGMENT_CHARS on the result.
def _fragments(
    span: _Span,
    *,
    prefix: str,
    path: str,
    priority: int,
    conditions: tuple[str, ...],
    plain_mode: bool,
    first_line: int | None = None,
) -> list[Fragment]:
    room = MAX_FRAGMENT_CHARS - (len(prefix) + 1 if prefix else 0)
    fragments: list[Fragment] = []
    for index, (body, start, end) in enumerate(_pieces(span, plain_mode=plain_mode, limit=room)):
        if index == 0 and first_line is not None:
            start = min(start, first_line)
        text = f"{prefix}\n{body}" if prefix else body
        fragments.append(Fragment(text, start, end, path, priority, conditions))
    return fragments


def _names(conditions: list[Condition]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(condition.name for condition in conditions))


# Extensions of the original file that survive in the Markdown file's name
# ("Constipatie rebela.rtf.md").
_SOURCE_EXTENSIONS = frozenset({".docx", ".doc", ".rtf", ".pdf", ".gdoc", ".odt", ".xlsx", ".pptx", ".txt"})


# The document's title: its file name without the .md and the original extension.
def _document_title(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    stem = path.stem
    while PurePosixPath(stem).suffix.lower() in _SOURCE_EXTENSIONS:
        stem = PurePosixPath(stem).stem
    return stem


# Split one already-normalized document into prioritised fragments.
# `relative_path` is the document's path below the source root (posix
# separators); its file and folder names are criterion 1.
def fragment_document(
    text: str,
    relative_path: str,
    dictionary: ConditionDictionary | None = None,
) -> list[Fragment]:
    dictionary = dictionary if dictionary is not None else load_dictionary()
    lines = text.split("\n")

    name_parts = PurePosixPath(relative_path).parts
    name_text = " / ".join((*name_parts[:-1], PurePosixPath(relative_path).stem))
    name_conditions = _names(dictionary.find(name_text))
    headings = _parse_headings(lines)

    # Criterion 1: the name says what the document is about. The document's
    # title stands in for the heading path, so the heading signal of the search
    # (ai/search.py) still sees the name that made this a priority-1 fragment.
    if name_conditions:
        return _fragments(
            _span(lines, 0, len(lines)), prefix="", path=_document_title(relative_path),
            priority=PRIORITY_DOCUMENT, conditions=name_conditions, plain_mode=False,
        )
    # Criterion 2: no structure to follow.
    if not headings:
        return _fragments(
            _span(lines, 0, len(lines)), prefix="", path="", priority=PRIORITY_PLAIN,
            conditions=(), plain_mode=True,
        )

    fragments: list[Fragment] = []
    consumed = [False] * len(lines)

    def path_of(position: int) -> str:
        heading = headings[position]
        return " > ".join(headings[i].title for i in (*heading.ancestors, position))

    # Criterion 3: a heading that names a condition takes its whole subtree.
    title_conditions = [dictionary.find(heading.title) for heading in headings]
    for position, heading in enumerate(headings):
        if consumed[heading.line] or not title_conditions[position]:
            continue
        inside = [
            i for i, other in enumerate(headings)
            if heading.line <= other.line < heading.subtree_end
        ]
        found = [condition for i in inside for condition in title_conditions[i]]
        fragments += _fragments(
            _span(lines, heading.line, heading.subtree_end), prefix="", path=path_of(position),
            priority=PRIORITY_DOCUMENT, conditions=_names(found), plain_mode=False,
        )
        for index in range(heading.line, heading.subtree_end):
            consumed[index] = True

    # Criteria 4 and 5: the own text of each section that is still free. The
    # text before the first heading is a section without a title.
    sections: list[tuple[int | None, int, int]] = []  # (heading position, first line, end line)
    if headings[0].line > 0:
        sections.append((None, 0, headings[0].line))
    for position, heading in enumerate(headings):
        sections.append((position, heading.line + 1, heading.body_end))

    for position, start, end in sections:
        heading_line = headings[position].line if position is not None else start
        if consumed[heading_line]:
            continue
        body = _span(lines, start, end)
        if not any(line.strip() for _, line in body):
            continue
        found = dictionary.find("\n".join(line for _, line in body))
        if position is None:
            prefix, path, first_line = "", "", None
        else:
            prefix = "\n".join(
                headings[i].raw for i in (*headings[position].ancestors, position)
            )
            path, first_line = path_of(position), headings[position].line + 1
        fragments += _fragments(
            body, prefix=prefix, path=path,
            priority=PRIORITY_SECTION if found else PRIORITY_PLAIN,
            conditions=_names(found), plain_mode=not found, first_line=first_line,
        )

    fragments.sort(key=lambda fragment: (fragment.line_start, fragment.line_end))
    return fragments
