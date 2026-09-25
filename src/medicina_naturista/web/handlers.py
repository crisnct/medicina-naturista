"""Reusable conversation rendering and Gradio event-result helpers."""
from __future__ import annotations

import html
import os
import re
from urllib.parse import quote

import gradio as gr

from medicina_naturista.core.models import SessionData
from medicina_naturista.reporting.pdf import (
    bibliography_label,
    build_reference_index,
    nutrition_display_groups,
    report_title,
    sort_sections_by_source_count,
)


def processing_button_update():
    return gr.update(value="⏳ Se pregătește...", interactive=False)


def ready_button_update():
    return gr.update(value="📨 Trimite", interactive=True)

# Convert the health problem into a safe downloadable PDF filename.
def _report_filename(session: SessionData) -> str:
    title = report_title(session.profile.as_dict())
    safe = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "-", title)
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    return f"{safe or 'Recomandări naturiste'}.pdf"


# Build the session-scoped HTML link for downloading the generated PDF.
def _download_html(session: SessionData) -> str:
    if not session.report_id:
        return ""
    prefix = os.getenv("GRADIO_ROOT_PATH", "").rstrip("/")
    url = f"{prefix}/api/reports/{quote(session.tab_id, safe='')}/{quote(session.report_id, safe='')}"
    filename = _report_filename(session)
    return (
        '<section class="report-ready-panel" role="status" aria-live="polite">'
        '<div class="report-ready-copy">'
        '<span class="report-ready-icon" aria-hidden="true">✅</span>'
        '<span><strong>Raportul complet este gata</strong>'
        '<small>Îl puteți salva pentru a-l consulta oricând.</small></span>'
        '</div>'
        f'<a href="{html.escape(url, quote=True)}" download="{html.escape(filename, quote=True)}" '
        'class="pdf-download" aria-label="Descarcă raportul complet în format PDF">'
        '<span aria-hidden="true">📄</span> Descarcă PDF</a>'
        '</section>'
    )


# Append a chat message while keeping history bounded to recent entries.
def _append(session: SessionData, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    if len(session.history) > 60:
        session.history = session.history[-60:]


# Add an assistant question to both the visible history and the profile transcript.
def _ask(session: SessionData, question: str) -> None:
    _append(session, "assistant", question)
    session.profile.add_transcript("assistant", question)


# Render report sections and bibliography as the textual chatbot response.
def _recommendation_text(sections: dict, evidence: dict) -> str:
    labels = (
        ("uz_intern", "Uz intern"),
        ("nutritie", "Nutriție"),
        ("uz_extern", "Uz extern"),
        ("alte_recomandari", "Alte Recomandări"),
        ("atentionari", "Atenționări"),
    )
    sections = sort_sections_by_source_count(sections, evidence)
    reference_numbers, references = build_reference_index(sections, evidence)
    lines = ["✅ Raportul este gata. Recomandările susținute de surse:"]
    found = False
    for key, label in labels:
        items = sections.get(key) or []
        if not items:
            continue
        found = True
        lines.append(f"\n{label}:")
        if key == "nutritie":
            for nutrition_key, nutrition_label, nutrition_items in nutrition_display_groups(items):
                formatted_items = []
                for item in nutrition_items:
                    citations = [
                        evidence[token]["source"]
                        for token in item.get("evidence_ids", [])
                        if token in evidence
                    ]
                    unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
                    markers = " ".join(f"[{number}]" for number in unique_numbers)
                    formatted_items.append(f"{item['text']} {markers}".rstrip())
                if nutrition_key == "recipes":
                    lines.append(f"**• {nutrition_label}:**")
                    if not formatted_items:
                        lines.append("    -")
                    else:
                        lines.extend(f"    - {item}" for item in formatted_items)
                    continue
                content = "; ".join(formatted_items) if formatted_items else "-"
                lines.append(f"**• {nutrition_label}:** {content}")
            continue
        for item in items:
            citations = [evidence[token]["source"] for token in item.get("evidence_ids", []) if token in evidence]
            unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
            markers = " ".join(f"[{number}]" for number in unique_numbers)
            lines.append(f"• {item['text']} {markers}".rstrip())
    if not found:
        lines.append("Nu au fost identificate recomandări specifice suficient susținute de fragmentele disponibile.")
    if references:
        lines.append("\nBibliografie:")
        lines.extend(
            f"{number} - {bibliography_label(source)}"
            for number, source in enumerate(references, start=1)
        )
    return "\n".join(lines)[:14000]
