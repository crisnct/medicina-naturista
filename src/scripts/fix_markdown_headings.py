r"""Repair the headings of a Markdown book made by extract_pdf_markdown.py, without any AI call.

It re-reads only the printed size of each heading from the source PDF's text layer and applies the
same rules as a new extraction: decorative `---` rules are dropped, text that was made a heading
although it is a paragraph becomes a paragraph again, and every heading below a chapter gets its
level from its printed size, so that parts such as "Preparare:" always sit under their section.
Chapters (`##`) and the book title are left as they are.

Apel:
    python src/scripts/fix_markdown_headings.py "carte.pdf.md" "carte.pdf"
Implicit rescrie fișierul Markdown; -o scrie într-un alt fișier. Păstrați o copie înainte.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

if __package__:
    from .pdf_headings import (
        RULE_LINE,
        apply_ranks,
        demote_run_in,
        drop_rules,
        heading_entries,
        measure_headings,
        numbered_book,
        ranks,
        section_size,
    )
    from .script_files import _commit_outputs, _remove_temp, _temporary_path
    from .script_logging import log_call
else:
    from pdf_headings import (
        RULE_LINE,
        apply_ranks,
        demote_run_in,
        drop_rules,
        heading_entries,
        measure_headings,
        numbered_book,
        ranks,
        section_size,
    )
    from script_files import _commit_outputs, _remove_temp, _temporary_path
    from script_logging import log_call


LOGGER = logging.getLogger(__name__)
PAGE_MARKER = re.compile(r"(<!-- Pagina PDF (\d+) -->)")
# Chapters are `##`; everything the model or the heuristics put below them starts at `###`.
FIRST_PART_LEVEL = 3


def _levels(text: str) -> Counter[int]:
    return Counter(
        len(m.group(1)) for line in text.splitlines() if (m := re.match(r"(#+)\s", line))
    )


@log_call
def fix_headings(markdown: str, document: pymupdf.Document) -> tuple[str, dict[str, object]]:
    """The repaired Markdown and a summary of what changed."""
    pieces = PAGE_MARKER.split(markdown)
    # pieces: head, marker, number, body, marker, number, body, ...
    head = pieces[0]
    pages: list[tuple[str, int, list[str]]] = []
    removed_rules = 0
    for index in range(1, len(pieces), 3):
        marker, number, body = pieces[index], int(pieces[index + 1]), pieces[index + 2]
        removed_rules += sum(bool(RULE_LINE.match(line)) for line in body.splitlines())
        text = demote_run_in(drop_rules(body.strip("\n")), FIRST_PART_LEVEL)
        pages.append((marker, number, text.splitlines()))
    entries = []
    measured = []
    for _marker, number, lines in pages:
        page_entries = heading_entries(lines, FIRST_PART_LEVEL)
        entries.append(page_entries)
        measured.append(
            measure_headings(document[number - 1], page_entries) if number <= len(document) else []
        )
    threshold = section_size(measured)
    numbered = numbered_book(measured)
    rebuilt = [head]
    for (marker, _number, lines), page_entries, page_measured in zip(
        pages, entries, measured, strict=True
    ):
        if page_entries and len(page_measured) == len(page_entries):
            lines = apply_ranks(
                lines, page_entries, ranks(page_measured, threshold, numbered), FIRST_PART_LEVEL
            )
        rebuilt += [marker, "\n\n" + "\n".join(lines) + "\n\n"]
    result = "".join(rebuilt).rstrip("\n") + "\n"
    summary = {
        "pages": len(pages),
        "section_heading_size": threshold,
        "numbered_headings": numbered,
        "rules_removed": removed_rules,
        "levels_before": dict(sorted(_levels(markdown).items())),
        "levels_after": dict(sorted(_levels(result).items())),
    }
    return result, summary


@log_call
def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Implicit: rescrie fișierul Markdown.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    output = (args.output or args.markdown).resolve()
    try:
        with pymupdf.open(args.pdf) as document:
            result, summary = fix_headings(args.markdown.read_text(encoding="utf-8"), document)
        staged = _temporary_path(output.parent)
        try:
            staged.write_text(result, encoding="utf-8", newline="\n")
            _commit_outputs({output: staged})
        finally:
            _remove_temp(staged)
    except (OSError, ValueError, RuntimeError) as exc:
        LOGGER.error("Repararea a eșuat: %s", exc)
        return 1
    print(f"Scris: {output}")
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv[1:] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(main())
