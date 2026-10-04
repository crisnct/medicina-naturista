#!/usr/bin/env python3
"""
Merge book PDF fragments in numeric book-page order.

Expected filenames:
    pag01-31.pdf
    pag32-53.pdf
    pag115-144.pdf
    ...

Behavior:
- reads PDF fragments from the folder passed as argument;
- extracts first/last book page from each filename;
- sorts numerically by the FIRST page number;
- reports missing page ranges but DOES NOT stop;
- stops on overlapping/invalid page ranges;
- optionally checks actual PDF page counts;
- saves the result in `<project>/data/documents` unless `--output-dir` is provided;
- the output filename is the source folder name + ".pdf".

Install:
    py -m pip install pypdf

Run:
    python scripts/merge_book_pdfs.py "C:\GoogleDrive\Medicina\_DeExtrasTextulCuAI\Vindecare prin nutritie"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter


FILE_PATTERN = re.compile(
    r"^pag(?P<first>\d+)-(?P<last>\d+)\.pdf$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PdfPart:
    path: Path
    first_page: int
    last_page: int

    @property
    def expected_page_count(self) -> int:
        return self.last_page - self.first_page + 1


def parse_pdf_part(path: Path) -> PdfPart | None:
    match = FILE_PATTERN.match(path.name)
    if not match:
        return None

    first_page = int(match.group("first"))
    last_page = int(match.group("last"))

    if first_page <= 0:
        raise ValueError(f"{path.name}: first page must be greater than 0.")

    if last_page < first_page:
        raise ValueError(
            f"{path.name}: invalid range {first_page}-{last_page}."
        )

    return PdfPart(
        path=path,
        first_page=first_page,
        last_page=last_page,
    )


def discover_parts(folder: Path) -> tuple[list[PdfPart], list[Path]]:
    parts: list[PdfPart] = []
    ignored: list[Path] = []

    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue

        part = parse_pdf_part(path)
        if part is None:
            ignored.append(path)
        else:
            parts.append(part)

    parts.sort(
        key=lambda part: (
            part.first_page,
            part.last_page,
            part.path.name.lower(),
        )
    )

    ignored.sort(key=lambda path: path.name.lower())

    return parts, ignored


def validate_ranges(parts: list[PdfPart]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    gaps: list[str] = []

    if not parts:
        return ["No matching PDF fragments were found."], gaps

    for previous, current in zip(parts, parts[1:]):
        expected_next = previous.last_page + 1

        if current.first_page > expected_next:
            gaps.append(
                f"Missing book pages {expected_next}-{current.first_page - 1} "
                f"between {previous.path.name} and {current.path.name}"
            )

        elif current.first_page < expected_next:
            errors.append(
                f"Overlapping page ranges: "
                f"{previous.path.name} ({previous.first_page}-{previous.last_page}) "
                f"and {current.path.name} "
                f"({current.first_page}-{current.last_page})"
            )

    return errors, gaps


def verify_pdf_page_counts(parts: list[PdfPart]) -> list[str]:
    warnings: list[str] = []

    for index, part in enumerate(parts, start=1):
        try:
            actual_count = len(PdfReader(str(part.path)).pages)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot read {part.path.name}: {exc}"
            ) from exc

        expected_count = part.expected_page_count

        print(
            f"[{index:02}/{len(parts):02}] checked "
            f"{part.path.name}: {actual_count} PDF pages"
        )

        if actual_count != expected_count:
            warnings.append(
                f"{part.path.name}: filename range "
                f"{part.first_page}-{part.last_page} implies "
                f"{expected_count} pages, but the PDF contains "
                f"{actual_count} pages."
            )

    return warnings


def merge_pdfs(parts: list[PdfPart], output_path: Path) -> None:
    writer = PdfWriter()

    try:
        for index, part in enumerate(parts, start=1):
            print(
                f"[{index:02}/{len(parts):02}] adding "
                f"{part.path.name} "
                f"(book pages {part.first_page}-{part.last_page})"
            )
            writer.append(str(part.path))

        # Create the configured output directory only when a merge is ready to be written.
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as output_file:
            writer.write(output_file)

    finally:
        writer.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge pag<first>-<last>.pdf files in numeric book-page order. "
            "The result is saved in data/documents by default, using the source "
            "folder name as the PDF filename."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing the PDF fragments.",
    )

    parser.add_argument(
        "--skip-page-count-check",
        action="store_true",
        help=(
            "Skip verification that the number of PDF pages matches "
            "the range encoded in the filename."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Destination folder. Defaults to <project>/data/documents.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    source_folder = args.folder.expanduser().resolve()

    if not source_folder.is_dir():
        print(
            f"ERROR: source folder does not exist:\n{source_folder}",
            file=sys.stderr,
        )
        return 2

    project_root = Path(__file__).resolve().parents[2]
    output_dir = (args.output_dir or project_root / "src" / "scripts").expanduser().resolve()
    output_filename = f"{source_folder.name}.pdf"
    output_path = output_dir / output_filename

    print(f"Project root  : {project_root}")
    print(f"Source folder : {source_folder}")
    print(f"Output PDF    : {output_path}")

    parts, ignored_pdfs = discover_parts(source_folder)

    if not parts:
        print(
            "\nERROR: no files matching pag<first>-<last>.pdf were found.",
            file=sys.stderr,
        )
        return 3

    print("\nOrder detected:")
    for part in parts:
        print(
            f"  {part.first_page:>4}-{part.last_page:<4} "
            f"{part.path.name}"
        )

    if ignored_pdfs:
        print(
            "\nPDF files ignored because their filenames do not match "
            "pag<first>-<last>.pdf:"
        )
        for path in ignored_pdfs:
            print(f"  - {path.name}")

    errors, gaps = validate_ranges(parts)

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)

        print("\nNothing was merged.", file=sys.stderr)
        return 4

    if gaps:
        print("\nPAGE GAPS DETECTED - merge will continue:")
        for gap in gaps:
            print(f"  - {gap}")

    if not args.skip_page_count_check:
        print("\nChecking PDF page counts...")
        warnings = verify_pdf_page_counts(parts)

        if warnings:
            print("\nPAGE COUNT WARNINGS - merge will continue:")
            for warning in warnings:
                print(f"  - {warning}")

    # Prevent accidental self-overwrite if the output path happens to match
    # one of the source PDFs.
    source_paths = {part.path.resolve() for part in parts}
    if output_path.resolve() in source_paths:
        print(
            "\nERROR: the output file is also one of the input files.",
            file=sys.stderr,
        )
        return 5

    print(f"\nMerging {len(parts)} PDFs...")
    merge_pdfs(parts, output_path)

    try:
        total_pages = len(PdfReader(str(output_path)).pages)
    except Exception as exc:
        print(
            f"\nERROR: merged PDF was written but could not be verified: {exc}",
            file=sys.stderr,
        )
        return 6

    print("\nDone.")
    print(f"Output      : {output_path}")
    print(f"Total pages : {total_pages}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
