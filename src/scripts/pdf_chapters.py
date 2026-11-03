"""Recover a book's chapters from the running heads printed at the top of its pages.

A scanned book usually has no outline, but its chapter title is repeated at the top of every
other page. Those heads, found in the embedded text layer, give the chapter list and the page
where each chapter opens; the extractor then writes one chapter heading per chapter instead of
trusting each page's own, inconsistent heading guesses.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

if __package__:
    from .script_logging import log_call
else:
    from script_logging import log_call


LOGGER = logging.getLogger(__name__)
# A head sits in the first lines of a page, below any OCR noise.
HEAD_LINES = 5
HEAD_AREA = 0.4
# The opening page shows the title in the upper part, below some ornaments.
OPENER_AREA = 0.7
# A head spanning this share of the document is the author or book title, not a chapter.
GLOBAL_SPAN = 0.8
GLOBAL_MIN_PAGES = 5
# A chapter opens on one of the few pages before its first running head.
OPENER_LOOKBACK = 5
MIN_TITLE_OVERLAP = 0.5
# Two heads of one chapter share most words; OCR drops or truncates some.
SAME_HEAD = 0.6
# A chapter's head can be missing for many pages (illustrations, entries that open mid-page).
RUN_GAP = 40
MIN_CHAPTERS = 2
# Running heads exist only if some run of them is long: titles of chapters and sections that
# stand at the top of a page occur once each and must not be mistaken for them.
STRONG_RUN = 4
LONG_WORD = 5
LEADING_LINES = 8
MAX_LEVEL = 6

HEADING = re.compile(r"^(#{1,5})(?=\s)")
HEADING_MARKS = re.compile(r"^#+\s*")
TOKEN = re.compile(r"(?:[^\W\d_]+(?:[-'][^\W\d_]+)*[:;,.?!]*|[:;,.?!]+)")


# Words of a line without case, diacritics, digits or punctuation, so OCR spelling noise matches.
def _words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return re.sub(r"[^A-Z ]", " ", plain.upper()).split()


# The layer's own reading order is reliable where a sort by position is not on a tilted scan;
# only the top of the page is read, which is where heads and chapter titles are.
def _top_lines(page: pymupdf.Page, limit: int | None, share: float) -> list[str]:
    area = pymupdf.Rect(0, 0, page.rect.width, page.rect.height * share)
    return [line.strip() for line in page.get_text(clip=area).splitlines() if line.strip()][:limit]


# OCR noise and page numbers share lines with a head; only word-like tokens are kept.
def _clean(line: str) -> str:
    return " ".join(token for token in line.split() if TOKEN.fullmatch(token))


# The head is the run of upper-case lines at the top; page numbers, ornaments and OCR noise
# before it are skipped and the first line of ordinary text after it ends it.
def _head(lines: list[str]) -> str:
    parts: list[str] = []
    for line in map(_clean, lines):
        letters = [char for char in line if char.isalpha()]
        if len(letters) >= 3 and sum(char.isupper() for char in letters) / len(letters) >= 0.9:
            parts.append(line)
        elif parts and letters:
            break
    return re.sub(r"\s+([?!:;,.])", r"\1", " ".join(parts)).strip()


# OCR noise on ornaments and contents pages comes out as upper-case letter runs without vowels.
def _reads_as_text(head: str) -> bool:
    return all(re.search(r"[AEIOUY]", word) for word in _words(head) if len(word) >= 3)


# One head is the same as another when one contains the other or they share most words.
def _same(first: frozenset[str], second: frozenset[str]) -> bool:
    small, large = sorted((first, second), key=len)
    if len(small) >= 2 and small <= large:
        return True
    return len(first & second) / len(first | second) >= SAME_HEAD


@dataclass(slots=True)
class _Run:
    """Pages whose running heads agree, with the spellings seen on them."""

    pages: list[int]
    variants: Counter[frozenset[str]]

    # The commonest wording is the title; heads that add a guide word still contain it.
    @property
    def core(self) -> frozenset[str]:
        return self.variants.most_common(1)[0][0]

    # Chapters follow one another, so two runs that share pages are two streams of heads on the
    # same pages (a part and, on the facing pages, a chapter or an article); the one with fewer
    # head pages is the subordinate.
    def outweighs(self, other: _Run) -> bool:
        return (
            self.pages[0] <= other.pages[-1]
            and other.pages[0] <= self.pages[-1]
            and len(self.pages) > len(other.pages)
        )


@dataclass(frozen=True, slots=True)
class Chapter:
    title: str
    opener: int


@dataclass(frozen=True, slots=True)
class Structure:
    chapters: tuple[Chapter, ...]
    # Words of every running head: lines made only of them at a page top are not body text.
    vocabulary: frozenset[str]

    def opens(self, number: int) -> bool:
        return any(chapter.opener == number for chapter in self.chapters)

    @log_call
    def arrange(self, number: int, markdown: str) -> str:
        """Drop the page's own head and title lines, open its chapter, and nest other headings."""
        chapter = next((item for item in self.chapters if item.opener == number), None)
        lines = self._without_heads(markdown.splitlines(), chapter)
        lines = [HEADING.sub(lambda m: (m.group(1) + "#")[:MAX_LEVEL], line) for line in lines]
        if chapter is not None:
            lines = [f"## {chapter.title}", ""] + lines
        return "\n".join(lines).strip("\n")

    # Only the first lines are inspected; a line that mixes in other words is body text.
    def _without_heads(self, lines: list[str], chapter: Chapter | None) -> list[str]:
        title = _words(chapter.title) if chapter else []
        kept = list(lines)
        index = inspected = 0
        while index < len(kept) and inspected < LEADING_LINES:
            text = HEADING_MARKS.sub("", kept[index]).strip()
            if not text:
                index += 1
                continue
            inspected += 1
            words = _words(text)
            if not re.search(r"[^\W\d_]", text):
                del kept[index]  # a page number or an ornament
            elif (
                words
                and all(word in self.vocabulary for word in words)
                and any(len(word) >= LONG_WORD for word in words)
            ):
                del kept[index]
            elif title and words[: len(title)] == title and len(words) > len(title):
                # A subtitle printed under the chapter title keeps its own line.
                kept[index] = "## " + " ".join(text.split()[len(title) :])
                index += 1
            else:
                break
        return kept


# The opening page carries the title in large type, so it is the page just before the first
# running head whose top lines share the most words with the title.
def _opener(document: pymupdf.Document, first: int, title: str) -> int:
    wanted = frozenset(_words(title))
    for number in range(max(1, first - OPENER_LOOKBACK), first + 1):
        page = document[number - 1]
        # A page headed by another chapter's title is that chapter's last page.
        head = frozenset(_words(_head(_top_lines(page, HEAD_LINES, HEAD_AREA))))
        if head and not _same(head, wanted):
            continue
        top = set(_words(" ".join(_top_lines(page, None, OPENER_AREA))))
        # The opening page precedes the running heads, so the earliest page that shows the
        # title wins even when OCR dropped a word of it.
        if wanted and len(wanted & top) / len(wanted) >= MIN_TITLE_OVERLAP:
            return number
    return first


# Heads of the book title repeat across the whole document, so they are told apart from
# chapter heads by how far apart their pages are.
def _global_heads(
    pages_by_words: dict[frozenset[str], list[int]], total: int
) -> set[frozenset[str]]:
    return {
        words
        for words, pages in pages_by_words.items()
        if len(pages) >= GLOBAL_MIN_PAGES and (pages[-1] - pages[0] + 1) / total >= GLOBAL_SPAN
    }


@log_call
def find_structure(document: pymupdf.Document) -> Structure | None:
    """Chapters and their opening pages, or None when the pages show no running heads."""
    heads: dict[int, str] = {}
    for number in range(1, len(document) + 1):
        head = _head(_top_lines(document[number - 1], HEAD_LINES, HEAD_AREA))
        if sum(len(word) for word in _words(head)) >= LONG_WORD and _reads_as_text(head):
            heads[number] = head
    pages_by_words: dict[frozenset[str], list[int]] = {}
    for number, head in heads.items():
        pages_by_words.setdefault(frozenset(_words(head)), []).append(number)
    book_heads = _global_heads(pages_by_words, len(document))
    # Chapter heads in page order. Two streams can alternate on facing pages (the part title on
    # one side, a chapter or an article on the other), so a head joins the most recent run it
    # agrees with, not only the run of the page before.
    runs: list[_Run] = []
    for number in sorted(heads):
        words = frozenset(_words(heads[number]))
        if any(_same(words, book) for book in book_heads):
            continue
        run = next(
            (r for r in reversed(runs) if number - r.pages[-1] <= RUN_GAP and _same(words, r.core)),
            None,
        )
        if run is None:
            runs.append(_Run([number], Counter({words: 1})))
        else:
            run.pages.append(number)
            run.variants[words] += 1
    candidates: list[tuple[_Run, str, int]] = []
    for run in runs:
        # The running head repeats on most pages of the chapter, so the commonest spelling wins
        # over the one-off variants of the opening page and of OCR.
        title = Counter(heads[number] for number in run.pages).most_common(1)[0][0]
        opener = _opener(document, run.pages[0], title)
        # A single upper-case line may just be a section heading; a short chapter is real only
        # when an earlier page opens it by showing the same title.
        if len(run.pages) < 2 and opener >= run.pages[0]:
            continue
        candidates.append((run, title, opener))
    chapters: list[Chapter] = []
    vocabulary = {word for book in book_heads for word in book}
    kept: list[_Run] = []
    for run, title, opener in sorted(candidates, key=lambda item: item[2]):
        # A run that shares pages with a larger one is an article or a sub-chapter under it: its
        # own headings come from the pages, and it must not split the chapter around it.
        if any(other is not run and other.outweighs(run) for other, _, _ in candidates):
            continue
        if chapters and opener == chapters[-1].opener and len(run.pages) > len(kept[-1].pages):
            # Two titles share the opening page: the one with more head pages is the chapter.
            chapters[-1], kept[-1] = Chapter(title, opener), run
        elif not chapters or opener > chapters[-1].opener:
            chapters.append(Chapter(title, opener))
            kept.append(run)
    for run in kept:
        vocabulary |= run.core
    if len(chapters) < MIN_CHAPTERS or sum(len(r.pages) >= STRONG_RUN for r in kept) < MIN_CHAPTERS:
        return None
    LOGGER.info("Capitole detectate din antetele curente: %s", len(chapters))
    return Structure(tuple(chapters), frozenset(vocabulary))
