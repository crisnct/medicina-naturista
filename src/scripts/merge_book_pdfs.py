#!/usr/bin/env python3
r"""
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
- checks actual page counts during the same read used for merging (unless skipped);
- merges and deskews pages in memory with PyMuPDF, preserving original PDF content;
- does not run OCR, launch external processes, or create intermediate page images;
- uses --deskew off to disable correction (does not perform OCR or orientation detection);
- saves the result in the project root unless `--output-dir` is provided;
- the output filename is the source folder name + ".pdf";
- use --debug for function-entry logs with named parameters (large objects summarized).

Install:
    py -m pip install -e ".[pdf]"

Run:
    python src/scripts/merge_book_pdfs.py "C:\GoogleDrive\Medicina\_DeExtrasTextulCuAI\Importanta plantelor in viata omului - prima mea carte de fitoterapie"
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sys
import time
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path

import pymupdf

if __package__:
    from .script_files import _commit_outputs, _remove_temp, _temporary_path
    from .script_logging import log_call
else:
    from script_files import _commit_outputs, _remove_temp, _temporary_path
    from script_logging import log_call

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PART_ORDER = attrgetter("first_page", "last_page", "path")

FILE_PATTERN = re.compile(
    r"^pag(?P<first>\d+)-(?P<last>\d+)\.pdf$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PdfPart:
    path: Path
    first_page: int
    last_page: int

    @log_call
    def __post_init__(self) -> None:
        if not all(
            isinstance(page, int) and not isinstance(page, bool)
            for page in (self.first_page, self.last_page)
        ):
            raise ValueError("Book page numbers must be integers.")
        if self.first_page < 1 or self.last_page < self.first_page:
            raise ValueError(f"{self.path}: invalid page range {self.first_page}-{self.last_page}.")
        object.__setattr__(self, "path", Path(self.path).expanduser().resolve())

    @property
    @log_call
    def expected_page_count(self) -> int:
        return self.last_page - self.first_page + 1


@log_call
def parse_pdf_part(path: Path) -> PdfPart | None:
    match = FILE_PATTERN.fullmatch(path.name)
    return PdfPart(path, *map(int, match.groups())) if match else None


@log_call
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

    parts.sort(key=PART_ORDER)
    ignored.sort(key=lambda path: path.name.lower())

    return parts, ignored


@log_call
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


@log_call
def _skew_value(value: str | float) -> float:
    angle = float(value)
    if not math.isfinite(angle) or not 0 <= angle <= 45:
        raise ValueError("--max-skew must be a finite number between 0 and 45.")
    return angle


@log_call
def _open_pdf(path: Path) -> pymupdf.Document:
    document = pymupdf.open(path)
    try:
        if not document.is_pdf or not len(document):
            raise ValueError(f"{path.name}: expected a PDF with at least one page.")
        if document.needs_pass:
            raise ValueError(f"{path.name}: password-protected PDFs are not supported.")
        if document.is_repaired:
            LOGGER.warning("PDF repaired while opening: %s", path)
        return document
    except BaseException:
        document.close()
        raise


@log_call
def _validate_inputs(parts: list[PdfPart], output_path: Path) -> None:
    errors, gaps = validate_ranges(parts)
    if errors:
        raise ValueError("\n".join(errors))
    for gap in gaps:
        LOGGER.warning(gap)
    if output_path.is_dir():
        raise IsADirectoryError(f"Output path is a directory: {output_path}")
    output_exists = output_path.exists()
    for part in parts:
        if not part.path.is_file():
            raise FileNotFoundError(f"Source PDF does not exist: {part.path}")
        if output_path == part.path or output_exists and output_path.samefile(part.path):
            raise ValueError("The output file is also one of the input files (or an alias).")


@log_call
def _straighten(document: pymupdf.Document, start: int, count: int, max_skew: float) -> int:
    if not max_skew:
        return 0
    if __package__:
        from .pdf_deskew import deskew_page, estimate_page_skew
    else:
        from pdf_deskew import deskew_page, estimate_page_skew
    corrected = 0
    started = last_log = time.monotonic()
    for index in range(count):
        page = document[start + index]
        angle = estimate_page_skew(page, max_skew)
        if angle:
            deskew_page(page, angle)
            corrected += 1
        LOGGER.debug("page=%s correction=%+.2f degrees", start + index + 1, angle)
        now = time.monotonic()
        if now - last_log >= 10 or index + 1 == count:
            rate = (index + 1) / max(0.001, now - started)
            LOGGER.info(
                "Deskew %s/%s (%.1f%%), %.2f pages/s, elapsed=%.0fs, ETA=%.0fs",
                index + 1,
                count,
                100 * (index + 1) / count,
                rate,
                now - started,
                (count - index - 1) / rate,
            )
            last_log = now
    return corrected


@log_call
def merge_pdfs(
    parts: list[PdfPart],
    output_path: Path,
    *,
    deskew: bool = True,
    max_skew: float = 30.0,
    check_page_counts: bool = True,
) -> int:
    """Read each fragment once, verify the staged PDF, and publish it atomically."""
    max_skew = _skew_value(max_skew)
    if not isinstance(deskew, bool) or not isinstance(check_page_counts, bool):
        raise ValueError("deskew and check_page_counts must be booleans.")
    parts = sorted(parts, key=PART_ORDER)
    output_path = Path(output_path).expanduser().resolve()
    _validate_inputs(parts, output_path)
    corrected, outlines = 0, []
    temporary_path = None
    try:
        with pymupdf.open() as writer:
            for index, part in enumerate(parts, start=1):
                LOGGER.info(
                    "[%s/%s] adding %s (book pages %s-%s)",
                    index,
                    len(parts),
                    part.path.name,
                    part.first_page,
                    part.last_page,
                )
                first_index = len(writer)
                with _open_pdf(part.path) as document:
                    count = len(document)
                    if check_page_counts and count != part.expected_page_count:
                        LOGGER.warning(
                            "%s: range %s-%s implies %s pages, but PDF contains %s; continuing.",
                            part.path.name,
                            part.first_page,
                            part.last_page,
                            part.expected_page_count,
                            count,
                        )
                    writer.insert_pdf(document)
                    outlines.extend(
                        [level, title, page + first_index if page > 0 else -1]
                        for level, title, page in document.get_toc()
                    )
                    if deskew:
                        corrected += _straighten(writer, first_index, count, max_skew)
            if outlines:
                writer.set_toc(outlines)
            total_pages = len(writer)
            temporary_path = _temporary_path(output_path.parent, prefix=".merge-", suffix=".pdf")
            writer.save(temporary_path, garbage=3, deflate=True)
        with _open_pdf(temporary_path) as verification:
            if verification.is_repaired or len(verification) != total_pages:
                raise RuntimeError(
                    "Merged PDF verification failed: damaged PDF or incorrect page count."
                )
        _commit_outputs({output_path: temporary_path})
    finally:
        if temporary_path is not None:
            _remove_temp(temporary_path)
    LOGGER.info("Done: %s; pages=%s, corrected=%s", output_path, total_pages, corrected)
    return total_pages


@log_call
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Merge pag<first>-<last>.pdf files in numeric book-page order. "
            "The result is saved in the project root by default, using the source "
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
            "Skip the page-count warning during merge when the PDF does not match "
            "the range encoded in the filename."
        ),
    )

    parser.add_argument(
        "--deskew",
        choices=("auto", "off"),
        default="auto",
        help="Automatically straighten tilted pages (default: auto). Does not detect 90/180-degree orientation.",
    )
    parser.add_argument(
        "--max-skew",
        type=_skew_value,
        default=30.0,
        help="Maximum tilt to detect in degrees, from 0 to 45 (default: 30).",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT,
        help="Destination folder (default: %(default)s, the project root).",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log function entry and named parameters; summarize large objects.",
    )
    return parser


@log_call
def main() -> int:
    args = build_parser().parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        source_folder = args.folder.expanduser().resolve()
        if not source_folder.is_dir():
            LOGGER.error("Source folder does not exist: %s", source_folder)
            return 2
        parts, ignored = discover_parts(source_folder)
        if not parts:
            LOGGER.error("No files matching pag<first>-<last>.pdf were found in %s.", source_folder)
            return 3
        if ignored:
            LOGGER.warning(
                "Ignored PDFs (filename does not match): %s", ", ".join(p.name for p in ignored)
            )
        output_dir = args.output_dir.expanduser().resolve()
        output_path = output_dir / f"{source_folder.name}.pdf"
        merge_pdfs(
            parts,
            output_path,
            deskew=args.deskew == "auto",
            max_skew=args.max_skew,
            check_page_counts=not args.skip_page_count_check,
        )
    except KeyboardInterrupt:
        LOGGER.warning("Merge interrupted; no partial PDF was published.")
        return 130
    except ValueError as exc:
        LOGGER.debug("Merge validation failed", exc_info=True)
        LOGGER.error("Merge rejected: %s", exc)
        return 4
    except Exception as exc:
        LOGGER.debug("Merge failed", exc_info=True)
        LOGGER.error("Merge failed: %s", exc)
        return 6
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv[1:] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(main())
