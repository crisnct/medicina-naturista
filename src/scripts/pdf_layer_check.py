"""Decide whether a scanned page's embedded text layer can stand for the page's text.

The layer of a scanned book is old OCR output: it can drop whole paragraphs or carry garbage
without any error, so it is only trusted after independent checks against the page image.
"""

from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
import pymupdf

if __package__:
    from .clean_documents import ENGLISH_HUNSPELL_DIR, HUNSPELL_DIR, build_dictionary, fold
    from .script_logging import log_call
else:
    from clean_documents import ENGLISH_HUNSPELL_DIR, HUNSPELL_DIR, build_dictionary, fold
    from script_logging import log_call


PREVIEW_DPI = 100
# Calibrated on a scanned Romanian book: a page whose layer dropped a paragraph left 0.17 of its
# ink without any text box, intact pages at most 0.06. Pages whose layer has several wrong or
# merged words measured 0.033-0.047 unknown words after joining hyphenated line ends; pages
# with a single slip, which the vision model matches, measured at most 0.025.
MAX_UNCOVERED_INK = 0.10
MAX_UNKNOWN_WORDS = 0.03
# Too few words make the unknown-word rate meaningless.
MIN_WORDS_FOR_RATE = 30
# Scanner borders and edge shadows are not page content.
MARGIN = 0.07

WORD = re.compile(r"[^\W\d_]{3,}")
HYPHEN_BREAK = re.compile(r"(\w)-\s+(\w)")
DICTIONARIES = {"ron": (HUNSPELL_DIR, "ro_RO"), "eng": (ENGLISH_HUNSPELL_DIR, "en_GB")}


# Only a lowercase continuation proves a word was split; "A- B" is a real dash or a list.
def _join_break(match: re.Match[str]) -> str:
    return match.group(1) + match.group(2) if match.group(2).islower() else match.group(0)


# Expanding Hunspell takes seconds, so it happens once per run and only for known languages.
@lru_cache(maxsize=2)
def known_words(language: str) -> set[str] | None:
    source = DICTIONARIES.get(language)
    if source is None:
        return None
    return build_dictionary(source[0], dictionary_name=source[1])[0]


# OCR noise on figures and tables shows up as symbol salad or runs of accented letters; real
# Latin-script words stay below these ratios.
def _garbled(token: str) -> bool:
    if len(token) < 6:
        return False
    symbols = sum(char in "%&$!?*#@~^=<>|\\[]{}" for char in token)
    accented = sum(char.isalpha() and not char.isascii() for char in token)
    return symbols >= 3 or (len(token) >= 8 and accented / len(token) > 0.6)


# Share of dark pixels that no text box of the layer covers: a missing paragraph is invisible
# to the layer itself, only the image still shows it.
def _uncovered_ink(page: pymupdf.Page, words: list) -> float:
    scale = PREVIEW_DPI / 72
    pixmap = page.get_pixmap(dpi=PREVIEW_DPI, colorspace=pymupdf.csGRAY)
    gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    ink = gray < 140
    covered = np.zeros_like(ink)
    for x0, y0, x1, y1, *_ in words:
        box = pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix
        covered[
            max(0, int(box.y0 * scale) - 3) : int(box.y1 * scale) + 4,
            max(0, int(box.x0 * scale) - 3) : int(box.x1 * scale) + 4,
        ] = True
    height, width = ink.shape
    inside = (slice(int(height * MARGIN), int(height * (1 - MARGIN))),) + (
        slice(int(width * MARGIN), int(width * (1 - MARGIN))),
    )
    total = int(ink[inside].sum())
    return float((ink[inside] & ~covered[inside]).sum() / total) if total else 0.0


@log_call
def layer_problems(page: pymupdf.Page, language: str) -> list[str]:
    """Reasons the embedded text must not be used for this page; empty when it can be."""
    words = page.get_text("words")
    if not words:
        return ["no text layer"]
    problems = []
    ink = _uncovered_ink(page, words)
    if ink > MAX_UNCOVERED_INK:
        problems.append(f"uncovered ink {ink:.2f}")
    text = HYPHEN_BREAK.sub(_join_break, page.get_text())
    garbled = sum(_garbled(token) for token in text.split())
    if garbled:
        problems.append(f"{garbled} garbled tokens")
    known = known_words(language)
    if known is not None:
        # Capitalised words are mostly names the dictionary does not list.
        tokens = [word for word in WORD.findall(text) if not word[0].isupper()]
        if len(tokens) >= MIN_WORDS_FOR_RATE:
            rate = sum(fold(word) not in known for word in tokens) / len(tokens)
            if rate > MAX_UNKNOWN_WORDS:
                problems.append(f"unknown words {rate:.2f}")
    return problems
