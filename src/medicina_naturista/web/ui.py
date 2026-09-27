"""Static assets and presentational constants for the Gradio interface."""
from __future__ import annotations

import base64
import html
from pathlib import Path

import gradio as gr

from medicina_naturista.ai.categories import CategoryTree

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
CATEGORY_FILTER_JS = _read_static("js/category_filter.js")
# Fold the fragments panel back up (it is a <details> element).
COLLAPSE_FRAGMENTS_JS = (
    "() => { document.querySelectorAll('#medical-chatbot .fragments-panel-inner').forEach(d => { d.open = false; }); }"
)

THEME = gr.themes.Soft(font=["Arial", "sans-serif"])

HERO_HTML = """
<section id="hero-panel" aria-labelledby="hero-title">
    <div class="hero-kicker"><span aria-hidden="true">🌿</span> Ghid naturist bazat pe surse locale</div>
    <img class="hero-doctor" src="__DOCTOR_DATA_URI__" alt="Dr. Cuișor">
    <div class="hero-title-block">
        <h1 id="hero-title">Remedii Naturiste</h1>
        <p class="hero-byline">de la Dr. Cuișor</p>
        <p class="hero-description">
            Descrieți problema cu care vă confruntați și primiți un raport informativ, clar și ușor de consultat. Informațiile sunt orientative și nu înlocuiesc consultul sau îngrijirea medicală.
        </p>
    </div>
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


# Render one category as a tree list item, recursing into its subfolders.
# Every node — leaf or branch — gets its own checkbox: category_filter.js
# makes checking a branch cascade to everything under it, and makes a
# branch's own checkbox reflect the aggregate (checked/unchecked/mixed) of
# its descendants. data-real="1" marks a category with documents of its own
# (own_documents > 0) — the only ids category_filter.js ever serializes into
# the hidden #category-selection field, since a purely structural branch
# (subfolders only) is never a chunk's category_id (see ai/categories.py).
# force_leaf renders a node without its children list even if it has some —
# used once, for the synthetic "documents with no subfolder" root entry,
# whose real children are already rendered as separate top-level siblings.
def _category_node_html(tree: CategoryTree, node_id: str, *, force_leaf: bool = False) -> str:
    node = tree.nodes[node_id]
    is_real = node.own_documents > 0
    has_children = bool(node.children) and not force_leaf
    label = html.escape(node.label)
    node_id_attr = html.escape(node_id, quote=True)
    if has_children:
        toggle = (
            '<button type="button" class="cat-toggle" aria-expanded="false" '
            f'aria-label="Extinde {label}">▸</button>'
        )
    else:
        toggle = '<span class="cat-toggle cat-toggle-spacer" aria-hidden="true"></span>'
    row = (
        '<div class="cat-row">'
        f"{toggle}"
        '<label class="cat-check-label">'
        f'<input type="checkbox" class="cat-checkbox" data-id="{node_id_attr}">'
        f'<span class="cat-label-text">{label} <span class="cat-count">({node.total_documents})</span></span>'
        "</label>"
        "</div>"
    )
    children_html = ""
    if has_children:
        items = "".join(_category_node_html(tree, child_id) for child_id in node.children)
        children_html = f'<ul class="cat-children" hidden>{items}</ul>'
    return (
        f'<li class="cat-node" data-id="{node_id_attr}" data-real="{"1" if is_real else "0"}">'
        f"{row}{children_html}"
        "</li>"
    )


# Build the collapsible "Filtrează sursele" panel from the category tree
# loaded by Retriever (None when the current index predates category
# support). Selection state lives entirely client-side, in category_filter.js
# — this only renders the static starting markup, always fully unchecked
# ("every category" is the unopened-panel default, per session.selected_categories).
def category_filter_panel_html(tree: CategoryTree | None) -> str:
    # No id on this outer <section> — main.py sets elem_id="category-filter-panel"
    # on the gr.HTML(...) call instead, so that id lands on Gradio's own wrapper
    # (a direct flex child of its Column) rather than on this nested markup,
    # which is what lets the panel's width/alignment CSS rule actually apply.
    if tree is None:
        return (
            '<section class="category-filter-panel">'
            '<p class="category-filter-unavailable">'
            "Filtrarea pe categorii nu este disponibilă până la reconstruirea indexului."
            "</p></section>"
        )
    root = tree.nodes[tree.root_id]
    top_items = []
    if root.own_documents > 0:
        top_items.append(_category_node_html(tree, tree.root_id, force_leaf=True))
    top_items.extend(_category_node_html(tree, child_id) for child_id in root.children)
    tree_html = f'<ul class="category-tree" data-category-tree>{"".join(top_items)}</ul>'
    return (
        '<section class="category-filter-panel">'
        '<details class="category-filter-details">'
        '<summary class="category-filter-summary">'
        '<span aria-hidden="true">🗂️</span> Filtrează sursele (opțional)'
        "</summary>"
        '<div class="category-filter-body">'
        '<div class="category-filter-toolbar">'
        '<p class="category-filter-status" data-category-status>Se caută în toate sursele.</p>'
        '<button type="button" class="category-filter-reset" data-category-reset>Toate sursele</button>'
        "</div>"
        f"{tree_html}"
        "</div>"
        "</details>"
        "</section>"
    )
