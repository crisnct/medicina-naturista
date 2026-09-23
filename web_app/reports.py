"""Readable Romanian PDF report with source references next to each claim."""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

SECTION_KEYS = ("uz_intern", "nutritie", "uz_extern", "alte_recomandari", "atentionari")

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


def _page(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("NaturistRegular", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(18 * mm, 12 * mm, "Recomandări naturiste")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Pagina {document.page}")
    canvas.restoreState()


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


def _restore_romanian_diacritics(text: str) -> str:
    for plain, accented in sorted(_ROMANIAN_DIACRITIC_WORDS.items(), key=lambda item: -len(item[0])):
        pattern = re.compile(rf"(?<!\w){re.escape(plain)}(?!\w)", re.IGNORECASE)

        def replace(match: re.Match[str], value: str = accented) -> str:
            original = match.group(0)
            if original.isupper():
                return value.upper()
            if original[:1].isupper():
                return value.capitalize()
            return value

        text = pattern.sub(replace, text)
    return text


def report_title(profile: dict[str, Any]) -> str:
    """Return the title shared by the PDF metadata, document heading and download name."""
    problem = _restore_romanian_diacritics(
        " ".join(str(profile.get("health_problem") or "").split())[:240]
    )
    return f"Recomandări naturiste pentru {problem}" if problem else "Recomandări naturiste"


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
    return f"<b><u>{label}</u></b>{remainder}"


def create_pdf(
    profile: dict[str, Any],
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, str]],
) -> bytes:
    regular, bold = _register_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="NaturalTitle", fontName=bold, fontSize=21, leading=27,
        textColor=colors.HexColor("#173c46"), spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="NaturalSubtitle", fontName=bold, fontSize=11, leading=15,
        textColor=colors.HexColor("#176c73"), spaceBefore=13, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="NaturalSection", fontName=bold, fontSize=14, leading=19,
        textColor=colors.HexColor("#176c73"), spaceBefore=11, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="NaturalBody", fontName=regular, fontSize=9.5, leading=15,
        textColor=colors.HexColor("#21333c"), spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="NaturalSource", fontName=regular, fontSize=7.5, leading=11,
        textColor=colors.HexColor("#526774"), leftIndent=8, spaceAfter=8,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="NaturalNote", fontName=regular, fontSize=8.5, leading=13,
        textColor=colors.HexColor("#526774"), spaceAfter=10,
    ))
    body = styles["NaturalBody"]
    source_style = styles["NaturalSource"]
    title = report_title(profile)
    story: list[Any] = [Paragraph(escape(title), styles["NaturalTitle"])]
    story.append(Paragraph(
        "Material informativ adjuvant. Nu stabilește diagnostice și nu înlocuiește consultul sau "
        "tratamentul recomandat de un profesionist în sănătate.", styles["NaturalNote"]
    ))
    headings = (
        ("uz_intern", "1. Uz intern"),
        ("nutritie", "2. Nutriție"),
        ("uz_extern", "3. Uz extern"),
        ("alte_recomandari", "4. Alte Recomandări"),
        ("atentionari", "5. Atenționări"),
    )
    reference_numbers, references = build_reference_index(sections, evidence)
    story.append(HRFlowable(
        width="100%", thickness=0.8, color=colors.HexColor("#cbd5e1"),
        spaceBefore=8, spaceAfter=10,
    ))
    for key, heading in headings:
        story.append(Paragraph(heading, styles["NaturalSection"]))
        items = sections.get(key) or []
        if not items:
            story.append(Paragraph(
                "Nu au fost identificate informații suficient de relevante în sursele disponibile.", body
            ))
            continue
        for item in items:
            citations = [
                evidence[token]["source"] for token in item.get("evidence_ids", []) if token in evidence
            ]
            elements = [Paragraph("• " + format_recommendation(str(item["text"])), body)]
            if citations:
                unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
                markers = "".join(
                    f'<link href="#bibliografie-{number}" color="#176c73"><u>[{number}]</u></link>'
                    for number in unique_numbers
                )
                inline_sources = (
                    f' <font size="7.5" color="#526774"><b>Surse:</b> {markers}</font>'
                )
                elements = [Paragraph("• " + format_recommendation(str(item["text"])) + inline_sources, body)]
            story.append(KeepTogether(elements))
    story.append(Paragraph("6. Bibliografie", styles["NaturalSection"]))
    if references:
        for number, source in enumerate(references, start=1):
            story.append(Paragraph(
                f'<a name="bibliografie-{number}"/>{number} - {escape(bibliography_label(source))}',
                body,
            ))
    else:
        story.append(Paragraph("Nu există referințe bibliografice utilizate.", body))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=19 * mm, bottomMargin=20 * mm,
        title=title, author="Chatbot naturist",
    )
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()
