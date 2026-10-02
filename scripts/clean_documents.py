#!/usr/bin/env python3
"""Rewrite Markdown source files in place so that the fragments sent to the AI
carry as few characters (and tokens) as possible without losing medical
information.

Two families of rules run, in this order:

1. **The original rules** — strip the leading PDF-extraction metadata block
   (source_path, source_sha256, page_count, ...) with the repeated title and
   scaffold headings, external link destinations, e-mail addresses, phone
   numbers and the contact label a removed number leaves behind ("tel.",
   "mobil:"), "### Pagina N" and "<!-- Pagina PDF N -->" page markers,
   "[Nu a fost extras text din această pagină.]" placeholders, e-book
   "< previous page page_N next page >" navigation lines, empty "<!-- -->" HTML
   blocks, invisible characters, legacy cedillas (ş/ţ -> ș/ț) and
   "Vezi și"/"vezi si" cross-references.

   Phone numbers are matched by shape, not by label: a run of digits with phone
   separators is removed only when it looks like a national (0...) or
   international (+... / 00...) number, or when the line itself announces
   contact data. A number followed by a unit ("500 mg"), a thousands-separated
   quantity ("4.200.000", "150.000-300.000"), a date and an ISBN are never
   treated as a phone number.

2. **The compaction rules** — optionally fold Romanian diacritics to ASCII
   (currently OFF, see FOLD_DIACRITICS_BY_DEFAULT), then drop page
   furniture that carries no medical content: contents/index/glossary/
   bibliography sections (only when their title is unambiguous, they sit where
   such a section belongs and they actually look like a list of entries), book
   colophon lines, lines that hold nothing but a page number, contact details
   (e-mail addresses and phone numbers) and the running header — a line that
   repeats the document's own title. Repetition alone is deliberately not
   enough: this corpus repeats a template subheading for every entry
   ("Side Effects and Contraindications"), a table header on every page and even
   whole sentences, and dropping those destroys content.

Diacritics are folded *first*, before repeated lines are counted: folding makes
lines that differed only by diacritics identical, so counting before folding
would need a second pass to reach a fixed point. Running the script twice
changes nothing (verified on the whole corpus).

Every rule is deterministic and content-blind: no rule rewrites a sentence, and
**no rule may drop a number**. That last guarantee is enforced, not assumed —
``check_digit_invariant()`` requires every number present before cleaning to
still be present afterwards or to sit inside a span a whitelisted rule removed
(link destinations, page furniture, dropped sections). A file whose numbers do
not add up is left untouched, reported, and the run exits non-zero. This is what
protects doses, quantities and units ("500 mg", "3 lingurițe", "10 picături").

Line numbers shift for every file that loses lines; the changed bytes make the
next reindex re-process exactly those files, so no separate version bump is
needed. Sources stay the single input of the hybrid index: the indexer and the
Retriever never clean anything themselves.

Only a file whose content actually changes is rewritten. A rewritten file's
line endings are normalized to bare "\\n" in the process (CRLF and lone CR both
become LF) and its original encoding is kept when the result still fits in it.
"""
from __future__ import annotations

import argparse
import codecs
import collections
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_FALLBACK_ENCODINGS = ("utf-8", "utf-16", "cp1250", "cp1252")

# ---- Shared constants for the compaction rules ----

# Headings are the fragmentation boundaries (see ai/fragmenter.py): no rule may
# remove one except together with a whole furniture section it belongs to.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# A section whose heading names it as page furniture. The section is dropped
# only if every condition in is_furniture_section() also holds.
_TOC_HEADING_RE = re.compile(r"^#{1,6}\s*(?:cuprins|cuprinsul|sumar|table of contents|con[țt]inut)\b", re.IGNORECASE)
_INDEX_HEADING_RE = re.compile(r"^#{1,6}\s*(?:index|index alfabetic|glosar|glossary|abrevieri)\b", re.IGNORECASE)
_BIBLIOGRAPHY_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:bibliografie|bibliography|referin[țt]e|references|note bibliografice|"
    r"surse bibliografice|lecturi recomandate)\b",
    re.IGNORECASE,
)
# A heading that promises more than a contents list or a reference list
# ("Referințe și anexe") introduces real content and is never treated as
# furniture. Bare "Surse" is deliberately absent from the bibliography pattern:
# in this corpus "## Surse" lists the food sources of a nutrient.
_MIXED_HEADING_RE = re.compile(r"\b(?:si|și|and|plus|cuprinde)\b|&|\+|anex", re.IGNORECASE)

# An index/glossary/bibliography belongs at the end of a document; a dictionary
# entry that happens to be titled "Index" does not.
_TAIL_RATIO = 0.8
# A contents/index/reference section is mostly short entry lines ending in a page
# number or dot leaders — never continuous prose.
_MIN_ENTRY_DENSITY = 0.30
_ENTRY_END_RE = re.compile(r"(?:\d{1,4}|\.{3,}\s*\d*)\s*$")

# A dosage is a number with a unit. Such text is never treated as furniture and
# never removed as a repeated line.
_DOSAGE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|ml|kg|pic[ăa]turi|lingur(?:i[țt]e?|ă|i)|"
    r"capsule|comprimate|doze|ui|iu)\b",
    re.IGNORECASE,
)

# Colophon / front-matter credit lines. Both patterns are anchored at the start
# of the line and use word boundaries: a colophon line begins with the credit
# word ("Editura Litera", "Publicat de ...", "© 2015 ..."), while a line that
# merely contains one of these words is content — "carbohidratii sa fie
# distribuiti" is not a distribution credit, and "1. Banu C. ..., Editura
# Tehnica" is a bibliography entry. The positional restriction (first
# FRONT_MATTER_LINES lines) is a second guard.
_STRONG_CREDIT_RE = re.compile(
    r"^\s*(?:©|\(c\)\s*\d{4}|isbn|issn|descrierea cip|toate drepturile|"
    r"all rights reserved|tehnoredactare|corector|copert[ăa]|redactor|"
    r"traducere|traduc[ăa]tor|tip[ăa]rit|drepturi de autor|edi[țt]ia a)",
    re.IGNORECASE,
)
_FRONT_CREDIT_RE = re.compile(
    r"^\s*(?:\beditura\b|\bpublicat[ăa]?\s+(?:de|la|prin)\b|\bdistribuit\b|www\.|https?://|"
    r"[\w.+-]+\\?@[\w-]+|\bcopyright\b|orice reproducere|referen[țt]i de specialitate|"
    r"editor:|prepress)",
    re.IGNORECASE,
)
_FRONT_MATTER_LINES = 300
_MAX_CREDIT_LINE_CHARS = 200

# Roman numerals up to XXXIX: enough for the front matter of these documents and
# — unlike a bare [ivxlcdm]+ class — it cannot match a word such as "civil" or
# "mix". The lookahead keeps it from matching the empty string.
_ROMAN_PAGE = r"(?=[ivx])x{0,3}(?:ix|iv|v?i{0,3})"

# A line holding nothing but a page number: "12", "- 12 -", "pagina 12",
# "pag. 12", "page 104", "Page 104 of 350", "Page iv" or a roman numeral. The
# "Page N" forms stay behind as plain lines in PDFs whose extractor kept the page
# label — strip_page_markers() only knows the "# Page N" and "<!-- Page N -->"
# spellings.
_PAGE_NUMBER_ONLY_RE = re.compile(
    r"^\s*(?:[-–—]?\s*\d{1,4}\s*[-–—]?"
    r"|pag(?:ina)?\.?\s*\d+"
    r"|page(?:[ \t]+pdf)?[ \t]*[:.\-–—]?[ \t]*(?:\d{1,4}|" + _ROMAN_PAGE + r")"
    r"(?:[ \t]*(?:din|of|/)[ \t]*\d{1,4})?\.?"
    r"|" + _ROMAN_PAGE + r")\s*$",
    re.IGNORECASE,
)

# Running headers repeat the book title on every page; the title match (see
# strip_repeated_lines) is what tells them apart from repeated content.
_REPEATED_MIN_OCCURRENCES = 5

# Romanian diacritics and the legacy forms the extractors emit, folded to ASCII
# so the payload tokenizes more cheaply. This does not affect condition
# matching: the dictionary is written without diacritics and both matching and
# lexical search already normalize through plain()/unaccent().
_DIACRITICS_TABLE = str.maketrans(
    "ăâîșțĂÂÎȘȚşţŞŢãÃ", "aaistAAISTstSTaA"
)

# TEMPORARY SWITCH: diacritics folding is OFF while the sources are being
# tested. Set this back to True (or pass --fold-diacritics) to re-enable it; no
# other rule depends on it either way.
FOLD_DIACRITICS_BY_DEFAULT = False

# A number, as compared by the digit invariant.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# ---- Contact details (e-mail addresses and phone numbers) ----

# A line that announces contact data ("tel. 021 319 6390", "mobil: 0745 ...").
# Word boundaries are essential: without them "Eritrocitele" and "Suplimentele"
# match "tel" and turn a medical line into a contact line.
_CONTACT_LABEL_RE = re.compile(
    r"\b(?:tel|telefon|telefonul|telefoane|fax|telex|mobil|mobile|gsm|whatsapp|viber|"
    r"contact|contacta[țt]i|sun[ăa]|suna[țt]i|apel|apela[țt]i)\b[.:]?",
    re.IGNORECASE,
)
# A phone-shaped run: digits with the separators phone numbers use, optionally
# introduced by "+", "(" or the OCR stand-in letter "o" for a leading zero
# ("Tel o21 242 14 46"). Whether it really is a phone number is decided by
# _looks_like_phone(), which rejects quantities, dates and ISBNs.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\w])(?:\+?[0oO(]?\d[\d \t.\-/()\u00a0]{6,}\d)(?![\w])")
# "500 mg", "3 lingurițe", "10 ani" — a number followed by a unit is a dose or a
# duration, never a phone number.
_UNIT_TAIL_RE = re.compile(
    r"^[ \t]*(?:mg|mcg|µg|ug|ml|kg|g|ui|iu|%|lei|ani|zile|luni|s[ăa]pt[ăa]m[âa]ni|ore|minute|"
    r"lingur\w*|pic[ăa]turi|capsule|comprimate|doze|calorii)\b",
    re.IGNORECASE,
)
_UNIT_HEAD_RE = re.compile(
    r"(?:\b(?:mg|mcg|µg|ug|ml|kg|g|ui|iu|ani|zile|luni|lingur\w*|pic[ăa]turi|capsule|comprimate)|%)"
    r"[ \t]*$",
    re.IGNORECASE,
)
# "4.200.000", "150 000" — thousands separators are a quantity, not a phone.
_THOUSANDS_RE = re.compile(r"\d{1,3}(?:[.\u00a0][ \t]?\d{3})+")
_ISBN_RE = re.compile(r"97[89]\d{9}[\dX]")
_LEADING_DATE_RE = re.compile(r"^\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}(?!\d)")
# The shapes a phone number really has: a national number starts with 0, an
# international one with "+" or "00", and both are groups of 2-4 digits.
_NATIONAL_PHONE_RE = re.compile(r"^0\d{2,3}(?:[ .\-/()]{0,2}\d{2,4}){1,4}$")
_INTERNATIONAL_PHONE_RE = re.compile(r"^(?:\+|00)[ .\-]?\d{1,3}(?:[ .\-/()]{0,2}\d{2,4}){2,5}$")
# ".../1998" at the end is a journal or edition reference, not a phone number.
_YEAR_TAIL_RE = re.compile(r"/(?:19|20)\d{2}$")
# North-American toll-free numbers, the only unlabelled shape without a leading 0.
_TOLL_FREE_RE = re.compile(r"1[ .\-]?8(?:00|33|44|55|66|77|88)[ .\-]?\d{3}[ .\-]?\d{4}")
# A phone number has at least this many digits. On a contact line a 7-digit
# number is a local number ("Contact ... at 477-6019"), but only without a
# slash: "100/1998" is a code.
_MIN_PHONE_DIGITS = 9
_MIN_LABELLED_PHONE_DIGITS = 7
_MAX_PHONE_DIGITS = 15
# Two or more separators with nothing between them, left behind by a removal.
_SEPARATOR_RUN_RE = re.compile(r"(?:[ \t]*[,;]){2,}")
# A space left in front of the punctuation that closes the sentence around a
# removed number ("... sau ." -> "... sau.").
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"[ \t]+([.,;:!?])")


@dataclass(frozen=True)
class Removed:
    """One span a whitelisted rule removed, kept for the digit invariant."""

    rule: str
    text: str


class DigitInvariantError(RuntimeError):
    """A rule would have dropped a number no whitelisted removal accounts for."""

    def __init__(self, violations: list[tuple[str, list[str]]]) -> None:
        self.violations = violations
        files = ", ".join(relative for relative, _ in violations[:5])
        super().__init__(f"digit invariant violated in {len(violations)} file(s): {files}")


# ---- Newline-preserving text cleaning ----
# Every substitution below must never add or remove a newline character.

# [etichetă](url) -> etichetă. Restricted to a single line: a link split
# across lines is rare in this corpus and not worth risking a newline match.
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]*)\]\(([^()\n]+)\)")

# <a href="...">etichetă</a> -> etichetă.
_HTML_ANCHOR_RE = re.compile(r"<a\b[^>\n]*>([^<\n]*)</a>", re.IGNORECASE)

# A line containing a "see also" reference is dropped in its entirety (the
# newline itself is kept). Restricted to lines that actually contain the
# trigger phrase: a reference wrapped across several lines (common in
# PDF-extracted books) only has the line with "Vezi și"/"vezi si" removed —
# the wrapped continuation on following lines is left behind as a residual
# fragment. Accepted as a known v1 limitation rather than risk merging or
# dropping unrelated lines.
_VEZI_SI_LINE_RE = re.compile(r"(?m)^.*\b[Vv]ezi\s+(?:și|si)\b.*$")

# Any remaining bare URL not part of a Markdown/HTML link, including
# scheme-less "www." addresses, and e-mail addresses. PDF extraction sometimes
# escapes the at sign ("dspivak\@post-trib.com"), so the backslash is allowed.
_BARE_URL_RE = re.compile(r"(?:https?://|\bwww\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+\\?@[\w-]+(?:\.[\w-]+)+")

# Extraction artefacts: soft hyphen, zero-width characters, BOM and C0 control
# characters (never newline or tab) are dropped; NBSP becomes a plain space.
_INVISIBLE_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRANSLATION = str.maketrans({
    "\u00a0": " ",
    # Legacy cedilla forms -> the comma-below letters used in Romanian.
    "\u015f": "\u0219", "\u015e": "\u0218", "\u0163": "\u021b", "\u0162": "\u021a",
    # Typographic ligatures.
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
})

# Collapse runs of spaces/tabs left behind by the removals above, and trim
# trailing whitespace before a newline. Neither touches "\n" itself.
_INLINE_GAPS_RE = re.compile(r"[ \t]{2,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+(?=\n)")


def clean_text(text: str) -> str:
    """Remove external link destinations, e-mail addresses, "see also"
    cross-references and extraction artefacts from ``text`` while preserving
    every newline (and therefore every line number) it contains."""
    cleaned = _INVISIBLE_RE.sub("", text).translate(_TRANSLATION)
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = _HTML_ANCHOR_RE.sub(r"\1", cleaned)
    cleaned = _VEZI_SI_LINE_RE.sub("", cleaned)
    cleaned = _BARE_URL_RE.sub("", cleaned)
    cleaned = _EMAIL_RE.sub("", cleaned)
    cleaned = _INLINE_GAPS_RE.sub(" ", cleaned)
    cleaned = _TRAILING_SPACE_RE.sub("", cleaned)
    return cleaned


# ---- File-level cleaning ----


# Decode a Markdown file with the same encoding fallbacks build_hybrid_index.py
# uses, then normalize line endings to bare "\n" — writing raw bytes back out
# below skips Python's own text-mode newline translation, so this is the only
# place CRLF/CR get collapsed.
def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        decoded, encoding = raw.decode("utf-8-sig"), "utf-8-sig"
    else:
        decoded, encoding = None, None
        for candidate in _FALLBACK_ENCODINGS:
            try:
                decoded, encoding = raw.decode(candidate), candidate
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded, encoding = raw.decode("utf-8", errors="replace"), "utf-8"
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, encoding


_SCAFFOLD_HEADING_RE = re.compile(r"## (?:Pagini|Text nativ|Text extras|Con\w+ extras|Text OCR extras)")
_OCR_NOTE_RE = re.compile(r"Textul este rezultatul OCR local\b.*")


def _drop_blank_head(lines: list[str]) -> None:
    while lines and not lines[0].strip():
        lines.pop(0)


# The extractor writes "# <file name>" with or without the source extension
# (e.g. "# x.pdf" for x.pdf.md, "# x" for x.docx.md). Only such a line is a
# generated title; any other first heading is real content. With no stem
# (file name unknown) any "# " heading is accepted.
def _is_file_title(line: str, stem: str | None) -> bool:
    if not line.startswith("# "):
        return False
    if stem is None:
        return True
    title = " ".join(line[2:].split()).casefold()
    name = " ".join(stem.split()).casefold().replace(" .", ".")
    return title == name or name.startswith(title + ".")


# The OCR output ends with a "## Notă" section holding the OCR disclaimer.
def _drop_ocr_note(lines: list[str]) -> None:
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and _OCR_NOTE_RE.fullmatch(lines[-1].strip()):
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].startswith("## Not"):
            lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()


# Drop what the extraction scripts prepend to every converted document: the
# leading "---" ... "---" metadata block (recognised by its source_path key, so
# unrelated frontmatter is never touched), the "# file.ext" title that repeats
# the file name, the "## Pagini"/"## Text extras"/... scaffold heading, the trailing OCR
# disclaimer and the ```text fence around OCR output. Unlike clean_text(), this
# removes lines.
def strip_extraction_metadata(text: str, stem: str | None = None) -> str:
    if not text.startswith("---\n"):
        return text
    lines = text.split("\n")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return text
    if not any(line.startswith(("source_path:", "source_relative_path:")) for line in lines[1:end]):
        return text
    rest = lines[end + 1:]
    _drop_blank_head(rest)
    if rest and _is_file_title(rest[0], stem):
        rest.pop(0)
        _drop_blank_head(rest)
    if rest and _SCAFFOLD_HEADING_RE.fullmatch(rest[0].strip()):
        rest.pop(0)
        _drop_blank_head(rest)
    _drop_ocr_note(rest)
    if rest and rest[0].strip() == "```text":
        closing = next((i for i in range(len(rest) - 1, 0, -1) if rest[i].strip()), None)
        if closing is not None and rest[closing].strip() == "```":
            del rest[closing]
            rest.pop(0)
            _drop_blank_head(rest)
    return "\n".join(rest) + "\n" if rest else ""


_PAGE_LABEL = r"(?:pagina|page)(?:[ \t]+pdf)?[ \t]+\d+(?:[ \t]+(?:din|of)[ \t]+\d+)?"
_PAGE_MARKER_RE = re.compile(
    rf"(?:#{{1,6}}[ \t]*{_PAGE_LABEL}|<!--[ \t]*{_PAGE_LABEL}[ \t]*-->)[ \t]*",
    re.IGNORECASE,
)

# E-book navigation lines: "< previous page page_109 next page >" (page id may
# be roman, the trailing "next page >" may be cut off) and "cover next page >".
_EBOOK_NAV_RE = re.compile(
    r"(?:<[ 	]*previous page[ 	]+page_\w+(?:[ 	]+next page[ 	]*>)?"
    r"|cover[ 	]+next page[ 	]*>)[ 	]*",
    re.IGNORECASE,
)

# Pandoc's empty raw-HTML block ("```{=html}" / "<!-- -->" / "```", used to
# separate adjacent lists/quotes) and the bare "<!-- -->" comment it contains.
_EMPTY_HTML_BLOCK_RE = re.compile(r"(?m)^```\{=html\}[ \t]*\n<!--[ \t]*-->[ \t]*\n```[ \t]*$")
_EMPTY_COMMENT_RE = re.compile(r"<!--[ \t]*-->[ \t]*")

# Whole-line placeholders the extractors emit for a page/slide without text:
# "[Nu a fost extras text din această pagină.]" (or "...acest diapozitiv.") and
# "[Nu a fost recuperat text OCR cu încredere suficientă.]".
_EMPTY_PLACEHOLDER_RE = re.compile(
    r"\[[ \t]*Nu a fost (?:extras|recuperat) text\b[^\]\n]*\][ \t]*", re.IGNORECASE,
)


# Remove the generated "### Pagina 8" heading lines, "<!-- Pagina PDF 8 -->"
# comment lines, e-book "< previous page page_N next page >" navigation lines, empty pandoc
# HTML blocks and empty-page placeholder lines, plus the blank line that
# would otherwise be left doubled up where one sat between paragraphs.
# Removes lines, like strip_extraction_metadata().
def strip_page_markers(text: str) -> str:
    kept: list[str] = []
    skip_blank = False
    for line in _EMPTY_HTML_BLOCK_RE.sub("<!-- -->", text).split("\n"):
        if (
            _PAGE_MARKER_RE.fullmatch(line)
            or _EBOOK_NAV_RE.fullmatch(line)
            or _EMPTY_COMMENT_RE.fullmatch(line)
            or _EMPTY_PLACEHOLDER_RE.fullmatch(line)
        ):
            skip_blank = not kept or not kept[-1].strip()
            continue
        if skip_blank and not line.strip():
            continue
        skip_blank = False
        kept.append(line)
    return "\n".join(kept)


_BLANK_RUN_RE = re.compile(r"\n(?:[ \t]*\n){2,}")


# Keep at most one blank line in a row: a blank line directly followed by
# another blank line is dropped. Runs last, so it also squeezes the gaps left
# by every removal above. Removes lines, like strip_extraction_metadata().
def collapse_blank_lines(text: str) -> str:
    return _BLANK_RUN_RE.sub("\n\n", text)


# ---- Compaction rules ----

# Fold Romanian diacritics (and the legacy cedilla forms) to ASCII. Character
# count is unchanged; UTF-8 byte count and token count both drop, because
# ș/ț/ă/â/î take two bytes each and ASCII tokenizes more efficiently.
def fold_diacritics(text: str) -> str:
    return text.translate(_DIACRITICS_TABLE)


# Index of the first line after the section that starts at `start` and whose
# heading has `level` hashes (i.e. the next heading of the same or a higher
# level), or len(lines) when the section runs to the end of the document.
def section_end(lines: Sequence[str], start: int, level: int) -> int:
    index = start + 1
    while index < len(lines):
        match = _HEADING_RE.match(lines[index])
        if match and len(match.group(1)) <= level:
            return index
        index += 1
    return index


# Which kind of page furniture a heading announces, or None when it announces
# content.
def furniture_kind(line: str) -> str | None:
    if _TOC_HEADING_RE.match(line):
        return "toc"
    if _INDEX_HEADING_RE.match(line):
        return "index_glossary"
    if _BIBLIOGRAPHY_HEADING_RE.match(line):
        return "bibliography"
    return None


def entry_density(lines: Sequence[str]) -> float:
    """Share of non-blank lines that end like a contents/reference entry."""
    content = [line.strip() for line in lines if line.strip()]
    if not content:
        return 0.0
    entries = sum(1 for line in content if _ENTRY_END_RE.search(line))
    return entries / len(content)


# A heading that names page furniture still introduces content sometimes
# (this corpus has "## REFERINȚE ȘI ANEXE" full of crystal descriptions, "##
# Surse" listing the food sources of a nutrient, and a dictionary entry titled
# "## INDEX"). A section is dropped only when its title is unambiguous, it sits
# where such a section belongs, it looks like a list of entries and it carries
# no dosage. position_ratio is the character position of the heading relative
# to the whole document.
def is_furniture_section(lines: Sequence[str], position_ratio: float, kind: str) -> bool:
    block = "\n".join(lines)
    if len(block) <= 120 or _DOSAGE_RE.search(block):
        return False
    if kind in {"index_glossary", "bibliography"} and position_ratio < _TAIL_RATIO:
        return False
    return entry_density(lines) >= _MIN_ENTRY_DENSITY


# Drop contents/index/glossary/bibliography sections that pass
# is_furniture_section(), together with every heading inside them.
def strip_furniture_sections(text: str) -> tuple[str, list[Removed]]:
    lines = text.split("\n")
    total_chars = max(len(text), 1)
    kept: list[str] = []
    removed: list[Removed] = []
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = _HEADING_RE.match(line)
        kind = furniture_kind(line) if heading else None
        if kind is not None and not _MIXED_HEADING_RE.search(heading.group(2)):
            end = section_end(lines, index, len(heading.group(1)))
            block = lines[index:end]
            if is_furniture_section(block, offset / total_chars, kind):
                removed.append(Removed(f"furniture:{kind}", "\n".join(block)))
                offset += sum(len(item) + 1 for item in block)
                index = end
                continue
        kept.append(line)
        offset += len(line) + 1
        index += 1
    return "\n".join(kept), removed


# Drop colophon/credit lines (copyright, ISBN, publisher, translators,
# reviewers, prepress). Anchored at the start of the line, only in the front
# matter, and never a long line: a content sentence or a bibliography entry that
# merely mentions the publisher must survive.
def strip_colophon_lines(
    lines: Sequence[str], *, front_matter_lines: int = _FRONT_MATTER_LINES
) -> tuple[list[str], list[Removed]]:
    kept: list[str] = []
    removed: list[Removed] = []
    for index, line in enumerate(lines):
        is_credit = _STRONG_CREDIT_RE.match(line) or (
            index < front_matter_lines and _FRONT_CREDIT_RE.match(line)
        )
        if is_credit and len(line.strip()) < _MAX_CREDIT_LINE_CHARS:
            removed.append(Removed("colophon", line))
            continue
        kept.append(line)
    return kept, removed


# Drop lines that hold nothing but a page number.
def strip_page_number_lines(lines: Sequence[str]) -> tuple[list[str], list[Removed]]:
    kept: list[str] = []
    removed: list[Removed] = []
    for line in lines:
        if _PAGE_NUMBER_ONLY_RE.match(line):
            removed.append(Removed("page_number_line", line))
            continue
        kept.append(line)
    return kept, removed


# A line that repeats the running header of a page — the document's own title
# reprinted on every page. Repetition alone is *not* evidence of page furniture:
# books in this corpus repeat a template subheading for every entry ("Side
# Effects and Contraindications", "Preparation and Dosage"), a table header on
# every page ("SUPLIMENT DOZĂ RECOMANDATĂ OBSERVAȚII") and even whole sentences
# ("sfert din cantitatea recomandată."). Dropping those destroys content, so a
# repeated line is removed only when it repeats the document's title.
def _title_key(value: str) -> str:
    """Comparable form of a title: no extension, punctuation, case or spacing."""
    value = re.sub(r"\.(?:pdf|docx?|gdoc|txt|rtf|odt|pptx|xlsx|md|jpe?g|png)$", "", value.strip(), flags=re.IGNORECASE)
    return " ".join(re.findall(r"[^\W_]+", value.casefold().translate(_DIACRITICS_TABLE), flags=re.UNICODE))


def _document_titles(text: str, stem: str | None) -> tuple[str, ...]:
    """Every spelling of the document's own title the running header may use."""
    titles: list[str] = []
    if stem:
        titles.append(stem)
    for match in re.finditer(r"(?m)^#\s+(.+)$", text):
        titles.append(match.group(1))
    return tuple(key for key in (_title_key(title) for title in titles) if key)


def _is_running_header(line: str, titles: Sequence[str]) -> bool:
    """A line that is (or is the title plus a page number) the document title."""
    key = _title_key(re.sub(r"[\s\-–—|:]*\d{1,4}\s*$", "", line))
    if not key:
        return False
    for title in titles:
        if key == title:
            return True
        # A page may print "Title - Author" where the file is named "Title", or
        # the other way round. Compare word runs, and only between strings long
        # enough to be a title: a one-letter file name would otherwise match any
        # line containing that letter.
        if len(title) >= 12 and len(key) >= 12 and (key in title or title in key):
            return True
    return False


def strip_repeated_lines(
    text: str,
    *,
    titles: Sequence[str] = (),
    min_occurrences: int = _REPEATED_MIN_OCCURRENCES,
) -> tuple[str, list[Removed]]:
    """Drop the document's own title where it repeats as a running page header.

    The title match is the whole evidence, so a short title counts too — but the
    line may be neither a Markdown heading (that is document structure) nor a
    line carrying a dosage.
    """
    lines = text.split("\n")
    counts = collections.Counter(line.strip() for line in lines if line.strip())
    kept: list[str] = []
    removed: list[Removed] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if (
            titles
            and counts[stripped] >= min_occurrences
            and _is_running_header(stripped, titles)
            and not _HEADING_RE.match(stripped)
            and not _DOSAGE_RE.search(stripped)
        ):
            if stripped in seen:
                removed.append(Removed("running_header", line))
                continue
            seen.add(stripped)
        kept.append(line)
    return "\n".join(kept), removed


# ---- Contact details ----

# The digits of a phone candidate, with the OCR stand-in letter "o" read as zero.
def _phone_digits(candidate: str) -> str:
    return re.sub(r"\D", "", candidate.replace("o", "0").replace("O", "0"))


# Decide whether a phone-shaped run really is a phone number. Conservative on
# purpose: a false positive deletes a dose, a quantity or a bibliographic
# reference, and the digit invariant cannot catch it because the removal is
# whitelisted.
def _looks_like_phone(candidate: str, *, labeled: bool, head: str, tail: str) -> bool:
    text = candidate.strip()
    digits = _phone_digits(text)
    minimum = _MIN_LABELLED_PHONE_DIGITS if labeled and "/" not in text else _MIN_PHONE_DIGITS
    if not minimum <= len(digits) <= _MAX_PHONE_DIGITS:
        return False
    # "000000000000" and friends are placeholders or DOI tails.
    if len(set(digits)) == 1:
        return False
    # A number glued to a unit is a dose or a duration, never contact data.
    if _UNIT_TAIL_RE.match(tail) or _UNIT_HEAD_RE.search(head):
        return False
    # Quantities with thousands separators ("4.200.000"), also as a range
    # ("150.000-300.000"), are statistics.
    if _THOUSANDS_RE.fullmatch(text):
        return False
    if "-" in text and _THOUSANDS_RE.search(text):
        return False
    if _ISBN_RE.fullmatch(re.sub(r"[ \t-]", "", text)):
        return False
    if _LEADING_DATE_RE.match(text):
        return False
    # "Genome Biology 3(12):0079.1-0079.14" and "100/1998" are references.
    if _YEAR_TAIL_RE.search(text):
        return False
    if _NATIONAL_PHONE_RE.match(text) or _INTERNATIONAL_PHONE_RE.match(text):
        return True
    if _TOLL_FREE_RE.fullmatch(text):
        return True
    if labeled:
        # A contact line may hold a number whose grouping is unusual: an OCR
        # reading ("Tel o21 242 14 46"), a pair of numbers ("tel. 2100082/2103470")
        # or a bracketed one ("tel. (0264/538769"). The guards above already
        # rejected quantities, dates, ISBNs, DOIs and journal references.
        return True
    return False


# A contact label is removed only where it introduces or follows a removed
# number ("tel. 021...", "021... (tel)"). The same words appear inside ordinary
# sentences ("sau suna la tel. ...", "Contact Diane ... at 477-6019"), and
# deleting them there would change the meaning of the sentence.
_LABEL_GAP_RE = re.compile(r"^[ \t.,:;\-–—()/]{0,4}$")


def _attached_label_spans(
    line: str, phone_spans: Sequence[tuple[int, int]]
) -> list[tuple[int, int, str]]:
    attached: list[tuple[int, int, str]] = []
    for match in _CONTACT_LABEL_RE.finditer(line):
        for start, end in phone_spans:
            before = match.end() <= start and _LABEL_GAP_RE.fullmatch(line[match.end():start])
            after = end <= match.start() and _LABEL_GAP_RE.fullmatch(line[end:match.start()])
            if before or after:
                attached.append((match.start(), match.end(), "phone_label"))
                break
    return attached


# Delete phone numbers, and the contact label glued to a removed number
# ("tel.", "mobil:"). A line that held nothing else disappears entirely. Only the
# spans a rule actually removed are recorded, so the digit invariant still sees
# every number that vanished.
def strip_contact_details(text: str) -> tuple[str, list[Removed]]:
    kept: list[str] = []
    removed: list[Removed] = []
    for line in text.split("\n"):
        if not _PHONE_CANDIDATE_RE.search(line):
            kept.append(line)
            continue

        labeled = bool(_CONTACT_LABEL_RE.search(line))
        phone_spans: list[tuple[int, int, str]] = []
        for match in _PHONE_CANDIDATE_RE.finditer(line):
            candidate = match.group(0)
            if _looks_like_phone(
                candidate, labeled=labeled, head=line[:match.start()], tail=line[match.end():]
            ):
                phone_spans.append((match.start(), match.end(), "phone_number"))
        if not phone_spans:
            kept.append(line)
            continue

        spans = sorted(phone_spans + _attached_label_spans(line, [(s, e) for s, e, _ in phone_spans]))
        pieces: list[str] = []
        line_removals: list[Removed] = []
        last = 0
        for start, end, rule in spans:
            pieces.append(line[last:start])
            line_removals.append(Removed(rule, line[start:end]))
            last = end
        pieces.append(line[last:])

        cleaned = _TRAILING_SPACE_RE.sub(
            "",
            _SPACE_BEFORE_PUNCTUATION_RE.sub(
                r"\1", _INLINE_GAPS_RE.sub(" ", _SEPARATOR_RUN_RE.sub(",", "".join(pieces)))
            ),
        )
        removed.extend(line_removals)
        if any(character.isalnum() for character in cleaned):
            kept.append(cleaned)
        else:
            removed.append(Removed("empty_contact_line", cleaned))
    return "\n".join(kept), removed


# ---- The digit invariant ----

# Every number of a text, as a multiset.
def numbers(text: str) -> collections.Counter[str]:
    return collections.Counter(_NUMBER_RE.findall(text))


# Removals that consist of whole lines dropped by a stage that only ever deletes
# lines (strip_extraction_metadata, strip_page_markers, the "Vezi și" rule).
# Comparing the line multisets before/after attributes each dropped line to the
# stage that dropped it, without changing those functions' signatures.
def _line_drop_removals(before: str, after: str, rule: str) -> list[Removed]:
    dropped = collections.Counter(before.split("\n")) - collections.Counter(after.split("\n"))
    return [Removed(rule, line) for line, count in dropped.items() for _ in range(count)]


# Inline pieces clean_text() deletes from a line that itself survives: the
# destination of a Markdown/HTML link, a bare URL, an e-mail address. Only these
# can carry a number (".../capitolul-12").
def _inline_link_removals(text: str) -> list[Removed]:
    removed: list[Removed] = []
    for match in _MARKDOWN_LINK_RE.finditer(text):
        removed.append(Removed("link_destination", match.group(2)))
    for pattern in (_HTML_ANCHOR_RE, _BARE_URL_RE):
        for match in pattern.finditer(text):
            removed.append(Removed("link_destination", match.group(0)))
    for match in _EMAIL_RE.finditer(text):
        removed.append(Removed("email", match.group(0)))
    return removed


# The numbers that may legitimately be missing because a whitelisted rule
# removed the text carrying them.
def accounted_numbers(removals: Sequence[Removed]) -> collections.Counter[str]:
    accounted: collections.Counter[str] = collections.Counter()
    for removal in removals:
        accounted.update(_NUMBER_RE.findall(removal.text))
    return accounted


# Numbers present before cleaning that are neither present after it nor covered
# by a whitelisted removal. An empty list means no dose or quantity was lost.
def check_digit_invariant(before: str, after: str, removals: Sequence[Removed]) -> list[str]:
    accounted = accounted_numbers(removals)
    missing = numbers(before) - numbers(after)
    return sorted(number for number, count in missing.items() if accounted[number] < count)


# ---- The pipeline ----

# Run every rule over one document, in order, and return the compacted text
# together with every span the rules removed (for the digit invariant and the
# end-of-run summary). `stem` lets strip_extraction_metadata() recognise the
# generated "# file.ext" title.
def compact_document(
    text: str, *, stem: str | None = None, fold_diacritics_to_ascii: bool = FOLD_DIACRITICS_BY_DEFAULT
) -> tuple[str, list[Removed]]:
    removals: list[Removed] = []
    # Taken from the raw text: the "# file.ext" title is itself stripped later.
    titles = _document_titles(text, stem)

    without_metadata = strip_extraction_metadata(text, stem)
    removals += _line_drop_removals(text, without_metadata, "extraction_metadata")

    without_markers = strip_page_markers(without_metadata)
    removals += _line_drop_removals(without_metadata, without_markers, "page_marker")

    without_links = clean_text(without_markers)
    # Lines clean_text() dropped (a "Vezi și" line) or rewrote in place (a link,
    # an e-mail address, a run of spaces). Reported as one rule: it is an upper
    # bound of what that stage removed, which is all the digit invariant needs.
    removals += _line_drop_removals(without_markers, without_links, "inline_cleanup")
    removals += _inline_link_removals(without_markers)

    without_contacts, contact_removals = strip_contact_details(without_links)
    removals += contact_removals

    # Folding comes before the repeated-line count: folding can turn two lines
    # that differed only by diacritics into the same line, and counting first
    # would leave that duplicate for a second run to find.
    staged = fold_diacritics(without_contacts) if fold_diacritics_to_ascii else without_contacts

    staged, furniture = strip_furniture_sections(staged)
    removals += furniture

    lines, colophon = strip_colophon_lines(staged.split("\n"))
    removals += colophon
    lines, page_numbers = strip_page_number_lines(lines)
    removals += page_numbers
    staged, repeated = strip_repeated_lines("\n".join(lines), titles=titles)
    removals += repeated

    return collapse_blank_lines(staged), removals


# Describe what a run removed, one line per rule.
def _format_rule_totals(removed_by_rule: collections.Counter[str]) -> str:
    return " | ".join(f"{rule} {_format_int(chars)}" for rule, chars in removed_by_rule.most_common())


def _format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _write(path: Path, cleaned: str, encoding: str) -> None:
    # write_bytes(), not write_text(): the latter would re-apply platform
    # newline translation on top of the "\n"-only text _read() already produced,
    # corrupting line endings on Windows.
    try:
        payload = cleaned.encode(encoding)
    except UnicodeEncodeError:
        # e.g. cp1250 has no comma-below ș/ț: the file becomes UTF-8.
        payload = cleaned.encode("utf-8")
    path.write_bytes(payload)


def clean_documents(
    source: Path,
    *,
    dry_run: bool,
    fold_diacritics_to_ascii: bool = FOLD_DIACRITICS_BY_DEFAULT,
) -> int:
    """Compact every Markdown file under ``source`` in place.

    Returns the number of files that changed. Raises DigitInvariantError when a
    file would have lost a number no whitelisted rule accounts for; that file is
    left untouched and the run keeps going, so the remaining files are still
    compacted.
    """
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    paths = sorted(
        (path for path in source.rglob("*.md") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    changed = 0
    violations: list[tuple[str, list[str]]] = []
    removed_by_rule: collections.Counter[str] = collections.Counter()
    characters_before = 0
    characters_after = 0

    for path in paths:
        decoded, encoding = _read(path)
        cleaned, removals = compact_document(
            decoded, stem=path.stem, fold_diacritics_to_ascii=fold_diacritics_to_ascii
        )
        missing = check_digit_invariant(decoded, cleaned, removals)
        if missing:
            relative = path.relative_to(source).as_posix()
            violations.append((relative, missing))
            print(f"Skipped, digit invariant: {relative} (missing {', '.join(missing)})", flush=True)
            continue
        if cleaned == decoded:
            continue

        changed += 1
        characters_before += len(decoded)
        characters_after += len(cleaned)
        for removal in removals:
            removed_by_rule[removal.rule] += len(removal.text) + 1

        relative = path.relative_to(source).as_posix()
        print(f"{'Would clean' if dry_run else 'Cleaning'}: {relative}", flush=True)
        if not dry_run:
            _write(path, cleaned, encoding)

    verb = "Would rewrite" if dry_run else "Rewrote"
    print(f"{verb} {changed}/{len(paths)} files", flush=True)
    noun = "file" if changed == 1 else "files"
    scope = f"{noun} that would change" if dry_run else f"{noun} changed"
    print(
        f"Characters {_format_int(characters_before)} -> {_format_int(characters_after)} "
        f"({_format_int(characters_before - characters_after)} fewer) over {changed} {scope}",
        flush=True,
    )
    print(
        f"Removed by rule: {_format_rule_totals(removed_by_rule) or 'nothing to remove'}",
        flush=True,
    )
    print(
        f"Diacritics: {'folded to ASCII' if fold_diacritics_to_ascii else 'kept'}; "
        f"digit-invariant violations: {len(violations)}",
        flush=True,
    )
    if violations:
        raise DigitInvariantError(violations)
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact the Markdown sources under data/documents in place.",
    )
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files that would change without writing them",
    )
    parser.add_argument(
        "--fold-diacritics", action="store_true",
        help="Fold Romanian diacritics to ASCII (currently off by default)",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        clean_documents(
            arguments.source,
            dry_run=arguments.dry_run,
            fold_diacritics_to_ascii=arguments.fold_diacritics,
        )
    except DigitInvariantError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
