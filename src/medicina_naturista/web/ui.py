"""Static assets and presentational constants for the Gradio interface."""
from __future__ import annotations

import base64
from pathlib import Path

import gradio as gr

STATIC_ROOT = Path(__file__).resolve().parent / "static"
ORNAMENT_SVG_PATH = STATIC_ROOT / "images" / "ornament-fitoterapie-antet.svg"
DOCTOR_IMAGE_PATH = STATIC_ROOT / "images" / "dr-cuisor.webp"


def _read_static(relative_path: str) -> str:
    return (STATIC_ROOT / relative_path).read_text(encoding="utf-8")


# Embed the ornament in the delivered CSS so reverse-proxy prefixes cannot break its URL.
def _svg_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _webp_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


APP_CSS = _read_static("css/app.css").replace(
    "__HERO_ORNAMENT_DATA_URI__",
    _svg_data_uri(ORNAMENT_SVG_PATH),
)
COMPOSER_STATE_JS = _read_static("js/app.js")
AUTO_SCROLL_JS = _read_static("js/auto_scroll.js")
# Fold the fragments panel back up (it is a <details> element).
COLLAPSE_FRAGMENTS_JS = (
    "() => { document.querySelectorAll('#medical-chatbot .fragments-panel-inner').forEach(d => { d.open = false; }); }"
)

THEME = gr.themes.Soft(font=["Arial", "sans-serif"])

HERO_HTML = """
<section id="hero-panel" aria-labelledby="hero-title">
    <img class="hero-doctor" src="__DOCTOR_DATA_URI__" alt="Dr. Cuișor">
    <div class="hero-kicker"><span aria-hidden="true">🌿</span> Ghid naturist bazat pe surse locale</div>
    <div class="hero-title-block">
        <h1 id="hero-title">Remedii Naturiste</h1>
        <p class="hero-byline">de la Dr. Cuișor</p>
    </div>
    <p class="hero-description">
        Descrieți problema cu care vă confruntați și primiți un raport informativ, clar și ușor de consultat. Informațiile sunt orientative și nu înlocuiesc consultul sau îngrijirea medicală.
    </p>
</section>
"""
HERO_HTML = HERO_HTML.replace("__DOCTOR_DATA_URI__", _webp_data_uri(DOCTOR_IMAGE_PATH))

ASSISTANT_HEADER_HTML = """
<div class="assistant-identity">
    <span class="assistant-avatar" aria-hidden="true">🩺</span>
    <span><strong>Dr. Cuișor</strong><small>Răspunsuri bazate pe surse locale</small></span>
</div>
"""

MESSAGE_HELPER_HTML = """
<div><span aria-hidden="true">📝</span> Specificați strict problema de sănătate și nimic altceva. Puteți menționa mai multe sinonime separate prin virgulă.</div>
"""
