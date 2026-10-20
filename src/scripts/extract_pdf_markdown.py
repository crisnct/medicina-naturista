r"""Extract PDF text with PyMuPDF to Markdown with adaptive layout and headings.

Each page is straightened before text extraction or PyMuPDF's in-memory OCR.
OCR uses the integrated Tesseract engine and language data, without its executable.
The source PDF is unchanged; corrected pages are prepared individually in memory.
The source wording is preserved. Heading reconstruction is heuristic, especially
for OCR layers that do not encode bold fonts or document semantics.

Apel pentru un PDF:
    python src/scripts/extract_pdf_markdown.py "C:\GoogleDrive\Medicina\Books\Importanta plantelor in viata omului - prima mea carte de fitoterapie.pdf"

Implicit, pentru carte.pdf creează folderul și salvează fișierul în:
    <rădăcina proiectului>/medicina-naturista-documente/data/documents/Surse sigure/carte/carte.pdf.md
Calea este independentă de directorul de lansare. Îndreaptă separat fiecare pagină.
Opțiuni: -o "C:/Documente/carte.md" pentru altă destinație;
         --report "C:/Documente/carte.json" pentru raportul pe pagini;
         --tessdata "C:/Program Files/Tesseract-OCR/tessdata" pentru datele OCR;
         --deskew off pentru dezactivarea îndreptării;
         --debug pentru logarea intrării în funcții și a parametrilor (parole mascate).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import re
import sys
import tempfile
import time
import unicodedata
from bisect import bisect_right
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from itertools import zip_longest
from operator import attrgetter
from pathlib import Path
from statistics import median

import numpy as np
import pymupdf

if __package__:
    from .pdf_deskew import deskew_page, estimate_page_skew, estimate_skew
    from .script_files import _commit_outputs, _remove_temp, _temporary_path
    from .script_logging import log_call
else:
    from pdf_deskew import deskew_page, estimate_page_skew, estimate_skew
    from script_files import _commit_outputs, _remove_temp, _temporary_path
    from script_logging import log_call


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT / "medicina-naturista-documente" / "data" / "documents" / "Surse sigure"
)
MAX_OCR_PIXELS = 64_000_000


@dataclass(frozen=True, slots=True)
class Options:
    columns: str = "auto"
    ocr: str = "auto"
    lang: str = "ron+eng"
    dpi: int = 250
    deskew: bool = True
    max_skew: float = 30.0
    start_page: int = 1
    end_page: int | None = None
    tessdata: str | None = None
    password: str | None = field(default=None, repr=False)

    @log_call
    def __post_init__(self) -> None:
        if self.columns not in {"auto", "1", "2", "3"} or self.ocr not in {
            "auto",
            "always",
            "never",
        }:
            raise ValueError("Mod invalid pentru coloane sau OCR.")
        if not math.isfinite(self.max_skew) or not 0 <= self.max_skew <= 30:
            raise ValueError("--max-skew trebuie să fie un număr finit între 0 și 30.")
        if not isinstance(self.dpi, int) or not 72 <= self.dpi <= 600:
            raise ValueError("--dpi trebuie să fie un număr întreg între 72 și 600.")
        if (
            not isinstance(self.start_page, int)
            or self.start_page < 1
            or self.end_page is not None
            and (not isinstance(self.end_page, int) or self.end_page < self.start_page)
        ):
            raise ValueError("Intervalul de pagini este invalid.")
        if not self.lang or any(
            not re.fullmatch(r"[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)?", language)
            for language in self.lang.split("+")
        ):
            raise ValueError("Limbi OCR invalide; exemplu: ron+eng.")


@dataclass(frozen=True, slots=True)
class Glyph:
    text: str
    x0: float
    x1: float
    baseline: float
    size: float
    bold: bool = False


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: float
    column: int = 0


LINE_VALUES = attrgetter(*(item.name for item in fields(Line)))


@dataclass(slots=True)
class Profile:
    sizes: Counter = field(default_factory=Counter)
    labels: Counter = field(default_factory=Counter)
    margins: Counter = field(default_factory=Counter)
    occurrences: Counter = field(default_factory=Counter)
    outlines: dict[str, int] = field(default_factory=dict)
    pages: int = 0
    parts: bool = False

    @log_call
    def observe(self, lines: list[Line]) -> None:
        self.pages += 1
        for line in lines:
            self.occurrences[_margin_key(line.text)] += 1
            if len(line.text) > 80:
                self.sizes[round(line.size * 2) / 2] += len(line.text)
            if _short_title(line.text):
                self.labels[_canonical(line.text)] += 1
            if (
                PART.match(line.text)
                and len(line.text) < 55
                and not line.text.endswith(("-", ",", "."))
            ):
                self.parts = True
        # Running headers can be far from the physical edge of a scanned page.
        # Only its first/last baseline is eligible, never interior repeated labels.
        for edge in (_edge_lines(lines), lines[-1:]):
            for line in edge:
                if len(line.text) < 140:
                    self.margins[_margin_key(line.text)] += 1

    @property
    @log_call
    def body_size(self) -> float:
        return self.sizes.most_common(1)[0][0] if self.sizes else 10.0


PART = re.compile(r"^(?:partea|part)\s+(?:[IVXLCDM]+|\d+|întâi|intai|unu|doi|trei)\b", re.I)
CHAPTER = re.compile(
    r"^(?:capitol(?:ul)?|chapter|secțiunea|sectiunea|section|anexa|appendix)\s+(?:[IVXLCDM]+|\d+)\b",
    re.I,
)
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)(?:[.)]?\s+)\S")
BULLET = re.compile(r"^[•●▪■□*+\-]\s+(.+)$")
TOC = re.compile(r"(?:\.{3,}|(?:\.\s){3,}|…{2,})\s*\d+\s*$")


@lru_cache(maxsize=8192)
@log_call
def _canonical(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.upper())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


@lru_cache(maxsize=8192)
@log_call
def _margin_key(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"^\d+\s*|\s*\d+$", "", _canonical(text))).strip()


@log_call
def _edge_lines(lines: list[Line]) -> list[Line]:
    if not lines:
        return []
    first = min(line.top for line in lines)
    return [line for line in lines[:4] if line.top <= first + line.size * 1.5]


@lru_cache(maxsize=8192)
@log_call
def _short_title(text: str) -> bool:
    return (
        2 <= len(text) <= 90
        and text[:1].isupper()
        and not text.endswith((".", ",", ";", ":", "!", "?", "-"))
        and not BULLET.match(text)
        and not TOC.search(text)
    )


@lru_cache(maxsize=8192)
@log_call
def _all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= 0.95


@log_call
def _open_pdf(source: Path | io.BytesIO, password: str | None = None) -> pymupdf.Document:
    document = (
        pymupdf.open(stream=source.getvalue(), filetype="pdf")
        if isinstance(source, io.BytesIO)
        else pymupdf.open(source)
    )
    try:
        if not document.is_pdf or not len(document):
            raise ValueError("Sursa trebuie să fie un PDF cu cel puțin o pagină.")
        if document.needs_pass and not document.authenticate(password or ""):
            raise ValueError("PDF-ul este protejat; furnizați parola corectă cu --password.")
        if document.is_repaired:
            LOGGER.warning("PDF reparat la deschidere: %s", source)
        return document
    except BaseException:
        document.close()
        raise


@log_call
def _text_glyphs(
    page: pymupdf.Page, options: Options, textpage: pymupdf.TextPage | None = None
) -> tuple[list[Glyph], float]:
    """Read native character baselines and font styles in displayed page coordinates."""
    raw = page.get_text(
        "rawdict",
        flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES,
        textpage=textpage,
    )
    a, b, c, d, e, f = page.rotation_matrix
    small_heights = pymupdf.TOOLS.set_small_glyph_heights()
    chars = []
    seen: dict[tuple, list[tuple[float, float]]] = {}
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            dx, dy = line["dir"]
            advance_x, advance_y = dx * a + dy * c, dx * b + dy * d
            for span in line["spans"]:
                size = float(span["size"])
                height = size * (1 if small_heights else span["ascender"] - span["descender"])
                hs, hc = height * abs(dy), height * abs(dx)
                bold = bool(span["flags"] & 16) or bool(
                    re.search(r"bold|black|heavy|semibold", span["font"], re.I)
                )
                for char in span["chars"]:
                    text = char["c"]
                    if not text:
                        continue
                    ox, oy = char["origin"]
                    x0, y0, x1, y1 = char["bbox"]
                    # Baseline length of the rotated glyph rectangle; avoids
                    # allocating Rect/Quad/Point objects for every character.
                    width = math.hypot(x1 - x0 - hs, y1 - y0 - hc)
                    x0, y0 = ox * a + oy * c + e, ox * b + oy * d + f
                    x1, y1 = x0 + advance_x * width, y0 + advance_y * width
                    # Match overlapping text layers without merging adjacent characters.
                    cell_x, cell_y = math.floor(x0 * 2), math.floor(y0 * 2)
                    style = (text, round(size, 2), bold)
                    duplicate = any(
                        abs(x0 - x) <= 0.5 and abs(y0 - y) <= 0.5
                        for cx in range(cell_x - 1, cell_x + 2)
                        for cy in range(cell_y - 1, cell_y + 2)
                        for x, y in seen.get((style, cx, cy), [])
                    )
                    if duplicate:
                        continue
                    seen.setdefault((style, cell_x, cell_y), []).append((x0, y0))
                    chars.append((text, x0, y0, x1, y1, size, bold))
    if not chars or not any(char[0].strip() for char in chars):
        return [], 0.0
    angle = 0.0
    if options.deskew:
        visible = [char for char in chars if char[0].strip()]
        if not visible:
            return [], 0.0
        x = np.array([(char[1] + char[3]) / 2 for char in visible])
        y = np.array([char[2] for char in visible])
        angle = estimate_skew(x, y, options.max_skew, max(1.0, median(c[5] for c in visible) * 0.2))
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    glyphs = []
    for text, x0, y0, x1, y1, size, bold in chars:
        start, end = x0 * cosine + y0 * sine, x1 * cosine + y1 * sine
        baseline = -(x0 + x1) / 2 * sine + (y0 + y1) / 2 * cosine
        glyphs.append(Glyph(text, min(start, end), max(start, end), baseline, size, bold))
    return glyphs, angle


@log_call
def _line_from_glyphs(chars: list[Glyph]) -> Line:
    ordered = chars  # _group_glyphs already sorted each row by x.
    gaps = [b.x0 - a.x1 for a, b in zip(ordered, ordered[1:]) if a.text.strip() and b.text.strip()]
    normal_gap = max(0.0, median(gaps)) if gaps else 0.0
    parts = []
    previous = None
    for char in ordered:
        if previous and not previous.text.endswith(" ") and not char.text.isspace():
            gap = char.x0 - previous.x1
            if gap > max(0.7, min(previous.size, char.size) * 0.15, normal_gap * 2):
                parts.append(" ")
        parts.append(char.text)
        previous = char
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    sizes = [c.size for c in ordered if c.text.strip()]
    size = float(median(sizes)) if sizes else 10.0
    base = float(median(c.baseline for c in ordered))
    return Line(
        text,
        min(c.x0 for c in ordered),
        max(c.x1 for c in ordered),
        base - size,
        base,
        size,
        sum(len(c.text) for c in ordered if c.bold) / max(1, sum(len(c.text) for c in ordered)),
    )


@log_call
def _group_glyphs(glyphs: list[Glyph]) -> list[Line]:
    if not glyphs:
        return []
    typical = median(c.size for c in glyphs)
    tolerance = max(1.5, min(4.0, typical * 0.28))
    groups: list[list[Glyph]] = []
    baseline = 0.0
    for char in sorted(glyphs, key=lambda c: (c.baseline, c.x0)):
        if not groups or abs(char.baseline - baseline) > tolerance:
            groups.append([char])
            baseline = char.baseline
        else:
            groups[-1].append(char)
            # Online mean avoids quadratic recomputation on long rows.
            baseline += (char.baseline - baseline) / len(groups[-1])
    lines = []
    for group in groups:
        ordered = sorted(group, key=lambda c: c.x0)
        # Separate columns, table cells, and horizontally distant captions.
        pieces: list[list[Glyph]] = [[]]
        for char in ordered:
            if pieces[-1] and char.x0 - pieces[-1][-1].x1 > typical * 2.5:
                pieces.append([])
            pieces[-1].append(char)
        lines.extend(_line_from_glyphs(piece) for piece in pieces)
    return [line for line in lines if line.text]


@log_call
def _column_cuts(lines: list[Line], mode: str) -> list[float]:
    if not lines or mode == "1":
        return []
    low, high = min(line_item.x0 for line_item in lines), max(line_item.x1 for line_item in lines)
    width = high - low
    if width < 50:
        return []
    if mode != "auto":
        return [low + width * n / int(mode) for n in range(1, int(mode))]
    # A gutter has many lines ending on its left and starting on its right,
    # with few prose lines crossing it. Full-width headings are permitted.
    body = [line_item for line_item in lines if len(line_item.text) > 18]
    if len(body) < 8:
        return []
    x0, x1, top, bottom, size = np.array(
        [(line.x0, line.x1, line.top, line.bottom, line.size) for line in body]
    ).T
    cuts = np.linspace(low + width * 0.2, high - width * 0.2, 100)
    left, right = x1 <= cuts[:, None] - 4, x0 >= cuts[:, None] + 4
    crossings = ((x0 < cuts[:, None]) & (x1 > cuts[:, None])).sum(axis=1)
    counts = np.minimum(left.sum(axis=1), right.sum(axis=1))
    min_overlap = 4 * float(np.median(size))
    candidates = []
    for index in np.flatnonzero((counts >= 4) & (crossings <= len(body) * 0.12)):
        lmask, rmask = left[index], right[index]
        overlap = min(bottom[lmask].max(), bottom[rmask].max()) - max(
            top[lmask].min(), top[rmask].min()
        )
        gutter = x0[rmask].min() - x1[lmask].max()
        if overlap >= min_overlap and gutter >= 8:
            candidates.append((counts[index] - crossings[index] * 3, gutter, float(cuts[index])))
    if not candidates:
        return []
    best = max(candidates)[2]
    cuts = [best]
    # Detect a possible third column on either side of the strongest gutter.
    for subset in (
        [line_item for line_item in lines if line_item.x1 < best],
        [line_item for line_item in lines if line_item.x0 > best],
    ):
        extra = (
            _column_cuts(subset, "auto") if len(subset) < len(lines) and len(subset) >= 12 else []
        )
        if extra:
            cuts.append(extra[0])
    return sorted(cuts)[:2]


@log_call
def _reading_order(lines: list[Line], cuts: list[float]) -> list[Line]:
    if not cuts:
        return _coalesce_rows(lines)
    spanning, rest = [], []
    for line in lines:
        (spanning if any(line.x0 < cut - 4 and line.x1 > cut + 4 for cut in cuts) else rest).append(
            line
        )
    spanning.sort(key=lambda line: line.top)
    tops = [line.top for line in spanning]
    bands = [[[] for _ in range(len(cuts) + 1)] for _ in range(len(spanning) + 1)]
    for line in rest:
        bands[bisect_right(tops, line.top)][bisect_right(cuts, line.x0)].append(line)
    result = []
    for band, boundary in zip_longest(bands, spanning):
        for column, segment in enumerate(band):
            result.extend(replace(line, column=column) for line in _coalesce_rows(segment))
        if boundary is not None:
            result.append(boundary)
    return result


@log_call
def _coalesce_rows(lines: list[Line]) -> list[Line]:
    """Reunite separated fragments after the actual column boundaries are known."""
    result: list[Line] = []
    for line in sorted(lines, key=lambda line_item: (line_item.bottom, line_item.x0)):
        if (
            result
            and abs(result[-1].bottom - line.bottom) <= min(result[-1].size, line.size) * 0.28
        ):
            previous = result.pop()
            left, right = sorted((previous, line), key=lambda line_item: line_item.x0)
            size = (previous.size * len(previous.text) + line.size * len(line.text)) / (
                len(previous.text) + len(line.text)
            )
            result.append(
                Line(
                    left.text + " " + right.text,
                    min(left.x0, right.x0),
                    max(left.x1, right.x1),
                    min(left.top, right.top),
                    (left.bottom + right.bottom) / 2,
                    size,
                    max(left.bold, right.bold),
                    left.column,
                )
            )
        else:
            result.append(line)
    return result


@log_call
def _find_tessdata(directory: str | None, language: str) -> str:
    """Resolve language files without invoking PyMuPDF's executable discovery."""
    configured = directory or os.environ.get("TESSDATA_PREFIX")
    candidates = (
        [Path(configured).expanduser()]
        if configured
        else [
            Path("C:/Program Files/Tesseract-OCR/tessdata"),
            Path("/usr/share/tesseract-ocr/5/tessdata"),
            Path("/usr/share/tesseract-ocr/4.00/tessdata"),
            Path("/usr/share/tessdata"),
            Path("/usr/local/share/tessdata"),
            Path("/opt/homebrew/share/tessdata"),
        ]
    )
    languages = language.split("+")
    for candidate in candidates:
        if all(name and (candidate / f"{name}.traineddata").is_file() for name in languages):
            return str(candidate.resolve())
    raise RuntimeError(
        f"Lipsesc datele OCR pentru {language!r}. Indicați directorul cu fișierele "
        ".traineddata prin --tessdata sau TESSDATA_PREFIX, ori folosiți --ocr never."
    )


@log_call
def _ocr_glyphs(page: pymupdf.Page, options: Options) -> tuple[list[Glyph], float]:
    """Render and recognize the prepared page in memory through PyMuPDF."""
    width, height = page.rect.width, page.rect.height
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise ValueError("Dimensiuni invalide pentru pagina OCR.")
    if math.ceil(width * options.dpi / 72) * math.ceil(height * options.dpi / 72) > MAX_OCR_PIXELS:
        raise ValueError("Randarea OCR depășește limita de 64 megapixeli; reduceți --dpi.")
    textpage = page.get_textpage_ocr(
        flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES,
        language=options.lang,
        dpi=options.dpi,
        full=True,
        tessdata=_find_tessdata(options.tessdata, options.lang),
    )
    # OCR font metrics are synthetic. Preserve native word/line grouping instead
    # of fitting baselines independently from those artificial character fonts.
    rows = []
    baselines: dict[tuple[int, int], list[float]] = {}
    line_widths: dict[tuple[int, int], list[float]] = {}
    for x0, y0, x1, y1, text, block, line, _ in textpage.extractWORDS():
        box = pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix
        key = (block, line)
        rows.append((key, text, box))
        baselines.setdefault(key, []).append(box.y1)
        widths = line_widths.setdefault(key, [0.0, 0.0])
        widths[0] += box.width
        widths[1] += max(1, len(text))
    # GlyphLessFont heights can vary wildly between identical scanned rows.
    # Infer relative text sizes from mean character width instead, normalized
    # to the profile's default body size. Preserve larger scanned headings.
    sizes = {key: width / count for key, (width, count) in line_widths.items()}
    typical = median(sizes.values()) if sizes else 1.0
    line_baselines = {key: median(values) for key, values in baselines.items()}
    glyphs = [
        Glyph(
            text + " ",
            box.x0,
            box.x1,
            line_baselines[key],
            max(1.0, 10.0 * sizes[key] / max(0.001, typical)),
        )
        for key, text, box in rows
    ]
    return glyphs, 0.0


@log_call
def _page_glyphs(
    page: pymupdf.Page, page_index: int, options: Options
) -> tuple[list[Glyph], float, str]:
    """Prepare this page independently, then read its text or run OCR exactly once."""
    angle = 0.0
    with ExitStack() as resources:
        if options.deskew:
            angle = estimate_page_skew(page, options.max_skew)
            if angle:
                corrected = resources.enter_context(pymupdf.open())
                corrected.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
                page = deskew_page(corrected[0], angle)

        # Both paths now see the same corrected page. Do not rotate it again.
        prepared_options = replace(options, deskew=False)
        glyphs, _ = _text_glyphs(page, prepared_options) if options.ocr != "always" else ([], 0.0)
        method = "text"
        if not glyphs and options.ocr != "never":
            glyphs, _ = _ocr_glyphs(page, prepared_options)
            method = "ocr"
    return glyphs, angle, method


@log_call
def _heading_level(
    line: Line, profile: Profile, body: float, gap: float, prose_width: float = math.inf
) -> int | None:
    text = line.text
    if (
        len(text) > 180
        or not any(c.isalpha() for c in text)
        or BULLET.match(text)
        or TOC.search(text)
    ):
        return None
    if _canonical(text) in profile.outlines:
        return profile.outlines[_canonical(text)]
    if (
        PART.match(text)
        and not text.endswith(("-", ",", "."))
        and (len(text) < 55 or line.size > body * 1.15)
    ):
        return 2
    if (
        CHAPTER.match(text)
        and not text.endswith(("-", ",", "."))
        and (len(text) < 55 or line.size > body * 1.15)
    ):
        return 3 if profile.parts else 2
    numbered = NUMBERED.match(text)
    styled = line.size >= body * 1.08 or line.bold >= 0.6
    if numbered and len(text) < 120 and (styled or gap > body * 0.5):
        return min(6, 2 + numbered.group(1).count("."))
    if text.endswith((".", ":", ";", "!", "?")) and not styled:
        return None
    if line.size >= body * 1.35:
        return 2
    if _all_caps(text) and len(text) < 130 and not text.endswith((".", ";", "!", "?")):
        return 3 if line.size < body * 1.2 else 2
    if _short_title(text) and profile.labels[_canonical(text)] >= 4:
        return 4
    if (
        not text.endswith((".", ":", ";", "!", "?", "-"))
        and math.isfinite(gap)
        and gap > body * 1.25
        and text[:1].isupper()
        and len(text.split()) <= 16
        and len(text) < 150
    ):
        return 3
    if (
        len(text) > 50
        and line.x1 - line.x0 > prose_width * 0.8
        and line.size < body * 1.18
        and line.bold < 0.6
    ):
        return None
    if (
        styled
        and not text.endswith((".", ":", ";", "!", "?", "-"))
        and (line.bold >= 0.6 or line.size >= body * 1.18 or gap > body * 0.7 and len(text) < 150)
    ):
        return 3
    return None


@log_call
def _join_text(previous: str, text: str) -> str:
    if previous.endswith("-") and text[:1].isalpha():
        return previous[:-1] + text
    return previous + " " + text


@log_call
def _render_page(lines: list[Line], profile: Profile) -> tuple[str, int]:
    if not lines:
        return "*[Pagină fără text detectabil]*", 0
    sizes = Counter()
    for line in lines:
        if len(line.text) > 60:
            sizes[round(line.size * 2) / 2] += len(line.text)
    body = sizes.most_common(1)[0][0] if sizes else profile.body_size
    prose_widths = [line.x1 - line.x0 for line in lines if len(line.text) > 60]
    prose_width = median(prose_widths) if prose_widths else math.inf
    removed = set()
    edge_threshold = max(3, math.ceil(profile.pages * 0.015))
    edges = {id(line) for line in _edge_lines(lines)}
    edge_indexes = {i for i, line in enumerate(lines) if id(line) in edges} | {len(lines) - 1}
    for index in edge_indexes:
        line = lines[index]
        if re.fullmatch(r"[\s–—-]*\d+[\s–—-]*", line.text):
            removed.add(index)
        elif (
            (key := _margin_key(line.text))
            and profile.margins[key] >= max(edge_threshold, profile.occurrences[key] * 0.75)
            and line.size < body * 1.12
        ):
            removed.add(index)
    blocks: list[tuple[str, int | None]] = []
    paragraph = ""
    previous = None
    heading_count = 0

    @log_call
    def flush():
        nonlocal paragraph
        if paragraph:
            blocks.append((paragraph, None))
            paragraph = ""

    for index, line in enumerate(lines):
        if index in removed:
            continue
        gap = (
            line.top - previous.bottom if previous and previous.column == line.column else math.inf
        )
        column_changed = previous is not None and previous.column != line.column
        level = _heading_level(line, profile, body, gap, prose_width)
        if len(lines) <= 3 and _all_caps(line.text):
            level = 2
        if (
            level is None
            and blocks
            and blocks[-1][1] is not None
            and not paragraph
            and previous is not None
            and (
                previous.text.endswith((",", "-", "("))
                or previous.text.count("(") > previous.text.count(")")
            )
            and gap < body * 0.6
            and not column_changed
            and len(line.text) < 120
            and abs(previous.size - line.size) < body * 0.1
        ):
            level = blocks[-1][1]
        text = line.text.replace("#", r"\#")
        bullet = BULLET.match(text)
        if level:
            flush()
            # Wrapped headings with the same style form a single Markdown title.
            if (
                blocks
                and blocks[-1][1] == level
                and previous is not None
                and gap < body * 0.6
                and not column_changed
                and abs(previous.size - line.size) < body * 0.1
                and not CHAPTER.match(text)
                and not PART.match(text)
            ):
                prior, _ = blocks[-1]
                blocks[-1] = (_join_text(prior, text), level)
            else:
                blocks.append((text, level))
                heading_count += 1
        elif bullet:
            flush()
            blocks.append(("- " + bullet.group(1), None))
        elif TOC.search(text):
            flush()
            blocks.append((text, None))
        else:
            if column_changed or gap > body * 0.65:
                flush()
            if (
                blocks
                and blocks[-1][0].startswith("- ")
                and not paragraph
                and gap < body * 0.6
                and previous is not None
                and line.x0 <= previous.x0 + body
                and not (previous.text.endswith((".", ";", "!", "?")) and line.text[:1].isupper())
            ):
                prior, prior_level = blocks[-1]
                blocks[-1] = (_join_text(prior, text), prior_level)
            else:
                paragraph = _join_text(paragraph, text) if paragraph else text
        previous = line
    flush()
    rendered = []
    for text, level in blocks:
        block = "#" * level + " " + text if level else text
        if rendered and block.startswith("- ") and rendered[-1].startswith("- "):
            rendered[-1] += "\n" + block
        else:
            rendered.append(block)
    return "\n\n".join(rendered), heading_count


@log_call
def _validate_paths(pdf_path: Path, output_path: Path, report_path: Path | None):
    paths = [
        Path(path).expanduser().resolve()
        for path in (pdf_path, output_path, report_path)
        if path is not None
    ]
    for index, path in enumerate(paths):
        if any(
            path == previous or path.exists() and previous.exists() and path.samefile(previous)
            for previous in paths[:index]
        ):
            raise ValueError("Sursa PDF, Markdown și raportul trebuie să aibă căi diferite.")
    if not paths[0].is_file():
        raise FileNotFoundError(f"Fișierul PDF nu există: {paths[0]}")
    for target in paths[1:]:
        if target.is_dir():
            raise IsADirectoryError(f"Destinația este un director: {target}")
    return paths[0], paths[1], paths[2] if report_path is not None else None


@log_call
def extract_markdown(
    pdf_path: Path,
    output_path: Path,
    options: Options | None = None,
    report_path: Path | None = None,
) -> tuple[int, int]:
    options = options or Options()
    pdf_path, output_path, report_path = _validate_paths(pdf_path, output_path, report_path)
    started = last_log = time.monotonic()
    profile = Profile()
    report = {
        "source": str(pdf_path),
        "pages": [],
        "headings": 0,
        "characters": 0,
        "warnings": [
            "Ierarhia titlurilor este dedusă euristic; verificați rezultatul pentru documente complexe."
        ],
    }
    # Spool lightweight line records, freeing PDF caches after every page.
    # A failed extraction never replaces an existing output.
    temporary_root = PROJECT_ROOT / "aiPlans" / "tmp" / "pdfs"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as resources:
        directory = Path(resources.enter_context(tempfile.TemporaryDirectory(dir=temporary_root)))
        spool = directory / "pages.jsonl"
        staged = _temporary_path(output_path.parent)
        resources.callback(_remove_temp, staged)
        outputs = {output_path: staged}
        if report_path is not None:
            outputs[report_path] = _temporary_path(report_path.parent)
            resources.callback(_remove_temp, outputs[report_path])
        with (
            _open_pdf(pdf_path, options.password) as document,
            spool.open("w", encoding="utf-8") as records,
        ):
            for level, title, *_ in document.get_toc():
                profile.outlines[_canonical(title)] = min(6, int(level) + 1)
            total = len(document)
            end = options.end_page if options.end_page is not None else total
            if not 1 <= options.start_page <= end <= total:
                raise ValueError(f"Interval invalid; documentul are {total} pagini.")
            count = end - options.start_page + 1
            LOGGER.info(
                "Analiză: %s pagini; coloane=%s, OCR=%s, deskew=%s",
                count,
                options.columns,
                options.ocr,
                options.deskew,
            )
            for number in range(options.start_page, end + 1):
                try:
                    glyphs, angle, method = _page_glyphs(document[number - 1], number - 1, options)
                    lines = _group_glyphs(glyphs)
                except Exception as exc:
                    raise RuntimeError(f"Pagina {number}: {exc}") from exc
                cuts = _column_cuts(lines, options.columns)
                lines = _reading_order(lines, cuts)
                profile.observe(lines)
                records.write(
                    json.dumps(
                        {"number": number, "lines": list(map(LINE_VALUES, lines))},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                report["pages"].append(
                    {
                        "page": number,
                        "method": method,
                        "skew_degrees": round(angle, 2),
                        "columns": len(cuts) + 1,
                        "lines": len(lines),
                    }
                )
                if not lines:
                    report["warnings"].append(f"Pagina {number}: fără text detectabil ({method}).")
                now = time.monotonic()
                if now - last_log >= 10 or number == end:
                    done = number - options.start_page + 1
                    rate = done / max(0.001, now - started)
                    LOGGER.info(
                        "%s/%s (%.1f%%), %.2f pagini/s, timp=%.0fs, ETA=%.0fs",
                        done,
                        count,
                        100 * done / count,
                        rate,
                        now - started,
                        (count - done) / rate,
                    )
                    last_log = now
        with (
            staged.open("w", encoding="utf-8", newline="\n") as output,
            spool.open(encoding="utf-8") as records,
        ):
            output.write(
                f"# {pdf_path.stem}\n\n<!-- Text extras local. Titluri deduse din aspect și numerotare; grafia sursei este păstrată. -->\n"
            )
            for record in records:
                data = json.loads(record)
                text, headings = _render_page([Line(*line) for line in data["lines"]], profile)
                output.write(f"\n\n<!-- Pagina PDF {data['number']} -->\n\n{text}\n")
                report["headings"] += headings
                report["characters"] += len(text)
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        if report_path is not None:
            outputs[report_path].write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        _commit_outputs(outputs)
    LOGGER.info(
        "Titluri: %s; pagini fără text: %s",
        report["headings"],
        sum(page["lines"] == 0 for page in report["pages"]),
    )
    return profile.pages, report["characters"]


@log_call
def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=f"Implicit: {DEFAULT_OUTPUT_ROOT}/<nume fără extensie>/<fișier PDF>.md; creează folderul.",
    )
    parser.add_argument("--columns", choices=("auto", "1", "2", "3"), default="auto")
    parser.add_argument("--ocr", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--lang", default="ron+eng")
    parser.add_argument("--dpi", type=int, default=250)
    parser.add_argument(
        "--deskew",
        choices=("auto", "off"),
        default="auto",
        help="Îndreaptă separat fiecare pagină înainte de extragere/OCR (implicit: auto).",
    )
    parser.add_argument("--max-skew", type=float, default=30.0)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument(
        "--tessdata", help="Directorul cu datele OCR .traineddata; alternativ, TESSDATA_PREFIX."
    )
    parser.add_argument("--password")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Loghează intrarea în fiecare funcție și parametrii mascați/rezumați.",
    )
    parser.add_argument(
        "--report", type=Path, help="Raport JSON: unghi, coloane, OCR și avertismente pe pagină"
    )
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        output_path = args.output or DEFAULT_OUTPUT_ROOT / args.pdf.stem / f"{args.pdf.name}.md"
        options = Options(
            **{
                item.name: args.deskew == "auto"
                if item.name == "deskew"
                else getattr(args, item.name)
                for item in fields(Options)
            }
        )
        pages, characters = extract_markdown(args.pdf, output_path, options, args.report)
    except KeyboardInterrupt:
        LOGGER.warning("Extragerea a fost întreruptă.")
        return 130
    except Exception as exc:
        LOGGER.debug("Detalii eroare extragere", exc_info=True)
        LOGGER.error("Extragerea a eșuat: %s", exc)
        return 1
    print(f"Scris: {output_path.expanduser().resolve()}\nPagini: {pages}; caractere: {characters}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv[1:] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(main())
