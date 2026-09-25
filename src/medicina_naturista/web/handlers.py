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


GENERATE_LABEL = "💊 Generează rețeta"


# Show the panel holding "Generează rețeta" once fragments were found.
def generate_row_visible_update():
    return gr.update(visible=True)


# Hide the "Generează rețeta" panel (no fragments, or a report was just generated).
def generate_row_hidden_update():
    return gr.update(visible=False)


# Reset the button label/state to its clickable default (fragments ready, or
# a previous attempt failed and the patient may retry without losing them).
def generate_button_ready_update():
    return gr.update(value=GENERATE_LABEL, interactive=True)


# Disable the "Generează rețeta" button while the AI request is in flight.
def generate_button_processing_update():
    return gr.update(value="⏳ Se generează rețeta...", interactive=False)

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


# Collapse a fragment's whitespace/newlines into single spaces for display.
# The fragments panel shows the fragment's full text, untruncated — every
# match (like a single incidental word deep in a long fragment) needs to be
# visible, not hidden behind a preview cutoff.
def _normalize_text(text: str) -> str:
    return " ".join(text.split())


# Sort key for fragments within a document: numeric hybrid scores rank by
# value, and an exact-topic match ("Potrivire exactă pe subiect" — has no
# number to parse) ranks above every numeric score, since it is the
# strongest possible match.
def _relevance_sort_key(relevance: str) -> float:
    match = re.search(r"[\d.]+", relevance)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return float("inf")


# Build the scrollable panel showing every retrieved fragment as a single
# flat list, before the patient decides to send them to the AI. Only the
# fragment text and its relevance (score + source document, on one line) are
# shown — no chunk ids, line ranges, or other internal metadata — per the
# patient-facing transparency requirement.
#
# Ordering: exact-topic matches ("Potrivire exactă pe subiect") lead, sorted
# by document name, since they are the strongest possible match; every
# remaining fragment follows, sorted purely by relevance score (descending),
# regardless of which document it came from.
#
# The title and "found N fragments" banner sit in their own header, kept
# pinned above the scrollable fragment list (see .fragments-panel-header in
# app.css) so they stay visible while the patient scrolls. That banner used
# to be posted as a separate chat message; it now lives here instead, so it
# can carry its own styling and sit with no gap before the fragments — both
# awkward to do reliably from inside a chat bubble shared with every other
# assistant message.
def _fragments_panel_html(evidence: dict) -> str:
    if not evidence:
        return ""
    exact_entries: list[tuple[str, str]] = []  # (document, text)
    scored_entries: list[tuple[str, str, str]] = []  # (document, text, relevance)
    all_documents: set[str] = set()
    for item in evidence.values():
        document = item["source"].split(":", 1)[0].removeprefix("documents/")
        all_documents.add(document)
        relevance = item.get("relevance", "")
        if relevance == "Potrivire exactă pe subiect":
            exact_entries.append((document, item["text"]))
        else:
            scored_entries.append((document, item["text"], relevance))
    exact_entries.sort(key=lambda entry: entry[0].casefold())
    scored_entries.sort(key=lambda entry: _relevance_sort_key(entry[2]), reverse=True)

    parts = ['<div class="fragments-panel-inner">']
    parts.append(
        '<div class="fragments-panel-header">'
        '<p class="fragments-panel-title">🔎 Fragmentele relevante</p>'
        '<div class="fragments-panel-banner">'
        f"Am găsit {len(evidence)} fragmente relevante în {len(all_documents)} documente locale "
        "(le puteți vedea mai jos). Dacă vi se par potrivite, apăsați „Generează rețeta”."
        "</div>"
        "</div>"
    )
    for document, text in exact_entries:
        parts.append('<div class="fragments-panel-fragment">')
        parts.append(f'<p class="fragments-panel-fragment-text">{html.escape(_normalize_text(text))}</p>')
        parts.append(
            '<p class="fragments-panel-fragment-score">'
            f'{html.escape("Potrivire exactă pe subiect")}, {html.escape(document)}</p>'
        )
        parts.append("</div>")
    for document, text, relevance in scored_entries:
        parts.append('<div class="fragments-panel-fragment">')
        parts.append(f'<p class="fragments-panel-fragment-text">{html.escape(_normalize_text(text))}</p>')
        parts.append(f'<p class="fragments-panel-fragment-score">{html.escape(relevance)}, {html.escape(document)}</p>')
        parts.append("</div>")
    parts.append(
        '<p class="fragments-panel-summary">'
        f"Total: {len(evidence)} fragmente din {len(all_documents)} documente."
        "</p>"
    )
    parts.append("</div>")
    return "".join(parts)


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
