"""Extract PDF text to Markdown with adaptive layout and heading detection.

Text layers are deskewed geometrically; image-only pages use local Tesseract.
The source wording is preserved. Heading reconstruction is heuristic, especially
for OCR layers that do not encode bold fonts or document semantics.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import median

import numpy as np
import pdfplumber
from pdfminer.pdfdocument import PDFNoOutlines


@dataclass(frozen=True)
class Options:
    columns: str = "auto"
    ocr: str = "auto"
    lang: str = "ron+eng"
    dpi: int = 250
    deskew: bool = True
    max_skew: float = 30.0
    start_page: int = 1
    end_page: int | None = None
    tesseract_cmd: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class Glyph:
    text: str
    x0: float
    x1: float
    baseline: float
    size: float
    bold: bool = False


@dataclass(frozen=True)
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: float
    column: int = 0


@dataclass
class Profile:
    sizes: Counter = field(default_factory=Counter)
    labels: Counter = field(default_factory=Counter)
    margins: Counter = field(default_factory=Counter)
    occurrences: Counter = field(default_factory=Counter)
    outlines: dict[str, int] = field(default_factory=dict)
    pages: int = 0
    parts: bool = False

    def observe(self, lines: list[Line]) -> None:
        self.pages += 1
        for line in lines:
            self.occurrences[_margin_key(line.text)] += 1
            if len(line.text) > 80:
                self.sizes[round(line.size * 2) / 2] += len(line.text)
            if _short_title(line.text):
                self.labels[_canonical(line.text)] += 1
            if PART.match(line.text) and len(line.text) < 55 and not line.text.endswith(("-", ",", ".")):
                self.parts = True
        # Running headers can be far from the physical edge of a scanned page.
        # Only its first/last baseline is eligible, never interior repeated labels.
        for edge in (_edge_lines(lines), lines[-1:]):
            for line in edge:
                if len(line.text) < 140:
                    self.margins[_margin_key(line.text)] += 1

    @property
    def body_size(self) -> float:
        return self.sizes.most_common(1)[0][0] if self.sizes else 10.0


PART = re.compile(r"^(?:partea|part)\s+(?:[IVXLCDM]+|\d+|întâi|intai|unu|doi|trei)\b", re.I)
CHAPTER = re.compile(r"^(?:capitol(?:ul)?|chapter|secțiunea|sectiunea|section|anexa|appendix)\s+(?:[IVXLCDM]+|\d+)\b", re.I)
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)(?:[.)]?\s+)\S")
BULLET = re.compile(r"^[•●▪■□*+\-]\s+(.+)$")
TOC = re.compile(r"(?:\.{3,}|(?:\.\s){3,}|…{2,})\s*\d+\s*$")


def _canonical(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.upper())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def _margin_key(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"^\d+\s*|\s*\d+$", "", _canonical(text))).strip()


def _edge_lines(lines: list[Line]) -> list[Line]:
    if not lines:
        return []
    first = min(line.top for line in lines)
    return [line for line in lines[:4] if line.top <= first + line.size * 1.5]


def _short_title(text: str) -> bool:
    return (2 <= len(text) <= 90 and text[:1].isupper()
            and not text.endswith((".", ",", ";", ":", "!", "?", "-"))
            and not BULLET.match(text) and not TOC.search(text))


def _all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and sum(c.isupper() for c in letters) / len(letters) >= .95


def estimate_skew(x: np.ndarray, y: np.ndarray, max_angle: float = 30.0,
                  bin_size: float = 2.0, min_gain: float = 1.06) -> float:
    """Find the baseline direction by maximizing horizontal projection peaks.

    Works with independently positioned OCR glyphs whose matrices say zero
    rotation even though their baselines follow a tilted scanned page.
    """
    if len(x) < 30 or max_angle == 0 or np.ptp(x) < 20:
        return 0.0
    # Bounded work for very dense pages; deterministic sampling.
    if len(x) > 12000:
        indexes = np.linspace(0, len(x) - 1, 12000, dtype=int)
        x, y = x[indexes], y[indexes]
    x, y = x - np.median(x), y - np.median(y)

    def score(angle: float) -> float:
        rad = math.radians(angle)
        projected = -math.sin(rad) * x + math.cos(rad) * y
        bins = np.floor((projected - projected.min()) / bin_size).astype(int)
        counts = np.bincount(bins)
        return float(np.dot(counts.astype(float), counts))

    coarse = np.linspace(-max_angle, max_angle, max(3, int(max_angle * 4) + 1))
    best = max(coarse, key=score)
    fine = np.linspace(max(-max_angle, best - .5), min(max_angle, best + .5), 21)
    best = float(max(fine, key=score))
    # Prefer no transformation when there is no convincing improvement.
    return best if abs(best) >= .15 and score(best) > score(0) * min_gain else 0.0


def _text_glyphs(page, options: Options) -> tuple[list[Glyph], float]:
    chars = [c for c in page.dedupe_chars(tolerance=.5).chars if c["text"]]
    visible = [c for c in chars if c["text"].strip()]
    if not visible:
        return [], 0.0
    x = np.array([(c["x0"] + c["x1"]) / 2 for c in visible])
    y = np.array([float(page.height) - c["matrix"][5] for c in visible])
    size = median(c["size"] for c in visible)
    angle = estimate_skew(x, y, options.max_skew, max(1.0, size * .2)) if options.deskew else 0.0
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    glyphs = []
    for char in chars:
        a, b, _, _, e, f = char["matrix"]
        base = float(page.height) - f
        direction = math.atan2(-b, a)
        # Project the baseline endpoints, not an axis-aligned rotated bbox.
        advance = abs(char.get("adv", char["width"])) * math.hypot(a, b)
        end_x, end_y = e + advance * math.cos(direction), base + advance * math.sin(direction)
        start = e * cosine + base * sine
        end = end_x * cosine + end_y * sine
        projected_y = -((e + end_x) / 2) * sine + ((base + end_y) / 2) * cosine
        # char.size is a vertical bbox extent; compensate for true text rotation.
        font_size = max(1.0, (char["size"] - abs(char.get("adv", 0) * b)) / max(.2, abs(a)))
        glyphs.append(Glyph(char["text"], min(start, end), max(start, end),
                            projected_y, font_size,
                            bool(re.search(r"bold|black|heavy|semibold", char["fontname"], re.I))))
    return glyphs, angle


def _line_from_glyphs(chars: list[Glyph]) -> Line:
    ordered = sorted(chars, key=lambda c: c.x0)
    gaps = [b.x0 - a.x1 for a, b in zip(ordered, ordered[1:])
            if a.text.strip() and b.text.strip()]
    normal_gap = max(0.0, median(gaps)) if gaps else 0.0
    text = ""
    previous = None
    for char in ordered:
        if previous and not text.endswith(" ") and not char.text.isspace():
            gap = char.x0 - previous.x1
            if gap > max(.7, min(previous.size, char.size) * .15, normal_gap * 2):
                text += " "
        text += char.text
        previous = char
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    sizes = [c.size for c in ordered if c.text.strip()]
    size = float(median(sizes)) if sizes else 10.0
    base = float(median(c.baseline for c in ordered))
    return Line(text, min(c.x0 for c in ordered), max(c.x1 for c in ordered),
                base - size, base, size,
                sum(len(c.text) for c in ordered if c.bold) / max(1, sum(len(c.text) for c in ordered)))


def _group_glyphs(glyphs: list[Glyph]) -> list[Line]:
    if not glyphs:
        return []
    typical = median(c.size for c in glyphs)
    tolerance = max(1.5, min(4.0, typical * .28))
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


def _column_cuts(lines: list[Line], mode: str) -> list[float]:
    if not lines or mode == "1":
        return []
    low, high = min(l.x0 for l in lines), max(l.x1 for l in lines)
    width = high - low
    if width < 50:
        return []
    if mode != "auto":
        return [low + width * n / int(mode) for n in range(1, int(mode))]
    # A gutter has many lines ending on its left and starting on its right,
    # with few prose lines crossing it. Full-width headings are permitted.
    body = [l for l in lines if len(l.text) > 18]
    if len(body) < 8:
        return []
    candidates = []
    for cut in np.linspace(low + width * .2, high - width * .2, 100):
        left = [l for l in body if l.x1 <= cut - 4]
        right = [l for l in body if l.x0 >= cut + 4]
        crossing = sum(l.x0 < cut < l.x1 for l in body)
        if min(len(left), len(right)) < 4 or crossing > len(body) * .12:
            continue
        # The columns must coexist vertically, rather than two indented blocks.
        overlap = min(max(l.bottom for l in left), max(l.bottom for l in right)) - max(min(l.top for l in left), min(l.top for l in right))
        if overlap < 4 * median(l.size for l in body):
            continue
        gutter = min(l.x0 for l in right) - max(l.x1 for l in left)
        if gutter >= 8:
            candidates.append((min(len(left), len(right)) - crossing * 3, gutter, float(cut)))
    if not candidates:
        return []
    best = max(candidates)[2]
    cuts = [best]
    # Detect a possible third column on either side of the strongest gutter.
    for subset in ([l for l in lines if l.x1 < best], [l for l in lines if l.x0 > best]):
        extra = _column_cuts(subset, "auto") if len(subset) < len(lines) and len(subset) >= 12 else []
        if extra:
            cuts.append(extra[0])
    return sorted(cuts)[:2]


def _reading_order(lines: list[Line], cuts: list[float]) -> list[Line]:
    if not cuts:
        return _coalesce_rows(lines)
    spanning = [l for l in lines if any(l.x0 < c - 4 and l.x1 > c + 4 for c in cuts)]
    rest = [l for l in lines if l not in spanning]
    result = []
    start = -math.inf
    for boundary in sorted(spanning, key=lambda l: l.top) + [None]:
        end = boundary.top if boundary else math.inf
        band = [l for l in rest if start <= l.top < end]
        for column in range(len(cuts) + 1):
            segment = [l for l in band if sum(l.x0 >= c for c in cuts) == column]
            result.extend(Line(**{**asdict(l), "column": column}) for l in _coalesce_rows(segment))
        if boundary:
            result.append(boundary)
            start = boundary.top
    return result


def _coalesce_rows(lines: list[Line]) -> list[Line]:
    """Reunite separated fragments after the actual column boundaries are known."""
    result: list[Line] = []
    for line in sorted(lines, key=lambda l: (l.bottom, l.x0)):
        if result and abs(result[-1].bottom - line.bottom) <= min(result[-1].size, line.size) * .28:
            previous = result.pop()
            left, right = sorted((previous, line), key=lambda l: l.x0)
            size = (previous.size * len(previous.text) + line.size * len(line.text)) / (len(previous.text) + len(line.text))
            result.append(Line(left.text + " " + right.text, min(left.x0, right.x0), max(left.x1, right.x1),
                               min(left.top, right.top), (left.bottom + right.bottom) / 2,
                               size, max(left.bold, right.bold), left.column))
        else:
            result.append(line)
    return result


def _find_tesseract(command: str | None) -> str:
    resolved = command or shutil.which("tesseract")
    windows = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
    if not resolved and windows.is_file():
        resolved = str(windows)
    if not resolved:
        raise RuntimeError("O pagină necesită OCR, dar Tesseract lipsește. Instalați Tesseract cu limbile cerute sau folosiți --ocr never.")
    return resolved


def _deskew_image(image, max_angle: float):
    from PIL import Image
    # Exclude outer scan borders and downsample for bounded angle estimation.
    small = image.convert("L")
    small.thumbnail((1000, 1000))
    values = np.asarray(small)
    h, w = values.shape
    mask = values[int(h*.1):int(h*.9), int(w*.1):int(w*.9)] < 150
    # Solid scanner borders are not text baselines.
    mask[:, mask.mean(axis=0) > .45] = False
    mask[mask.mean(axis=1) > .45, :] = False
    y, x = np.nonzero(mask)
    if len(x) < 100:
        return image, 0.0
    angle = estimate_skew(x.astype(float), y.astype(float), max_angle, 1.5, min_gain=1.005)
    # PIL uses counter-clockwise visual rotation; screen-coordinate skew has
    # the opposite sign convention to mathematical baseline rotation.
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white"), angle


def _ocr_glyphs(pdf_path: Path, page_index: int, options: Options) -> tuple[list[Glyph], float]:
    import pypdfium2
    command = _find_tesseract(options.tesseract_cmd)
    with pypdfium2.PdfDocument(pdf_path, password=options.password) as pdf:
        image = pdf[page_index].render(scale=options.dpi / 72).to_pil().convert("RGB")
    image, angle = _deskew_image(image, options.max_skew) if options.deskew else (image, 0.0)
    with tempfile.TemporaryDirectory(prefix="pdf-ocr-", dir=pdf_path.parent) as directory:
        path = Path(directory) / "page.png"
        image.save(path)
        process = subprocess.run([command, str(path), "stdout", "-l", options.lang, "--psm", "3", "tsv"],
                                 capture_output=True, encoding="utf-8", timeout=300, check=False)
    if process.returncode:
        raise RuntimeError(f"Tesseract a eșuat la pagina {page_index + 1}: {process.stderr.strip()}")
    scale = 72 / options.dpi
    glyphs = []
    rows = []
    for row in csv.DictReader(io.StringIO(process.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        x, y, w, h = (float(row[k]) * scale for k in ("left", "top", "width", "height"))
        key = tuple(row[k] for k in ("block_num", "par_num", "line_num"))
        rows.append((key, text, x, y, w, h))
    # Tesseract's word boxes have varying bottoms for descenders. Fit baselines
    # using its own line IDs, rather than guessing from each word's bottom.
    baselines: dict[tuple, list[float]] = {}
    for key, _, _, y, _, h in rows:
        baselines.setdefault(key, []).append(y + h)
    for key, text, x, _, w, h in rows:
        glyphs.append(Glyph(text + " ", x, x + w, median(baselines[key]), max(1.0, h)))
    return glyphs, angle


def _heading_level(line: Line, profile: Profile, body: float, gap: float,
                   prose_width: float = math.inf) -> int | None:
    text = line.text
    if len(text) > 180 or not any(c.isalpha() for c in text) or BULLET.match(text) or TOC.search(text):
        return None
    if _canonical(text) in profile.outlines:
        return profile.outlines[_canonical(text)]
    if PART.match(text) and not text.endswith(("-", ",", ".")) and (len(text) < 55 or line.size > body * 1.15):
        return 2
    if CHAPTER.match(text) and not text.endswith(("-", ",", ".")) and (len(text) < 55 or line.size > body * 1.15):
        return 3 if profile.parts else 2
    numbered = NUMBERED.match(text)
    styled = line.size >= body * 1.08 or line.bold >= .6
    if numbered and len(text) < 120 and (styled or gap > body * .5):
        return min(6, 2 + numbered.group(1).count("."))
    if text.endswith((".", ":", ";", "!", "?")) and not styled:
        return None
    if line.size >= body * 1.35:
        return 2
    if _all_caps(text) and len(text) < 130 and not text.endswith((".", ";", "!", "?")):
        return 3 if line.size < body * 1.2 else 2
    if _short_title(text) and profile.labels[_canonical(text)] >= 4:
        return 4
    if (not text.endswith((".", ":", ";", "!", "?", "-")) and math.isfinite(gap) and gap > body * 1.25
            and text[:1].isupper() and len(text.split()) <= 16 and len(text) < 150):
        return 3
    if (len(text) > 50 and line.x1 - line.x0 > prose_width * .8
            and line.size < body * 1.18 and line.bold < .6):
        return None
    if (styled and not text.endswith((".", ":", ";", "!", "?", "-"))
            and (line.bold >= .6 or line.size >= body * 1.18
                 or gap > body * .7 and len(text) < 150)):
        return 3
    return None


def _join_text(previous: str, text: str) -> str:
    if previous.endswith("-") and text[:1].isalpha():
        return previous[:-1] + text
    return previous + " " + text


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
    edge_threshold = max(3, math.ceil(profile.pages * .015))
    edge_indexes = {i for i, line in enumerate(lines) if line in _edge_lines(lines)} | {len(lines) - 1}
    for index in edge_indexes:
        line = lines[index]
        if re.fullmatch(r"[\s–—-]*\d+[\s–—-]*", line.text):
            removed.add(index)
        elif (profile.margins[_margin_key(line.text)] >= edge_threshold
              and profile.margins[_margin_key(line.text)] >= profile.occurrences[_margin_key(line.text)] * .75
              and line.size < body * 1.12 and _margin_key(line.text)):
            removed.add(index)
    blocks: list[tuple[str, int | None]] = []
    paragraph = ""
    previous = None
    heading_count = 0

    def flush():
        nonlocal paragraph
        if paragraph:
            blocks.append((paragraph, None))
            paragraph = ""

    for index, line in enumerate(lines):
        if index in removed:
            continue
        gap = line.top - previous.bottom if previous and previous.column == line.column else math.inf
        column_changed = previous is not None and previous.column != line.column
        level = _heading_level(line, profile, body, gap, prose_width)
        if len(lines) <= 3 and _all_caps(line.text):
            level = 2
        if (level is None and blocks and blocks[-1][1] is not None and not paragraph
                and previous is not None
                and (previous.text.endswith((",", "-", "(")) or previous.text.count("(") > previous.text.count(")"))
                and gap < body * .6 and not column_changed
                and len(line.text) < 120 and abs(previous.size - line.size) < body * .1):
            level = blocks[-1][1]
        text = line.text.replace("#", r"\#")
        bullet = BULLET.match(text)
        if level:
            flush()
            # Wrapped headings with the same style form a single Markdown title.
            if (blocks and blocks[-1][1] == level and previous is not None
                    and gap < body * .6 and not column_changed
                    and abs(previous.size - line.size) < body * .1
                    and not CHAPTER.match(text) and not PART.match(text)):
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
            if column_changed or gap > body * .65:
                flush()
            if (blocks and blocks[-1][0].startswith("- ") and not paragraph
                    and gap < body * .6 and previous is not None
                    and line.x0 <= previous.x0 + body
                    and not (previous.text.endswith((".", ";", "!", "?")) and line.text[:1].isupper())):
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


def extract_markdown(pdf_path: Path, output_path: Path, options: Options | None = None,
                     report_path: Path | None = None) -> tuple[int, int]:
    options = options or Options()
    pdf_path, output_path = pdf_path.resolve(), output_path.resolve()
    if pdf_path == output_path or report_path and report_path.resolve() in {pdf_path, output_path}:
        raise ValueError("Sursa PDF, Markdown și raportul trebuie să aibă căi diferite.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = last_log = time.monotonic()
    profile = Profile()
    report = {"source": str(pdf_path), "pages": [], "headings": 0, "characters": 0,
              "warnings": ["Ierarhia titlurilor este dedusă euristic; verificați rezultatul pentru documente complexe."]}
    # Spool lightweight line records, freeing PDF caches after every page.
    # A failed extraction never replaces an existing output.
    with tempfile.TemporaryDirectory(prefix="pdf-markdown-", dir=output_path.parent) as directory:
        spool = Path(directory) / "pages.jsonl"
        with pdfplumber.open(pdf_path, password=options.password) as document, spool.open("w", encoding="utf-8") as records:
            try:
                for level, title, *_ in document.doc.get_outlines():
                    if isinstance(title, bytes):
                        title = title.decode("utf-8", errors="replace")
                    profile.outlines[_canonical(title)] = min(6, int(level) + 1)
            except PDFNoOutlines:
                pass
            total = len(document.pages)
            end = options.end_page if options.end_page is not None else total
            if not 1 <= options.start_page <= end <= total:
                raise ValueError(f"Interval invalid; documentul are {total} pagini.")
            count = end - options.start_page + 1
            print(f"Analiză: {count} pagini; coloane={options.columns}, OCR={options.ocr}, deskew={options.deskew}", file=sys.stderr, flush=True)
            for number in range(options.start_page, end + 1):
                page = document.pages[number - 1]
                glyphs, angle = _text_glyphs(page, options) if options.ocr != "always" else ([], 0.0)
                method = "text"
                if not glyphs and options.ocr != "never":
                    glyphs, angle = _ocr_glyphs(pdf_path, number - 1, options)
                    method = "ocr"
                lines = _group_glyphs(glyphs)
                cuts = _column_cuts(lines, options.columns)
                lines = _reading_order(lines, cuts)
                profile.observe(lines)
                records.write(json.dumps({"number": number, "lines": [asdict(l) for l in lines]}, ensure_ascii=False) + "\n")
                report["pages"].append({"page": number, "method": method, "skew_degrees": round(angle, 2),
                                        "columns": len(cuts) + 1, "lines": len(lines)})
                if not lines:
                    report["warnings"].append(f"Pagina {number}: fără text detectabil ({method}).")
                page.close()
                now = time.monotonic()
                if now - last_log >= 10 or number == end:
                    done = number - options.start_page + 1
                    rate = done / max(.001, now - started)
                    print(f"{done}/{count} ({done/count:.1%}), {rate:.2f} pagini/s, timp={now-started:.0f}s, ETA={(count-done)/rate:.0f}s", file=sys.stderr, flush=True)
                    last_log = now
        staged = Path(directory) / "output.md"
        with staged.open("w", encoding="utf-8", newline="\n") as output, spool.open(encoding="utf-8") as records:
            output.write(f"# {pdf_path.stem}\n\n<!-- Text extras local. Titluri deduse din aspect și numerotare; grafia sursei este păstrată. -->\n")
            for record in records:
                data = json.loads(record)
                text, headings = _render_page([Line(**line) for line in data["lines"]], profile)
                output.write(f"\n\n<!-- Pagina PDF {data['number']} -->\n\n{text}\n")
                report["headings"] += headings
                report["characters"] += len(text)
        staged.replace(output_path)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Titluri: {report['headings']}; pagini fără text: {sum(p['lines'] == 0 for p in report['pages'])}", file=sys.stderr, flush=True)
    return profile.pages, report["characters"]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Implicit: lângă PDF, cu extensia .md")
    parser.add_argument("--columns", choices=("auto", "1", "2", "3"), default="auto")
    parser.add_argument("--ocr", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--lang", default="ron+eng")
    parser.add_argument("--dpi", type=int, default=250)
    parser.add_argument("--deskew", choices=("auto", "off"), default="auto")
    parser.add_argument("--max-skew", type=float, default=30.0)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--tesseract-cmd")
    parser.add_argument("--password")
    parser.add_argument("--report", type=Path, help="Raport JSON: unghi, coloane, OCR și avertismente pe pagină")
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"Fișierul PDF nu există: {args.pdf}")
    if not 0 <= args.max_skew <= 30 or not 72 <= args.dpi <= 600:
        parser.error("--max-skew trebuie să fie între 0 și 30; --dpi între 72 și 600.")
    options = Options(args.columns, args.ocr, args.lang, args.dpi, args.deskew == "auto",
                      args.max_skew, args.start_page, args.end_page, args.tesseract_cmd, args.password)
    try:
        pages, characters = extract_markdown(args.pdf, args.output or args.pdf.with_suffix(".md"), options, args.report)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Extragerea a eșuat: {exc}\n")
    print(f"Scris: {(args.output or args.pdf.with_suffix('.md')).resolve()}\nPagini: {pages}; caractere: {characters}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
