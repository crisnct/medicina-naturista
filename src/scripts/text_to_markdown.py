"""Convert a plain-text file (e.g. extracted from a book PDF) to Markdown with headings.

The structure is guessed from the text alone, so the result is a first draft:

- "Partea ...", "Capitolul ..." lines become "# " headings;
- short ALL-CAPS lines become "## " headings;
- other short lines that look like titles (no final punctuation, followed by a
  running paragraph) become "### " headings;
- lines broken by the page layout are re-joined into paragraphs, hyphenated words
  ("alimen-" + "tele") are glued back, and bare page numbers are dropped;
- bullet lines ("-", "•", "*") become Markdown list items;
- table-of-contents lines with dotted leaders ("Titlu ......... 12") are kept as
  plain list items instead of being mistaken for headings.

Usage:
    python scripts/text_to_markdown.py input.txt                 # writes input.md
    python scripts/text_to_markdown.py input.txt -o out.md
    python scripts/text_to_markdown.py input.txt --max-heading 70 --no-toc
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PART_RE = re.compile(r"^(partea|capitolul|capitol|secțiunea|sectiunea|anexa)\b", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:pagina\s+)?\d{1,4}\s*$", re.IGNORECASE)
TOC_LINE_RE = re.compile(r"^.{2,}?\s*(?:\.{3,}|(?:\.\s){3,}|…{2,}).*\d+\s*$")
BULLET_RE = re.compile(r"^\s*[-•*▪●]\s+(.*)$")
SENTENCE_END = (".", "!", "?", ":", ";", "”", "\"", ")")
HEADING_END_BLOCKED = (",", ";", ":", "-", "–", "—")


def _is_all_caps(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _is_part_heading(line: str) -> bool:
    """"Partea întâi", "Capitolul 5" — short, without sentence punctuation."""
    return bool(PART_RE.match(line)) and len(line.split()) <= 3 and not re.search(r"[,.;:()]", line)


def _looks_like_heading(line: str, prev: str | None, nxt: str | None, max_len: int, full_line: int) -> bool:
    if not line or len(line) > max_len or line.endswith(HEADING_END_BLOCKED):
        return False
    # A line as long as the page's normal lines is a wrapped paragraph, not a title;
    # titles also carry no sentence punctuation inside them.
    if len(line) >= 0.7 * full_line or re.search(r"[,;?!]|\.\s", line):
        return False
    if line.endswith(".") and not _is_all_caps(line):
        return False
    if not line[0].isupper() and not line[0].isdigit():
        return False
    if BULLET_RE.match(line) or TOC_LINE_RE.match(line):
        return False
    # A title is followed by running text and preceded by the end of a paragraph.
    if nxt is None or len(nxt) <= len(line):
        return False
    return prev is None or prev == "" or prev.endswith(SENTENCE_END)


def _clean_lines(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return ["" if PAGE_NUMBER_RE.match(line) else line.strip() for line in lines]


def _join(paragraph: list[str]) -> str:
    out = ""
    for line in paragraph:
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line  # hyphenated word broken at the end of a line
        else:
            out = f"{out} {line}" if out else line
    return out


def _typical_line_length(lines: list[str]) -> int:
    lengths = sorted(len(line) for line in lines if len(line) > 30)
    return lengths[len(lengths) * 3 // 4] if lengths else 80  # upper quartile ~ a full line


def convert(text: str, max_heading: int = 60, keep_toc: bool = True) -> str:
    lines = _clean_lines(text)
    full_line = _typical_line_length(lines)
    # Short lines repeated on many pages are running page headers, not real titles.
    counts: dict[str, int] = {}
    for line in lines:
        if line and len(line) <= max_heading:
            counts[line.lower()] = counts.get(line.lower(), 0) + 1
    seen_headers: set[str] = set()
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(_join(paragraph))
            paragraph.clear()

    for index, line in enumerate(lines):
        if not line:
            flush()
            continue
        prev = paragraph[-1] if paragraph else ("" if index == 0 or not lines[index - 1] else lines[index - 1])
        nxt = next((candidate for candidate in lines[index + 1:] if candidate), None)

        if TOC_LINE_RE.match(line):
            flush()
            if keep_toc:
                title = re.sub(r"\s*(?:\.{3,}|(?:\.\s){3,}|…{2,}).*$", "", line).strip()
                page = re.search(r"(\d+)\s*$", line)
                blocks.append(f"- {title}" + (f" (p. {page.group(1)})" if page else ""))
            continue
        bullet = BULLET_RE.match(line)
        if bullet:
            flush()
            blocks.append(f"- {bullet.group(1)}")
            continue
        if _is_part_heading(line) or _looks_like_heading(line, prev, nxt, max_heading, full_line):
            flush()
            key = line.lower()
            if counts.get(key, 0) >= 3 and not _is_part_heading(line):
                if key in seen_headers:
                    continue  # repeated page header: keep only its first occurrence
                seen_headers.add(key)
            if _is_part_heading(line):
                blocks.append(f"# {line}")
            elif _is_all_caps(line):
                blocks.append(f"## {line.title()}")
            else:
                blocks.append(f"### {line}")
            continue
        paragraph.append(line)
    flush()

    # Consecutive list items stay tight; everything else is separated by a blank line.
    out: list[str] = []
    for block in blocks:
        if out and block.startswith("- ") and out[-1].startswith("- "):
            out[-1] += "\n" + block
        else:
            out.append(block)
    return "\n\n".join(out) + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="fișierul .txt de convertit")
    parser.add_argument("-o", "--output", type=Path, help="fișierul .md rezultat (implicit: același nume, extensia .md)")
    parser.add_argument("--max-heading", type=int, default=60, help="lungimea maximă a unui titlu, în caractere (implicit: 60)")
    parser.add_argument("--no-toc", action="store_true", help="elimină liniile de cuprins cu puncte de umplere")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Fișierul nu există: {args.input}")
    markdown = convert(args.input.read_text(encoding="utf-8"), args.max_heading, keep_toc=not args.no_toc)
    output = args.output or args.input.with_suffix(".md")
    output.write_text(markdown, encoding="utf-8")
    headings = sum(1 for line in markdown.splitlines() if line.startswith("#"))
    print(f"Scris: {output} ({headings} titluri)", file=sys.stderr)


if __name__ == "__main__":
    main()
