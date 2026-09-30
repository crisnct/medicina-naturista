"""Readable Romanian PDF report with source references next to each claim."""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from medicina_naturista.ai.conditions import find_conditions, resolve_query

SECTION_KEYS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")

TEXT_COLOR = "#203139"
MUTED_TEXT_COLOR = "#52636D"
SOURCE_COLOR = "#0F5C5E"
SECTION_PRESENTATION = {
    "uz_intern": {"number": "1", "label": "Uz intern", "color": "#087F73"},
    "nutritie": {"number": "2", "label": "Nutriție", "color": "#B7791F"},
    "uz_extern": {"number": "3", "label": "Uz extern", "color": "#3973B9"},
    "alte_recomandari": {"number": "4", "label": "Alte recomandări", "color": "#8059A5"},
    "atentionari": {"number": "5", "label": "Atenționări", "color": "#B8423E"},
}

FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
BOLD_CANDIDATES = (
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)
# The same portrait the web UI uses (a single copy of the file).
DOCTOR_IMAGE = Path(__file__).resolve().parents[1] / "web" / "static" / "images" / "dr-cuisor.webp"
# Same botanical ornament, widened so the left and right clusters reach the page edges.
ORNAMENT_PNG = (
    Path(__file__).resolve().parent / "assets" / "ornament-fitoterapie-antet-wide.png"
)
ORNAMENT_SIZE = (2621, 724)


# Locate Unicode fonts, register them with ReportLab, and return their names.
def _register_fonts() -> tuple[str, str]:
    normal = next((path for path in FONT_CANDIDATES if path.is_file()), None)
    bold = next((path for path in BOLD_CANDIDATES if path.is_file()), None)
    if normal is None or bold is None:
        raise RuntimeError("Nu există font Unicode pentru generarea PDF-ului.")
    if "NaturistRegular" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NaturistRegular", str(normal)))
    if "NaturistBold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NaturistBold", str(bold)))
    pdfmetrics.registerFontFamily("NaturistRegular", normal="NaturistRegular", bold="NaturistBold", italic="NaturistRegular", boldItalic="NaturistBold")
    return "NaturistRegular", "NaturistBold"


def _draw_footer(canvas: Any, document: Any) -> None:
    """Draw the shared footer without interfering with the reading order."""
    canvas.saveState()
    canvas.setFont("NaturistRegular", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(18 * mm, 12 * mm, "Remedii naturiste de la Dr. Cuișor")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Pagina {document.page}")
    canvas.restoreState()


def _draw_botanical_motif(canvas: Any, origin_x: float, origin_y: float, scale: float = 1.0) -> None:
    """Draw a layered botanical illustration; it is decorative only."""
    canvas.saveState()
    canvas.setLineWidth(1.25 * scale)
    canvas.setStrokeColor(colors.HexColor("#BFE8CF"))
    main_stem = canvas.beginPath()
    main_stem.moveTo(origin_x, origin_y)
    main_stem.curveTo(
        origin_x + 9 * mm * scale, origin_y + 7 * mm * scale,
        origin_x + 16 * mm * scale, origin_y + 19 * mm * scale,
        origin_x + 31 * mm * scale, origin_y + 28 * mm * scale,
    )
    canvas.drawPath(main_stem, stroke=1, fill=0)
    branch = canvas.beginPath()
    branch.moveTo(origin_x + 14 * mm * scale, origin_y + 14 * mm * scale)
    branch.curveTo(
        origin_x + 10 * mm * scale, origin_y + 21 * mm * scale,
        origin_x + 8 * mm * scale, origin_y + 26 * mm * scale,
        origin_x + 6 * mm * scale, origin_y + 31 * mm * scale,
    )
    canvas.drawPath(branch, stroke=1, fill=0)
    leaves = (
        (6, 6, 38, 1.00), (11, 11, -38, 0.92), (17, 17, 38, 1.05),
        (23, 22, -38, 0.92), (29, 27, 35, 0.86), (8, 26, -30, 0.72),
    )
    for offset_x, offset_y, angle, leaf_scale in leaves:
        x = origin_x + offset_x * mm * scale
        y = origin_y + offset_y * mm * scale
        canvas.saveState()
        canvas.translate(x, y)
        canvas.rotate(angle)
        canvas.setFillColor(colors.HexColor("#91D0AB"))
        canvas.setStrokeColor(colors.HexColor("#D7F2E1"))
        canvas.ellipse(
            -3.2 * mm * scale * leaf_scale,
            0,
            3.2 * mm * scale * leaf_scale,
            8.4 * mm * scale * leaf_scale,
            stroke=1,
            fill=1,
        )
        canvas.setStrokeColor(colors.HexColor("#5FAE87"))
        canvas.line(0, 0.6 * mm * scale, 0, 7.3 * mm * scale * leaf_scale)
        canvas.restoreState()
    canvas.restoreState()


def _first_page(canvas: Any, document: Any) -> None:
    """Draw the SVG-derived botanical ornament behind the first-page content."""
    canvas.saveState()
    width, height = A4
    header_height = 76 * mm
    canvas.setFillColor(colors.HexColor("#F4F9F7"))
    canvas.rect(0, height - header_height, width, header_height, stroke=0, fill=1)
    if ORNAMENT_PNG.is_file():
        ornament_width = width
        ornament_height = ornament_width * ORNAMENT_SIZE[1] / ORNAMENT_SIZE[0]
        canvas.setFillAlpha(0.34)
        canvas.drawImage(
            ImageReader(str(ORNAMENT_PNG)),
            0,
            height - header_height,
            width=ornament_width,
            height=ornament_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.setFillAlpha(1)
    canvas.restoreState()
    _draw_footer(canvas, document)


def _later_page(canvas: Any, document: Any) -> None:
    """Keep later pages calm while retaining the cover's botanical identity."""
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(colors.HexColor("#F4F9F7"))
    canvas.circle(width - 16 * mm, height - 16 * mm, 7 * mm, stroke=0, fill=1)
    canvas.restoreState()
    _draw_footer(canvas, document)


class BookmarkedParagraph(Paragraph):
    """Paragraph carrying a named destination and an outline entry for PDF readers."""

    def __init__(self, text: str, style: ParagraphStyle, bookmark: str | None = None, outline: str | None = None):
        super().__init__(text, style)
        self.bookmark = bookmark
        self.outline = outline


class CoverPanel(Flowable):
    """Reserve the cover band and vertically center its readable content."""

    def __init__(
        self,
        content: list[Flowable],
        visible_height: float,
        page_top_extension: float,
        image_path: Path | None = None,
        image_size: float = 0.0,
    ) -> None:
        super().__init__()
        self.content = content
        self.visible_height = visible_height
        self.page_top_extension = page_top_extension
        self.image_path = image_path
        self.image_size = image_size if image_path and image_path.is_file() else 0.0
        self.image_gap = 6 * mm
        self._metrics: list[tuple[Flowable, float, float, float]] = []

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        self.height = self.visible_height
        self._metrics = []
        for flowable in self.content:
            # Content next to the portrait wraps before it; the rest uses the full width.
            beside = self.image_size and getattr(flowable, "beside_image", False)
            width = available_width - self.image_size - self.image_gap if beside else available_width
            _, height = flowable.wrap(width, 1_000_000)
            self._metrics.append((
                flowable,
                flowable.getSpaceBefore(),
                height,
                flowable.getSpaceAfter(),
            ))
        return available_width, self.height

    def draw(self) -> None:
        total_height = sum(
            space_before + height + space_after
            for _, space_before, height, space_after in self._metrics
        )
        full_band_height = self.visible_height + self.page_top_extension
        y = (full_band_height + total_height) / 2
        if self.image_size:
            self.canv.drawImage(
                str(self.image_path),
                self.width - self.image_size,
                y - self.image_size,
                width=self.image_size,
                height=self.image_size,
                mask="auto",
            )
        for flowable, space_before, height, space_after in self._metrics:
            y -= space_before + height
            flowable.drawOn(self.canv, 0, y)
            y -= space_after


class RoundedSection(Flowable):
    """A splittable white card with a colored heading and matching outline."""

    def __init__(
        self,
        content: list[Flowable],
        background: str,
        border: str,
        bookmark: str | None = None,
        outline: str | None = None,
    ) -> None:
        super().__init__()
        self.content = content
        self.background_hex = background
        self.border_hex = border
        self.background = colors.HexColor(background)
        self.border = colors.HexColor(border)
        self.bookmark = bookmark
        self.outline = outline
        self.padding = 7
        self.radius = 11
        self._metrics: list[tuple[Flowable, float, float, float]] = []
        self._height = 0.0
        self._inner_width = 0.0

    def _measure(self, available_width: float) -> list[tuple[Flowable, float, float, float]]:
        inner_width = max(1, available_width - 2 * self.padding)
        measurements: list[tuple[Flowable, float, float, float]] = []
        for flowable in self.content:
            _, height = flowable.wrap(inner_width, 1_000_000)
            measurements.append((
                flowable,
                flowable.getSpaceBefore(),
                height,
                flowable.getSpaceAfter(),
            ))
        return measurements

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        self.width = available_width
        self._inner_width = max(1, available_width - 2 * self.padding)
        self._metrics = self._measure(available_width)
        self._height = 2 * self.padding + sum(
            space_before + height + space_after
            for _, space_before, height, space_after in self._metrics
        )
        return available_width, self._height

    def split(self, available_width: float, available_height: float) -> list[Flowable]:
        capacity = available_height - 2 * self.padding
        if capacity <= 0:
            return []
        metrics = self._measure(available_width)
        first_content: list[Flowable] = []
        remainder: list[Flowable] = []
        for index, (flowable, space_before, height, space_after) in enumerate(metrics):
            required = space_before + height + space_after
            if required <= capacity:
                first_content.append(flowable)
                capacity -= required
                continue

            split_height = capacity - space_before - space_after
            parts = flowable.split(max(1, available_width - 2 * self.padding), max(0, split_height))
            if parts:
                first_content.append(parts[0])
                remainder.extend(parts[1:])
            else:
                remainder.append(flowable)
            remainder.extend(item for item, _, _, _ in metrics[index + 1:])
            break

        # Keep the colored heading, its white breathing room, and at least one
        # content item together when a card starts near the bottom of a page.
        heading_would_be_orphaned = self.bookmark and len(first_content) <= 2 and remainder
        continuation_cannot_start = not self.bookmark and len(first_content) == 1 and remainder
        if not first_content or heading_would_be_orphaned or continuation_cannot_start:
            return []
        first = RoundedSection(
            first_content,
            self.background_hex,
            self.border_hex,
            bookmark=self.bookmark,
            outline=self.outline,
        )
        first.wrap(available_width, available_height)
        if not remainder:
            return [first]
        continuation = RoundedSection(remainder, self.background_hex, self.border_hex)
        return [first, continuation]

    def draw(self) -> None:
        self.canv.saveState()
        self.canv.setFillColor(colors.white)
        self.canv.setStrokeColor(self.border)
        self.canv.setLineWidth(1.0)
        self.canv.roundRect(0, 0, self.width, self._height, self.radius, stroke=1, fill=1)
        if self.bookmark and self._metrics:
            _, heading_before, heading_height, heading_after = self._metrics[0]
            header_height = self.padding + heading_before + heading_height + heading_after
            header_y = self._height - header_height
            self.canv.setFillColor(self.border)
            self.canv.roundRect(
                0, header_y, self.width, header_height, self.radius, stroke=0, fill=1
            )
            self.canv.rect(0, header_y, self.width, self.radius, stroke=0, fill=1)
            self.canv.setStrokeColor(self.border)
            self.canv.setLineWidth(1.0)
            self.canv.roundRect(0, 0, self.width, self._height, self.radius, stroke=1, fill=0)
        y = self._height - self.padding
        for flowable, space_before, height, space_after in self._metrics:
            y -= space_before + height
            flowable.drawOn(self.canv, self.padding, y)
            y -= space_after
        self.canv.restoreState()


class NatureReportDocTemplate(SimpleDocTemplate):
    """A document template that turns visual section headings into PDF bookmarks."""

    def afterFlowable(self, flowable: Any) -> None:
        bookmark = getattr(flowable, "bookmark", None)
        if not bookmark:
            return
        self.canv.bookmarkPage(bookmark)
        outline = getattr(flowable, "outline", None)
        if outline:
            self.canv.addOutlineEntry(outline, bookmark, level=0, closed=False)


# Assign stable bibliography numbers to cited internal sources in display order.
def build_reference_index(
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, str]],
) -> tuple[dict[str, int], list[str]]:
    """Assign one stable number to each cited internal source, by first appearance."""
    numbers: dict[str, int] = {}
    references: list[str] = []
    for section in SECTION_KEYS:
        for item in sections.get(section) or []:
            for token in item.get("evidence_ids", []):
                if token not in evidence:
                    continue
                source = evidence[token]["source"]
                if source not in numbers:
                    references.append(source)
                    numbers[source] = len(references)
    return numbers, references


# Sort every report section by the best relevance_percent among the fragments it cites,
# then by descending count of distinct cited sources, then by original position.
def sort_sections_by_relevance(
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Order every section by the highest relevance_percent of the fragments each item cites."""

    def sort_key(pair: tuple[int, dict[str, Any]]) -> tuple[float, int, int]:
        index, item = pair
        tokens = [token for token in item.get("evidence_ids", []) if token in evidence]
        best_relevance = max(
            (float(evidence[token].get("relevance_percent", 0.0)) for token in tokens),
            default=float("-inf"),
        )
        source_count = len({evidence[token]["source"] for token in tokens})
        return (-best_relevance, -source_count, index)

    ordered: dict[str, list[dict[str, Any]]] = {}
    for section, items in sections.items():
        indexed_items = sorted(enumerate(items), key=sort_key)
        ordered[section] = [item for _, item in indexed_items]
    return ordered


# Group nutrition claims into the fixed display order and split recipes into separate items.
def nutrition_display_groups(
    items: list[dict[str, Any]],
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Return nutrition claims grouped in the required order for UI and PDF rendering."""
    groups: dict[str, list[dict[str, Any]]] = {
        "recipes": [],
        "recommended": [],
        "not_recommended": [],
        "forbidden": [],
        "other": [],
    }
    category_pattern = re.compile(
        r"(?<!\w)(rețete culinare|alimente recomandate|alimente nerecomandate|"
        r"alimente n?interzise|alte recomandări nutriționale)\s*:?\s*",
        re.IGNORECASE,
    )
    prefix_pattern = re.compile(
        r"(?<!\w)(?:\*\*)?\[(RETETA|RECOMANDAT|NERECOMANDAT|INTERZIS|ALTE)\]"
        r"(?:\*\*)?\s*:?\s*",
        re.IGNORECASE,
    )
    prefix_names = {
        "reteta": "recipes",
        "recomandat": "recommended",
        "nerecomandat": "not_recommended",
        "interzis": "forbidden",
        "alte": "other",
    }
    category_names = {
        "rețete culinare": "recipes",
        "alimente recomandate": "recommended",
        "alimente nerecomandate": "not_recommended",
        "alimente interzise": "forbidden",
        "alimente ninterzise": "forbidden",
        "alte recomandări nutriționale": "other",
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_text = str(item.get("text") or "").replace("\r\n", "\n").strip()
        if not raw_text:
            continue
        text = re.sub(r"^\s*[-•]\s*", "", raw_text)
        evidence_ids = [token for token in item.get("evidence_ids", []) if isinstance(token, str)]
        prefix_matches = list(prefix_pattern.finditer(text))
        matches = prefix_matches or list(category_pattern.finditer(text))
        if matches:
            blocks = [
                (
                    prefix_names[match.group(1).casefold()]
                    if prefix_matches
                    else category_names[match.group(1).casefold()],
                    text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip(),
                )
                for index, match in enumerate(matches)
            ]
        else:
            blocks = [("other", text)]
        for category, content in blocks:
            if content.strip(" -•\n\t") == "":
                continue
            if category == "recipes":
                recipe_parts = re.split(
                    r"(?:^|\n)\s*[-•]\s*|\s+-\s+(?=[A-ZĂÂÎȘȚ0-9])",
                    content,
                )
                for recipe in recipe_parts:
                    recipe = " ".join(recipe.split())
                    if recipe and recipe != "-":
                        groups[category].append({"text": recipe, "evidence_ids": evidence_ids})
                continue
            groups[category].append({
                "text": "\n".join(line.strip() for line in content.split("\n") if line.strip()),
                "evidence_ids": evidence_ids,
            })
    labels = (
        ("recipes", "Rețete culinare"),
        ("recommended", "Alimente recomandate"),
        ("not_recommended", "Alimente nerecomandate"),
        ("forbidden", "Alimente total interzise"),
        ("other", "Alte recomandări"),
    )
    return [(key, label, groups[key]) for key, label in labels]


# Remove the internal documents prefix from a source label shown to users.
def bibliography_label(source: str) -> str:
    """Show the internal file and line range without the redundant documents/ prefix."""
    return source.removeprefix("documents/")


_ROMANIAN_DIACRITIC_WORDS = {
    "gripa": "gripă",
    "raceala": "răceală",
    "tuse": "tuse",
    "febra": "febră",
    "durere": "durere",
    "dureri": "dureri",
    "gat": "gât",
    "inflamatie": "inflamație",
    "inflamatii": "inflamații",
    "articulatie": "articulație",
    "articulatii": "articulații",
    "alergie": "alergie",
    "alergii": "alergii",
    "sinuzita": "sinuzită",
    "bronsita": "bronșită",
    "insomnie": "insomnie",
    "sanatate": "sănătate",
    "si": "și",
}


# Romanian spelling of the words in the canonical condition names
# (data/medical_conditions.txt is written without diacritics).
_CONDITION_DIACRITIC_WORDS = {
    "acidoza": "acidoză",
    "actinomicoza": "actinomicoză",
    "acuta": "acută",
    "adenomioza": "adenomioză",
    "afectiva": "afectivă",
    "agranulocitoza": "agranulocitoză",
    "albina": "albină",
    "alcaloza": "alcaloză",
    "alergica": "alergică",
    "alimentara": "alimentară",
    "alimentatie": "alimentație",
    "amebiaza": "amebiază",
    "amigdalita": "amigdalită",
    "amiloidoza": "amiloidoză",
    "amiotrofica": "amiotrofică",
    "amorteala": "amorțeală",
    "anchilozanta": "anchilozantă",
    "androgenetica": "androgenetică",
    "angina": "angină",
    "antitripsina": "antitripsină",
    "aortica": "aortică",
    "apendicita": "apendicită",
    "aplastica": "aplastică",
    "areata": "areată",
    "arsura": "arsură",
    "arteriala": "arterială",
    "arterioscleroza": "arterioscleroză",
    "arterita": "arterită",
    "articulatiei": "articulației",
    "artrita": "artrită",
    "artroza": "artroză",
    "ascaridioza": "ascaridioză",
    "ascita": "ascită",
    "asociata": "asociată",
    "aspergiloza": "aspergiloză",
    "aspirina": "aspirină",
    "ateroscleroza": "ateroscleroză",
    "atriala": "atrială",
    "autoimuna": "autoimună",
    "avitaminoza": "avitaminoză",
    "axiala": "axială",
    "balbaiala": "bâlbâială",
    "bataturi": "bătături",
    "batranete": "bătrânețe",
    "biliara": "biliară",
    "bipolara": "bipolară",
    "blefarita": "blefarită",
    "boala": "boală",
    "boreliozica": "boreliozică",
    "bronsic": "bronșic",
    "bronsita": "bronșită",
    "caderea": "căderea",
    "caine": "câine",
    "calcaie": "călcâie",
    "calda": "caldă",
    "candidoza": "candidoză",
    "cangrena": "cangrenă",
    "capsuni": "căpșuni",
    "cardiaca": "cardiacă",
    "cataracta": "cataractă",
    "celiaca": "celiacă",
    "celulita": "celulită",
    "cerebrala": "cerebrală",
    "cetoacidoza": "cetoacidoză",
    "chistica": "chistică",
    "cifoza": "cifoză",
    "circulatie": "circulație",
    "ciroza": "ciroză",
    "cistita": "cistită",
    "colecistita": "colecistită",
    "colibaciloza": "colibaciloză",
    "colica": "colică",
    "colita": "colită",
    "congenitala": "congenitală",
    "conjunctivita": "conjunctivită",
    "constipatie": "constipație",
    "convulsiva": "convulsivă",
    "coptura": "coptură",
    "coronariana": "coronariană",
    "coxartroza": "coxartroză",
    "crapate": "crăpate",
    "cronica": "cronică",
    "deficitara": "deficitară",
    "degenerescenta": "degenerescență",
    "degeraturi": "degerături",
    "dementa": "demență",
    "dentara": "dentară",
    "dependenta": "dependență",
    "dermatita": "dermatită",
    "diabetica": "diabetică",
    "diseritropoietica": "diseritropoietică",
    "disfunctie": "disfuncție",
    "diverticulita": "diverticulită",
    "dobandita": "dobândită",
    "drepanocitara": "drepanocitară",
    "eczema": "eczemă",
    "edera": "iederă",
    "eliptocitoza": "eliptocitoză",
    "encefalita": "encefalită",
    "encefalomielita": "encefalomielită",
    "endocardita": "endocardită",
    "endometrioza": "endometrioză",
    "enterocolita": "enterocolită",
    "enteropatica": "enteropatică",
    "entorsa": "entorsă",
    "epicondilita": "epicondilită",
    "eritroblastopenica": "eritroblastopenică",
    "eritrocitara": "eritrocitară",
    "eructatii": "eructații",
    "escara": "escară",
    "excesiva": "excesivă",
    "externa": "externă",
    "extrauterina": "extrauterină",
    "faciala": "facială",
    "falciforma": "falciformă",
    "faringita": "faringită",
    "febra": "febră",
    "feripriva": "feriprivă",
    "fibrilatie": "fibrilație",
    "fibrochistica": "fibrochistică",
    "fibroza": "fibroză",
    "fistula": "fistulă",
    "fisura": "fisură",
    "flebita": "flebită",
    "fractura": "fractură",
    "fructoza": "fructoză",
    "gastrica": "gastrică",
    "gastrita": "gastrită",
    "gastroenterita": "gastroenterită",
    "gestational": "gestațional",
    "giardiaza": "giardiază",
    "gingivita": "gingivită",
    "gonartroza": "gonartroză",
    "gonococica": "gonococică",
    "grasa": "grasă",
    "grau": "grâu",
    "greata": "greață",
    "greturi": "grețuri",
    "gripa": "gripă",
    "gusa": "gușă",
    "guta": "gută",
    "gutoasa": "gutoasă",
    "halitoza": "halitoză",
    "hemoglobina": "hemoglobină",
    "hemolitica": "hemolitică",
    "hemoragica": "hemoragică",
    "hepatica": "hepatică",
    "hepatita": "hepatită",
    "hiatala": "hiatală",
    "hiperregenerativa": "hiperregenerativă",
    "hipocroma": "hipocromă",
    "hipoplastica": "hipoplastică",
    "hiporegenerativa": "hiporegenerativă",
    "holera": "holeră",
    "idiopatica": "idiopatică",
    "incontinenta": "incontinență",
    "infectie": "infecție",
    "infectii": "infecții",
    "infectioasa": "infecțioasă",
    "inghinala": "inghinală",
    "insolatie": "insolație",
    "instabila": "instabilă",
    "insuficienta": "insuficiență",
    "insulina": "insulină",
    "intepatura": "înțepătură",
    "interfalangiana": "interfalangiană",
    "intoleranta": "intoleranță",
    "intoxicatie": "intoxicație",
    "izoimuna": "izoimună",
    "juvenila": "juvenilă",
    "kinaza": "kinază",
    "lactoza": "lactoză",
    "laringita": "laringită",
    "laterala": "laterală",
    "lauzie": "lăuzie",
    "litiaza": "litiază",
    "lupica": "lupică",
    "luxatie": "luxație",
    "macrocitara": "macrocitară",
    "maculara": "maculară",
    "mahmureala": "mahmureală",
    "mainii": "mâinii",
    "malabsorbtie": "malabsorbție",
    "malnutritie": "malnutriție",
    "mastita": "mastită",
    "matreata": "mătreață",
    "meningita": "meningită",
    "menopauza": "menopauză",
    "menstruatii": "menstruații",
    "micoza": "micoză",
    "microangiopatica": "microangiopatică",
    "microcitara": "microcitară",
    "migrena": "migrenă",
    "miocardita": "miocardită",
    "miozita": "miozită",
    "miscare": "mișcare",
    "mononucleoza": "mononucleoză",
    "multipla": "multiplă",
    "multisistemica": "multisistemică",
    "muscatura": "mușcătură",
    "musculara": "musculară",
    "mustar": "muștar",
    "mutilanta": "mutilantă",
    "nastere": "naștere",
    "nazala": "nazală",
    "nediferentiata": "nediferențiată",
    "nervoasa": "nervoasă",
    "nevrita": "nevrită",
    "nevroza": "nevroză",
    "nodala": "nodală",
    "non-sferocitara": "non-sferocitară",
    "normocitara": "normocitară",
    "normocroma": "normocromă",
    "obstructiva": "obstructivă",
    "oligoarticulara": "oligoarticulară",
    "onicomicoza": "onicomicoză",
    "ortostatica": "ortostatică",
    "osoasa": "osoasă",
    "osteomielita": "osteomielită",
    "osteoporoza": "osteoporoză",
    "otita": "otită",
    "otravitoare": "otrăvitoare",
    "oxiuroza": "oxiuroză",
    "paianjen": "păianjen",
    "palpitatii": "palpitații",
    "pancreatita": "pancreatită",
    "panica": "panică",
    "par": "păr",
    "parestezica": "parestezică",
    "parodontoza": "parodontoză",
    "parului": "părului",
    "pectorala": "pectorală",
    "pediculoza": "pediculoză",
    "penicilina": "penicilină",
    "pericardita": "pericardită",
    "periferica": "periferică",
    "peritonita": "peritonită",
    "pernicioasa": "pernicioasă",
    "peste": "pește",
    "pielonefrita": "pielonefrită",
    "pigmentara": "pigmentară",
    "piridoxina": "piridoxină",
    "pisica": "pisică",
    "poliarticulara": "poliarticulară",
    "poliartriculara": "poliarticulară",
    "poliomielita": "poliomielită",
    "postenterica": "postenterică",
    "posthemoragica": "posthemoragică",
    "postinfectioasa": "postinfecțioasă",
    "postnatala": "postnatală",
    "posturala": "posturală",
    "prematura": "prematură",
    "profunda": "profundă",
    "prostata": "prostată",
    "prostatita": "prostatită",
    "psihoza": "psihoză",
    "psoriazica": "psoriazică",
    "purpura": "purpură",
    "raceala": "răceală",
    "radiatii": "radiații",
    "rau": "rău",
    "reactiva": "reactivă",
    "refractara": "refractară",
    "renala": "renală",
    "retentie": "retenție",
    "retina": "retină",
    "retinita": "retinită",
    "reumatica": "reumatică",
    "reumatoida": "reumatoidă",
    "rezistenta": "rezistență",
    "rinita": "rinită",
    "rosii": "roșii",
    "rubeola": "rubeolă",
    "sacroiliaca": "sacroiliacă",
    "salmoneloza": "salmoneloză",
    "san": "sân",
    "sarcina": "sarcină",
    "sarcoidoza": "sarcoidoză",
    "sarpe": "șarpe",
    "scarlatina": "scarlatină",
    "scazut": "scăzut",
    "scazuta": "scăzută",
    "sciatica": "sciatică",
    "scleroza": "scleroză",
    "scolioza": "scolioză",
    "septica": "septică",
    "seronegativa": "seronegativă",
    "seropozitiva": "seropozitivă",
    "severa": "severă",
    "sexuala": "sexuală",
    "sezoniera": "sezonieră",
    "sfarcuri": "sfârcuri",
    "sferocitoza": "sferocitoză",
    "sforait": "sforăit",
    "sincopa": "sincopă",
    "sinusala": "sinusală",
    "sinuzita": "sinuzită",
    "sistemica": "sistemică",
    "solara": "solară",
    "spinala": "spinală",
    "spondilita": "spondilită",
    "spondiloza": "spondiloză",
    "steatoza": "steatoză",
    "stenoza": "stenoză",
    "sternoclaviculara": "sternoclaviculară",
    "stomatita": "stomatită",
    "supraventriculara": "supraventriculară",
    "talasemica": "talasemică",
    "telina": "țelină",
    "temporomandibulara": "temporomandibulară",
    "tendinita": "tendinită",
    "teniaza": "teniază",
    "tifoida": "tifoidă",
    "tiroidita": "tiroidită",
    "toxiinfectie": "toxiinfecție",
    "toxoplasmoza": "toxoplasmoză",
    "traheita": "traheită",
    "transpiratie": "transpirație",
    "trombocitopenica": "trombocitopenică",
    "tromboflebita": "tromboflebită",
    "tromboza": "tromboză",
    "tuberculoasa": "tuberculoasă",
    "tuberculoza": "tuberculoză",
    "tulburari": "tulburări",
    "tumora": "tumoră",
    "ulcerativa": "ulcerativă",
    "umarului": "umărului",
    "uretrita": "uretrită",
    "urinara": "urinară",
    "uscata": "uscată",
    "uveita": "uveită",
    "vaca": "vacă",
    "vaginita": "vaginită",
    "varicela": "varicelă",
    "varsaturi": "vărsături",
    "venoasa": "venoasă",
    "ventriculara": "ventriculară",
    "vezica": "vezică",
    "virala": "virală",
    "viroza": "viroză",
    "vitamina": "vitamină",
    "zona": "zonă",
}


# Restore common Romanian diacritics in generated titles and labels.
def _restore_romanian_diacritics(text: str) -> str:
    words = {**_CONDITION_DIACRITIC_WORDS, **_ROMANIAN_DIACRITIC_WORDS}
    for plain, accented in sorted(words.items(), key=lambda item: -len(item[0])):
        pattern = re.compile(rf"(?<!\w){re.escape(plain)}(?!\w)", re.IGNORECASE)

        # Preserve the capitalization style of the matched word.
        def replace(match: re.Match[str], value: str = accented) -> str:
            original = match.group(0)
            if original.isupper():
                return value.upper()
            if original[:1].isupper():
                return value.capitalize()
            return value

        text = pattern.sub(replace, text)
    return text


# Romanian list of names: "a", "a și b", "a, b și c".
def _join_romanian(names: list[str]) -> str:
    if len(names) <= 2:
        return " și ".join(names)
    return ", ".join(names[:-1]) + " și " + names[-1]


# Canonical names (lowercase, with diacritics) of the conditions the health
# problem text names according to the conditions dictionary: whole-word matches
# first, the typo-tolerant resolution of the search when there are none.
def condition_names_for(problem: str) -> list[str]:
    conditions = find_conditions(problem) or list(resolve_query(problem).conditions)
    names = [_restore_romanian_diacritics(condition.name.lower()) for condition in conditions]
    return list(dict.fromkeys(names))


# Create the Romanian report title from the conditions named by the user.
def report_title(profile: dict[str, Any]) -> str:
    """Return the title shared by the PDF metadata, document heading and download name."""
    problem = " ".join(str(profile.get("health_problem") or "").split())[:240]
    names = condition_names_for(problem)
    if names:
        return f"Remedii naturiste pentru {_join_romanian(names)}"
    # No condition recognised: fall back to the typed text (first synonym only).
    problem = _restore_romanian_diacritics(problem).split(",")[0].strip()
    return f"Remedii naturiste pentru {problem}" if problem else "Remedii naturiste"


# Format the leading intervention or product label for readable PDF output.
def format_recommendation(text: str) -> str:
    """Bold and underline the product/intervention label at the start of a claim."""
    clean = " ".join(str(text or "").split())
    match = re.match(
        r"^(?P<label>.{2,160}?)(?P<separator>:\s+|\s+[—-]\s+|\s+\(|"
        r"\s+(?=pentru\b|pulbere\b|administrat\b|preparat\b|"
        r"se\s+(?:ține|bea|ia|consumă|prepară)\b|"
        r"(?:½|¼|\d+(?:[.,]\d+)?)\s*(?:linguri?țe?|linguri?|ml|g|capsule?|picături?)\b))",
        clean,
        flags=re.IGNORECASE,
    )
    if not match:
        return escape(clean)
    label = escape(match.group("label").strip())
    remainder = escape(clean[match.end("label"):])
    return f"<b>{label}</b>{remainder}"


def _compress_reference_numbers(numbers: list[int]) -> str:
    """Return citation numbers as a compact, human-readable range list."""
    if not numbers:
        return ""
    ranges: list[str] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = number
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


def _reference_group_label(source: str) -> str:
    """Return a source filename/path without the line range for bibliography grouping."""
    return re.sub(r":\d+(?:-\d+)?$", "", bibliography_label(source))


def _section_heading(
    key: str,
    style: ParagraphStyle,
) -> Paragraph:
    """Create the heading rendered inside its rounded section container."""
    presentation = SECTION_PRESENTATION[key]
    anchor = f"section-{key}"
    text = (
        f'<a name="{anchor}"/>'
        f'<font size="15" color="#FFFFFF"><b>{presentation["number"]}. '
        f'{escape(presentation["label"])}</b></font>'
    )
    return Paragraph(text, style)


# Build the complete PDF report with sections, inline citations, and bibliography.
def create_pdf(
    profile: dict[str, Any],
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, str]],
) -> bytes:
    regular, bold = _register_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="NaturalCoverEyebrow", fontName=bold, fontSize=9, leading=12,
        textColor=colors.HexColor("#0F5C5E"), tracking=1.2, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="NaturalCoverTitle", fontName=bold, fontSize=27, leading=32,
        textColor=colors.HexColor("#203139"), spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="NaturalCoverByline", fontName=bold, fontSize=10.5, leading=13,
        textColor=colors.HexColor("#0F5C5E"), spaceBefore=8, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="NaturalCoverSubtitle", fontName=regular, fontSize=11, leading=16,
        textColor=colors.HexColor("#52636D"), spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="NaturalCoverInfo", fontName=regular, fontSize=10.5, leading=16,
        textColor=colors.HexColor("#203139"), spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="NaturalBody", fontName=regular, fontSize=10.5, leading=15.5,
        textColor=colors.HexColor(TEXT_COLOR), spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="NaturalEmpty", parent=styles["NaturalBody"], fontSize=10.5, leading=16,
        textColor=colors.HexColor(MUTED_TEXT_COLOR), spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="NaturalBibliographyGroup", fontName=bold, fontSize=11.5, leading=16,
        textColor=colors.HexColor("#52636D"), spaceBefore=7, spaceAfter=3,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="NaturalBibliography", fontName=regular, fontSize=9.2, leading=14,
        textColor=colors.HexColor(TEXT_COLOR), leftIndent=5, spaceAfter=4,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="NaturalBibliographyHeading", fontName=bold, fontSize=15, leading=19,
        textColor=colors.white, spaceBefore=0, spaceAfter=5,
    ))
    section_styles: dict[str, ParagraphStyle] = {}
    item_styles: dict[str, ParagraphStyle] = {}
    for key, presentation in SECTION_PRESENTATION.items():
        section_styles[key] = ParagraphStyle(
            f"NaturalSection{key}", fontName=bold, fontSize=15, leading=19,
            textColor=colors.white, spaceBefore=0, spaceAfter=5,
        )
        item_styles[key] = ParagraphStyle(
            f"NaturalItem{key}", parent=styles["NaturalBody"],
            leftIndent=4, spaceAfter=4,
        )

    title = report_title(profile)
    # The portrait sits at the top right of the cover; these paragraphs wrap
    # before it, while the info block below spans the full width.
    cover_content: list[Flowable] = [
        Paragraph("GHID INFORMATIV", styles["NaturalCoverEyebrow"]),
        Paragraph(escape(title), styles["NaturalCoverTitle"]),
        Paragraph("de la dr. Cuișor", styles["NaturalCoverByline"]),
        Paragraph(
            "Informații din documente locale organizate pentru lectură rapidă și consultare responsabilă. Nu stabilește diagnostice și nu înlocuiește consultul sau tratamentul recomandat de un profesionist în sănătate.",
            styles["NaturalCoverSubtitle"],
        ),
    ]
    for flowable in cover_content:
        flowable.beside_image = True
    story: list[Any] = [CoverPanel(
        cover_content,
        visible_height=56 * mm,
        page_top_extension=20 * mm,
        image_path=DOCTOR_IMAGE,
        image_size=44 * mm,
    )]
    story.append(Spacer(1, 6 * mm))

    headings = (
        "uz_intern",
        "nutritie",
        "uz_extern",
        "alte_recomandari",
        "atentionari",
    )
    sections = sort_sections_by_relevance(sections, evidence)
    reference_numbers, references = build_reference_index(sections, evidence)
    source_targets: dict[str, str] = {}

    def citations_for(item: dict[str, Any]) -> list[str]:
        return [
            evidence[token]["source"]
            for token in item.get("evidence_ids", [])
            if token in evidence
        ]

    def source_chip(citations: list[str]) -> str:
        if not citations:
            return ""
        numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
        return (
            ' <link href="#section-bibliografie" color="#0F5C5E">'
            f'<font size="8.7"><b>→ Surse {_compress_reference_numbers(numbers)}</b></font></link>'
        )

    def add_recommendation(
        section_content: list[Flowable],
        key: str,
        text: str,
        citations: list[str],
        anchor: str,
    ) -> None:
        for source in citations:
            source_targets.setdefault(source, anchor)
        section_content.append(Paragraph(
            f'<a name="{anchor}"/>{text}{source_chip(citations)}', item_styles[key]
        ))

    for key in headings:
        presentation = SECTION_PRESENTATION[key]
        section_content: list[Flowable] = [
            _section_heading(key, section_styles[key]),
            Spacer(1, 2.5 * mm),
        ]
        items = sections.get(key) or []
        if not items:
            section_content.append(Paragraph(
                "Nu au fost identificate informații suficient de relevante în sursele disponibile.",
                styles["NaturalEmpty"],
            ))
        elif key == "nutritie":
            nutrition_index = 0
            for nutrition_key, nutrition_label, nutrition_items in nutrition_display_groups(items):
                if nutrition_key == "recipes":
                    for recipe_number, item in enumerate(nutrition_items, start=1):
                        nutrition_index += 1
                        item_text = escape(str(item["text"])).replace(chr(10), "<br/>")
                        # Singular title; numbered only when there are several recipes.
                        recipe_label = "Rețetă culinară" if len(nutrition_items) == 1 else f"Rețetă culinară {recipe_number}"
                        add_recommendation(
                            section_content,
                            key,
                            f'<b>• {recipe_label}</b><br/>{item_text}',
                            citations_for(item),
                            f"recommendation-{key}-{nutrition_index}",
                        )
                    continue
                if not nutrition_items:
                    continue
                nutrition_index += 1
                texts = "; ".join(
                    escape(str(item["text"])).replace(chr(10), "<br/>") for item in nutrition_items
                )
                citations = [source for item in nutrition_items for source in citations_for(item)]
                add_recommendation(
                    section_content,
                    key,
                    f"<b>• {escape(nutrition_label)}</b><br/>{texts}",
                    list(dict.fromkeys(citations)),
                    f"recommendation-{key}-{nutrition_index}",
                )
        else:
            for index, item in enumerate(items, start=1):
                add_recommendation(
                    section_content,
                    key,
                    "● " + format_recommendation(str(item["text"])),
                    citations_for(item),
                    f"recommendation-{key}-{index}",
                )
        story.append(RoundedSection(
            section_content,
            "#FFFFFF",
            presentation["color"],
            bookmark=f"section-{key}",
            outline=f'{presentation["number"]}. {presentation["label"]}',
        ))
        story.append(Spacer(1, 4 * mm))

    bibliography_content: list[Flowable] = [
        Paragraph(
            '<a name="section-bibliografie"/><font size="15" color="#FFFFFF">'
            '<b>6. Bibliografie</b></font>',
            styles["NaturalBibliographyHeading"],
        ),
        Spacer(1, 2.5 * mm),
    ]
    if references:
        previous_group = ""
        for number, source in enumerate(references, start=1):
            group = _reference_group_label(source)
            if group != previous_group:
                bibliography_content.append(
                    Paragraph(escape(group), styles["NaturalBibliographyGroup"])
                )
                previous_group = group
            target = source_targets.get(source, "section-uz_intern")
            bibliography_content.append(Paragraph(
                f'<a name="bibliografie-{number}"/><b>{number} -</b> {escape(bibliography_label(source))} '
                f'<link href="#{target}" color="#52636D"><font size="8.5">← înapoi</font></link>',
                styles["NaturalBibliography"],
            ))
    else:
        bibliography_content.append(Paragraph(
            "Nu există referințe bibliografice utilizate.",
            styles["NaturalEmpty"],
        ))
    story.append(RoundedSection(
        bibliography_content,
        "#FFFFFF",
        "#52636D",
        bookmark="section-bibliografie",
        outline="6. Bibliografie",
    ))
    buffer = BytesIO()
    doc = NatureReportDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=20 * mm, bottomMargin=22 * mm,
        title=title, author="Chatbot naturist",
    )
    doc.footer_color = "#087F73"
    doc.build(story, onFirstPage=_first_page, onLaterPages=_later_page)
    return buffer.getvalue()
