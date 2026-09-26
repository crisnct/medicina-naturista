"""Extract an OCR-backed PDF to structured Markdown.

The extractor keeps the visual reading order of two-column book pages and
converts typographically larger lines to Markdown headings. It intentionally
does not rewrite OCR text, because silent language corrections can alter the
source material.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import pdfplumber


COLUMN_SPLIT_X = 297.0
LINE_TOLERANCE = 5.0
TABLE_LABELS = {
    "SUPLIMENT",
    "DOZĂ RECOMANDATĂ",
    "DOZA RECOMANDATA",
    "OBSERVAȚII",
    "OBSERVATII",
    "SIMPTOM",
    "CAUZĂ POSIBILĂ",
    "CAUZA POSIBILA",
}
SUBHEADINGS = {
    "NUTRIENTI",
    "PLANTE",
    "RECOMANDARI",
    "PRECAUTII",
    "PROCEDURA",
    "TRATAMENT",
    "SIMPTOME",
    "CAUZE",
    "INTRODUCERE",
    "OBSERVATII",
    "SURSE",
    "CE SE GASESTE PE RAFTURI",
    "SFATURI SI PRECAUTII",
    "VITAMINELE DE LA A LA Z",
    "DURATA TRATAMENTULUI",
}


@dataclass(frozen=True)
class Word:
    index: int
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float


@dataclass(frozen=True)
class Line:
    text: str
    top: float
    bottom: float
    x0: float
    x1: float
    max_size: float
    median_size: float
    large_word_ratio: float
    max_word_gap: float
    word_indexes: frozenset[int]


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    return text


def _canonical(text: str) -> str:
    normalized = text.upper().replace("Ş", "Ș").replace("Ţ", "Ț")
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    ).strip(" .:;-")


def _group_words(words: list[Word]) -> list[Line]:
    if not words:
        return []

    groups: list[list[Word]] = []
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        if not groups:
            groups.append([word])
            continue

        current_top = median(item.top for item in groups[-1])
        if abs(word.top - current_top) <= LINE_TOLERANCE:
            groups[-1].append(word)
        else:
            groups.append([word])

    lines: list[Line] = []
    for group in groups:
        ordered = sorted(group, key=lambda item: item.x0)
        word_gaps = [
            max(0.0, current.x0 - previous.x1)
            for previous, current in zip(ordered, ordered[1:])
        ]
        text = _normalize_text(" ".join(item.text for item in ordered))
        if not text:
            continue
        lines.append(
            Line(
                text=text,
                top=min(item.top for item in ordered),
                bottom=max(item.bottom for item in ordered),
                x0=min(item.x0 for item in ordered),
                x1=max(item.x1 for item in ordered),
                max_size=max(item.size for item in ordered),
                median_size=float(median(item.size for item in ordered)),
                large_word_ratio=(
                    sum(item.size >= 11.5 for item in ordered) / len(ordered)
                ),
                max_word_gap=max(word_gaps, default=0.0),
                word_indexes=frozenset(item.index for item in ordered),
            )
        )
    return lines


def _is_noise(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if compact.upper().strip(".:;-") in {"D", "G", "GR", "OGR", "OCR", "HCRR"}:
        return True
    alphanumeric = sum(character.isalnum() for character in compact)
    if len(compact) >= 6 and alphanumeric / len(compact) < 0.35:
        return True
    return False


def _is_running_header(line: Line, page_number: int) -> bool:
    if page_number <= 10 or line.top >= 72 or line.max_size > 11.5:
        return False
    letters = [character for character in line.text if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def _is_page_number(line: Line, page_height: float) -> bool:
    return line.top > page_height - 65 and bool(re.fullmatch(r"[\s\-–—]*\d+[\s\-–—]*", line.text))


def _is_heading_candidate(line: Line) -> bool:
    if (
        line.max_size < 12
        or line.median_size < 11.5
        or line.large_word_ratio < 0.6
        or len(line.text) > 160
        or _is_noise(line.text)
    ):
        return False
    normalized = _canonical(line.text)
    return normalized not in TABLE_LABELS and not normalized.startswith("SIMPTOM CAUZ")


def _format_line(line: Line) -> str:
    text = line.text.replace("#", r"\#")
    normalized = _canonical(text)

    if normalized in TABLE_LABELS or normalized.startswith("SIMPTOM CAUZ"):
        return f"**{text}**"

    if _is_heading_candidate(line):
        if normalized in SUBHEADINGS or line.max_size < 15:
            letters = [character for character in text if character.isalpha()]
            if (
                normalized not in SUBHEADINGS
                and letters
                and all(character.isupper() for character in letters)
            ):
                return f"## {text}"
            return f"### {text}"
        return f"## {text}"

    if text.startswith(("•", "* ", "□", "■")):
        item = text.lstrip("•*□■ ")
        return f"- {item}"

    return text


def _full_width_headings(lines: list[Line]) -> list[Line]:
    headings: list[Line] = []
    for line in lines:
        spans_columns = line.x0 < COLUMN_SPLIT_X - 25 and line.x1 > COLUMN_SPLIT_X + 25
        if (
            _is_heading_candidate(line)
            and line.median_size >= 12
            and spans_columns
            and line.max_word_gap <= 40
        ):
            headings.append(line)
    return headings


def _render_lines(lines: list[Line], page_number: int, page_height: float) -> list[str]:
    rendered: list[str] = []
    previous_was_heading = False
    for line in lines:
        if _is_running_header(line, page_number) or _is_page_number(line, page_height):
            continue
        if _is_noise(line.text):
            continue

        formatted = _format_line(line)
        is_heading = formatted.startswith("#")
        if rendered and (is_heading or previous_was_heading):
            if rendered[-1] != "":
                rendered.append("")
        rendered.append(formatted)
        previous_was_heading = is_heading
    return rendered


def _extract_page(page, page_number: int) -> list[str]:
    raw_words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        keep_blank_chars=False,
        extra_attrs=["size"],
    )
    words = [
        Word(
            index=index,
            text=item["text"],
            x0=float(item["x0"]),
            x1=float(item["x1"]),
            top=float(item["top"]),
            bottom=float(item["bottom"]),
            size=float(item["size"]),
        )
        for index, item in enumerate(raw_words)
    ]
    if not words:
        return ["*[Pagină fără text OCR detectabil]*"]

    all_lines = _group_words(words)
    full_headings = _full_width_headings(all_lines)
    consumed = set().union(*(line.word_indexes for line in full_headings)) if full_headings else set()

    # The symptom/cause tables span the complete page width. Keeping each row
    # together is more useful than forcing those pages into book columns.
    if page_number in {2, 10} or 137 <= page_number <= 140:
        return _render_lines(all_lines, page_number, float(page.height))

    left_words = [
        word for word in words
        if word.index not in consumed and (word.x0 + word.x1) / 2 < COLUMN_SPLIT_X
    ]
    right_words = [
        word for word in words
        if word.index not in consumed and (word.x0 + word.x1) / 2 >= COLUMN_SPLIT_X
    ]
    left_lines = _group_words(left_words)
    right_lines = _group_words(right_words)

    boundaries = sorted(full_headings, key=lambda line: line.top)
    page_lines: list[str] = []
    band_start = 0.0

    def append_band(band_end: float) -> None:
        left_band = [line for line in left_lines if band_start <= line.top < band_end]
        right_band = [line for line in right_lines if band_start <= line.top < band_end]
        page_lines.extend(_render_lines(left_band, page_number, float(page.height)))
        if left_band and right_band and page_lines and page_lines[-1] != "":
            page_lines.append("")
        page_lines.extend(_render_lines(right_band, page_number, float(page.height)))

    for heading in boundaries:
        append_band(heading.top)
        if page_lines and page_lines[-1] != "":
            page_lines.append("")
        page_lines.append(_format_line(heading))
        page_lines.append("")
        band_start = heading.bottom + 0.1

    append_band(float(page.height) + 1)
    while page_lines and page_lines[-1] == "":
        page_lines.pop()
    return page_lines


def extract_markdown(pdf_path: Path, output_path: Path) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    page_count = 0
    character_count = 0

    with pdfplumber.open(pdf_path) as document, temporary_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        page_count = len(document.pages)
        output.write("<!-- Pagina PDF 1 -->\n\n")
        output.write("# Vindecare prin nutriție\n\n")
        output.write("**Autor: Phyllis A. Balch**\n\n")
        output.write(
            "*Fără medicamente, doar prin vitamine, minerale, plante și "
            "suplimente alimentare naturale*\n\n"
        )
        output.write(
            "<!-- Text extras din stratul OCR al PDF-ului; grafia și eventualele "
            "erori OCR au fost păstrate. -->\n"
        )

        for page_number, page in enumerate(document.pages, start=1):
            if page_number == 1:
                continue
            if page_number % 25 == 0 or page_number == page_count:
                print(f"Procesare pagină {page_number}/{page_count}...", file=sys.stderr)

            lines = _extract_page(page, page_number)
            output.write(f"\n\n<!-- Pagina PDF {page_number} -->\n\n")
            page_text = "\n".join(lines)
            output.write(page_text)
            character_count += len(page_text)

    temporary_path.replace(output_path)
    return page_count, character_count


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args()

    pdf_path = args.pdf.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if not pdf_path.is_file():
        parser.error(f"Fișierul PDF nu există: {pdf_path}")
    if pdf_path == output_path:
        parser.error("Fișierul sursă și cel de ieșire trebuie să fie diferite.")

    pages, characters = extract_markdown(pdf_path, output_path)
    print(f"Scris: {output_path}")
    print(f"Pagini: {pages}; caractere extrase: {characters}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
