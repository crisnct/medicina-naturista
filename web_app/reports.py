"""Readable Romanian PDF report with source references next to each claim."""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

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
    canvas.drawString(18 * mm, 12 * mm, "Recomandări naturiste - material informativ adjuvant")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Pagina {document.page}")
    canvas.restoreState()


def create_pdf(
    profile: dict[str, Any],
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, str]],
) -> bytes:
    regular, bold = _register_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="NaturalTitle", fontName=bold, fontSize=16, leading=21,
        textColor=colors.HexColor("#173c46"), spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="NaturalSubtitle", fontName=bold, fontSize=11, leading=15,
        textColor=colors.HexColor("#176c73"), spaceBefore=13, spaceAfter=7,
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
    problems = profile.get("health_conditions") or []
    full_name = str(profile.get("full_name") or "utilizator")
    title = f"Recomandări naturiste pentru {full_name}"
    story: list[Any] = [Paragraph(escape(title), styles["NaturalTitle"])]
    story.append(Paragraph(
        "Material informativ adjuvant. Nu stabilește diagnostice și nu înlocuiește consultul sau "
        "tratamentul recomandat de un profesionist în sănătate.", styles["NaturalNote"]
    ))
    story.append(Paragraph("Rezumat utilizator", styles["NaturalSubtitle"]))
    rows = [
        ("Nume și prenume", full_name),
        ("Vârstă", f"{profile['age']} ani" if profile.get("age") is not None else "Necunoscut / nefurnizat"),
        ("Sex", str(profile.get("sex") or "Necunoscut / nefurnizat")),
        ("Greutate", f"{profile['weight_kg']} kg" if profile.get("weight_kg") is not None else "Necunoscut / nefurnizat"),
        ("Înălțime", f"{profile['height_cm']} cm" if profile.get("height_cm") is not None else "Necunoscut / nefurnizat"),
        ("Simptome", ", ".join(profile.get("symptoms") or []) or "Necunoscut / nefurnizat"),
        ("Descrierea problemei", str(profile.get("health_problem") or "Necunoscut / nefurnizat")),
    ]
    for key, value in rows:
        story.append(Paragraph(f"<b>{escape(key)}:</b> {escape(str(value))}", body))
    story.append(Paragraph("Probleme de sănătate", styles["NaturalSubtitle"]))
    if problems:
        for value in problems:
            story.append(Paragraph("• " + escape(str(value)), body))
    else:
        story.append(Paragraph("Nu au fost declarate probleme de sănătate distincte.", body))

    transcript = profile.get("transcript") or []
    if transcript:
        story.append(Paragraph("Discuția medicală", styles["NaturalSubtitle"]))
        for entry in transcript:
            if not isinstance(entry, dict):
                continue
            role = "Chatbot" if entry.get("role") == "assistant" else "Utilizator"
            content = str(entry.get("content") or "").strip()
            if content:
                story.append(Paragraph(f"<b>{escape(role)}:</b> {escape(content)}", body))

    headings = (
        ("uz_intern", "1. Uz intern"),
        ("nutritie", "2. Nutriție"),
        ("uz_extern", "3. Uz extern"),
        ("alte_recomandari", "4. Alte Recomandări"),
        ("atentionari", "5. Atenționări"),
    )
    for key, heading in headings:
        story.append(Paragraph(heading, styles["NaturalSubtitle"]))
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
            elements = [Paragraph("• " + escape(str(item["text"])), body)]
            if citations:
                elements.append(Paragraph("Surse: " + escape("; ".join(citations)), source_style))
            story.append(KeepTogether(elements))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=19 * mm, bottomMargin=20 * mm,
        title=title, author="Chatbot naturist",
    )
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()
