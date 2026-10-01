#!/usr/bin/env python3
"""Rewrite Markdown source files in place, stripping the leading PDF-extraction
metadata block (source_path, source_sha256, page_count, ...) with the
repeated title and scaffold headings, external link destinations, e-mail
addresses, "### Pagina N" and "<!-- Pagina PDF N -->" page markers,
"[Nu a fost extras text din această pagină.]" placeholders, e-book "< previous page page_N next page >" navigation lines, empty "<!-- -->" HTML blocks, invisible characters, legacy cedillas (ş/ţ -> ș/ț) and
"Vezi și"/"vezi si" cross-references. All cleaning rules live in this file.

Consecutive blank lines are collapsed into one.

Removing the metadata block, page markers and extra blank lines deletes lines,
so line numbers shift for those files; the changed bytes make the next reindex re-process them anyway.

Run this once (and again whenever new documents are added) before
rebuild_index.ps1: the hybrid index is built directly from already-clean
sources, so the indexer and Retriever never need to clean anything
themselves. clean_text() never removes a newline; and since a rewrite
changes each file's own bytes, the existing SHA-256-based incremental sync
picks up exactly the files this script touches on the next reindex — no
separate version bump is needed for the cleaning itself.

Only a file whose content actually changes is rewritten. A rewritten file's
line endings are normalized to bare "\\n" in the process (CRLF and lone CR
both become LF) — this changes the file's bytes but never its line count,
and matches how build_hybrid_index.py already normalizes line endings when
computing line numbers.
"""
from __future__ import annotations

import argparse
import codecs
import re
import sys
from pathlib import Path

_FALLBACK_ENCODINGS = ("utf-8", "utf-16", "cp1250", "cp1252")

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
# scheme-less "www." addresses, and e-mail addresses.
_BARE_URL_RE = re.compile(r"(?:https?://|\bwww\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

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


def clean_documents(source: Path, *, dry_run: bool) -> int:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")

    paths = sorted(
        (path for path in source.rglob("*.md") if path.is_file()),
        key=lambda item: item.relative_to(source).as_posix().casefold(),
    )
    changed = 0
    for path in paths:
        decoded, encoding = _read(path)
        cleaned = collapse_blank_lines(
            clean_text(strip_page_markers(strip_extraction_metadata(decoded, path.stem)))
        )
        if cleaned == decoded:
            continue
        changed += 1
        relative = path.relative_to(source).as_posix()
        print(f"{'Would clean' if dry_run else 'Cleaning'}: {relative}", flush=True)
        if not dry_run:
            # write_bytes(), not write_text(): the latter would re-apply
            # platform newline translation on top of the "\n"-only text
            # _read() already produced, corrupting line endings on Windows.
            try:
                payload = cleaned.encode(encoding)
            except UnicodeEncodeError:
                # e.g. cp1250 has no comma-below ș/ț: the file becomes UTF-8.
                payload = cleaned.encode("utf-8")
            path.write_bytes(payload)

    verb = "Would rewrite" if dry_run else "Rewrote"
    print(f"{verb} {changed}/{len(paths)} files", flush=True)
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path, default=project_root / "data" / "documents")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files that would change without writing them",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        clean_documents(arguments.source, dry_run=arguments.dry_run)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
