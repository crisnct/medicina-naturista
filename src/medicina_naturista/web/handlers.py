"""Reusable conversation rendering and structured chat-message builders.

Every chat message is a small JSON-serializable dict, distinguished by its
"kind": "text" (plain assistant/user text), "fragments" (the retrieval
results shown before generation), "generate" (the "Generează rețeta" call to
action for one search) or "download" (the finished PDF link). The frontend
renders each kind as its own component; nothing here produces HTML.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

from medicina_naturista.core.models import SessionData
from medicina_naturista.reporting.pdf import (
    bibliography_label,
    build_reference_index,
    nutrition_display_groups,
    report_title,
    sort_sections_by_relevance,
)


# Build a plain text chat message.
def _text(role: str, content: str) -> dict[str, Any]:
    return {"role": role, "kind": "text", "content": content}


GENERATE_LABEL = "💊 Generează rețeta"


# Build the "Generează rețeta" call-to-action message for one search.
def _generate_message(search_id: str, busy: bool = False) -> dict[str, Any]:
    return {"role": "assistant", "kind": "generate", "searchId": search_id, "busy": busy}


# Replace (or, with replacements=None, remove) the message holding one
# search's "generate" call to action, splicing `replacements` in its place so
# they land exactly where the removed message was — keeping chronological
# order. Looks the message up by its typed searchId field, not by scanning
# text for a marker.
def _replace_generate_message(
    session: SessionData, search_id: str, replacements: list[dict[str, Any]] | None
) -> None:
    for index, message in enumerate(session.history):
        if message.get("kind") == "generate" and message.get("searchId") == search_id:
            session.history[index : index + 1] = replacements or []
            return


# Convert the health problem into a safe downloadable PDF filename.
def _report_filename(session: SessionData, profile: dict | None = None) -> str:
    title = report_title(profile if profile is not None else session.profile.as_dict())
    safe = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "-", title)
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    return f"{safe or 'Recomandări naturiste'}.pdf"


# Build the session-scoped download message for the generated PDF.
def _download_message(
    session: SessionData, report_id: str | None = None, profile: dict | None = None
) -> dict[str, Any]:
    report_id = report_id or session.report_id
    if not report_id:
        return _text("assistant", "")
    # Kept behind an env var read here (not cached Settings) so a reverse
    # proxy that mounts the app under a sub-path (see PUBLIC_ROOT_PATH in the
    # deployment Caddyfile/compose) can be changed without a restart, and so
    # tests can monkeypatch it around a single call.
    prefix = os.getenv("PUBLIC_ROOT_PATH", os.getenv("GRADIO_ROOT_PATH", "")).rstrip("/")
    url = f"{prefix}/api/reports/{quote(session.tab_id, safe='')}/{quote(report_id, safe='')}"
    filename = _report_filename(session, profile)
    return {"role": "assistant", "kind": "download", "reportId": report_id, "url": url, "filename": filename}


# Collapse a fragment's whitespace/newlines into single spaces for display.
# The fragments panel shows the fragment's full text, untruncated — every
# match (like a single incidental word deep in a long fragment) needs to be
# visible, not hidden behind a preview cutoff.
def _normalize_text(text: str) -> str:
    return " ".join(text.split())


# Romanian label for a fragment's provenance, built from the found_by_<signal>
# booleans set by ai/search.py's rank() (propagated via Retriever.collect()).
# Shown next to the relevance score so the patient can see when a result was an
# exact lexical match. There is no semantic label: every fragment is ranked
# semantically, so it would appear on all of them. Adding a selective signal
# later only means adding one more (label, flag) pair to _MATCH_TYPE_SIGNALS.
_MATCH_TYPE_SIGNALS: tuple[tuple[str, str], ...] = (
    ("Lexicală", "found_by_lexical"),
)


def _match_type_label(item: dict) -> str:
    found_labels = [label for label, key in _MATCH_TYPE_SIGNALS if item.get(key)]
    if not found_labels:
        return ""
    return "Găsire " + " și ".join(found_labels)


# Build the structured "fragments found" message shown before the patient
# decides to send them to the AI — a single flat list, sorted by relevance
# score (evidence's raw "score" field, from Retriever.collect()), descending.
def _fragments_message(search_id: str, evidence: dict) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    all_documents: set[str] = set()
    for item in evidence.values():
        document = item["source"].split(":", 1)[0].removeprefix("documents/")
        all_documents.add(document)
        entries.append({
            "document": document,
            "text": _normalize_text(item["text"]),
            "score": item.get("score", float("-inf")),
            "relevancePercent": item.get("relevance_percent"),
            "matchLabel": _match_type_label(item),
        })
    entries.sort(key=lambda entry: entry["score"], reverse=True)
    for entry in entries:
        del entry["score"]
    return {
        "role": "assistant",
        "kind": "fragments",
        "searchId": search_id,
        "fragmentsCount": len(evidence),
        "documentsCount": len(all_documents),
        "fragments": entries,
    }


# Append a chat message while keeping history bounded to recent entries.
def _append(session: SessionData, message: dict[str, Any]) -> None:
    session.history.append(message)
    if len(session.history) > 60:
        session.history = session.history[-60:]


# Add an assistant question to both the visible history and the profile transcript.
def _ask(session: SessionData, question: str) -> None:
    _append(session, _text("assistant", question))
    session.profile.add_transcript("assistant", question)


# Render report sections and bibliography as the textual chatbot response.
# Kept as one Markdown-flavoured string (rendered by the frontend), rather
# than a fully structured payload, since the section/nutrition/citation
# formatting rules here are shared with reporting/pdf.py's own numbering.
def _recommendation_text(sections: dict, evidence: dict) -> str:
    labels = (
        ("uz_intern", "Uz intern"),
        ("nutritie", "Nutriție"),
        ("uz_extern", "Uz extern"),
        ("alte_recomandari", "Alte Recomandări"),
        ("atentionari", "Atenționări"),
    )
    sections = sort_sections_by_relevance(sections, evidence)
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
