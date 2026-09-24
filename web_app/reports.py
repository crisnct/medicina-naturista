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


# Draw the common footer with the report label and current page number.
def _page(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("NaturistRegular", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(18 * mm, 12 * mm, "Recomandări naturiste")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Pagina {document.page}")
    canvas.restoreState()


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


# Sort every report section by descending count of distinct cited sources.
def sort_sections_by_source_count(
    sections: dict[str, list[dict[str, Any]]],
    evidence: dict[str, dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    """Order every section by descending number of distinct cited sources."""
    ordered: dict[str, list[dict[str, Any]]] = {}
    for section, items in sections.items():
        indexed_items = list(enumerate(items))
        indexed_items.sort(
            key=lambda pair: (
                -len({
                    evidence[token]["source"]
                    for token in pair[1].get("evidence_ids", [])
                    if token in evidence
                }),
                pair[0],
            )
        )
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


# Restore common Romanian diacritics in generated titles and labels.
def _restore_romanian_diacritics(text: str) -> str:
    for plain, accented in sorted(_ROMANIAN_DIACRITIC_WORDS.items(), key=lambda item: -len(item[0])):
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


# Create the Romanian report title from the normalized health problem.
def report_title(profile: dict[str, Any]) -> str:
    """Return the title shared by the PDF metadata, document heading and download name."""
    problem = _restore_romanian_diacritics(
        " ".join(str(profile.get("health_problem") or "").split())[:240]
    )
    return f"Recomandări naturiste pentru {problem}" if problem else "Recomandări naturiste"


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


# Build the complete PDF report with sections, inline citations, and bibliography.
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
    styles.add(ParagraphStyle(
        name="NaturalNutritionItem", parent=styles["NaturalBody"], leftIndent=12,
    ))
    body = styles["NaturalBody"]
    nutrition_item = styles["NaturalNutritionItem"]
    nutrition_recipe = ParagraphStyle(
        "NaturalNutritionRecipe", parent=nutrition_item, leftIndent=24,
    )
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
    sections = sort_sections_by_source_count(sections, evidence)
    reference_numbers, references = build_reference_index(sections, evidence)
    for key, heading in headings:
        section_story: list[Any] = [
            HRFlowable(
                width="100%", thickness=0.8, color=colors.HexColor("#cbd5e1"),
                spaceBefore=8, spaceAfter=10,
            ),
            Paragraph(heading, styles["NaturalSection"]),
        ]
        items = sections.get(key) or []
        if not items:
            section_story.append(Paragraph(
                "Nu au fost identificate informații suficient de relevante în sursele disponibile.", body
            ))
            story.append(KeepTogether(section_story))
            continue
        if key == "nutritie":
            for nutrition_key, nutrition_label, nutrition_items in nutrition_display_groups(items):
                formatted_items = []
                for item in nutrition_items:
                    citations = [
                        evidence[token]["source"]
                        for token in item.get("evidence_ids", [])
                        if token in evidence
                    ]
                    text = escape(str(item["text"])).replace("\n", "<br/>")
                    inline_sources = ""
                    if citations:
                        unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
                        markers = " ".join(
                            f'<link href="#bibliografie-{number}" color="#176c73"><u>[{number}]</u></link>'
                            for number in unique_numbers
                        )
                        inline_sources = f' <font size="7.5" color="#526774"><b>Surse:</b> {markers}</font>'
                    formatted_items.append((text, inline_sources))
                if nutrition_key == "recipes":
                    section_story.append(Paragraph(f"• {escape(nutrition_label)}:", body))
                    if not formatted_items:
                        section_story.append(Paragraph("-", nutrition_recipe))
                    else:
                        for text, inline_sources in formatted_items:
                            section_story.append(Paragraph(f"- {text}{inline_sources}", nutrition_recipe))
                    continue
                content = "; ".join(
                    f"{text}{inline_sources}" for text, inline_sources in formatted_items
                ) or "-"
                section_story.append(
                    Paragraph(f"• {escape(nutrition_label)}: {content}", body)
                )
            story.append(KeepTogether(section_story))
            continue
        for item in items:
            citations = [
                evidence[token]["source"] for token in item.get("evidence_ids", []) if token in evidence
            ]
            elements = [Paragraph("• " + format_recommendation(str(item["text"])), body)]
            if citations:
                unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
                markers = " ".join(
                    f'<link href="#bibliografie-{number}" color="#176c73"><u>[{number}]</u></link>'
                    for number in unique_numbers
                )
                inline_sources = (
                    f' <font size="7.5" color="#526774"><b>Surse:</b> {markers}</font>'
                )
                elements = [Paragraph("• " + format_recommendation(str(item["text"])) + inline_sources, body)]
            section_story.append(KeepTogether(elements))
        story.append(KeepTogether(section_story))
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
