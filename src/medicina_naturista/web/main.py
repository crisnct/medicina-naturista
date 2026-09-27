"""Gradio conversation UI mounted on a small FastAPI application."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response

from medicina_naturista.config import settings

CACHE_ROOT = Path(os.getenv(
    "GRADIO_TEMP_DIR",
    "/tmp/gradio-cache" if os.name != "nt" else str(settings.temp_dir.parent / "tmp" / "gradio-cache"),
)).resolve()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(CACHE_ROOT)
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402

from medicina_naturista.ai.client import AIUnavailable, XAIClient, fit_evidence_to_context
from medicina_naturista.integrations.gmail import EMAIL_SKIPPED, send_report
from medicina_naturista.reporting.pdf import create_pdf
from medicina_naturista.ai.retrieval import Retriever
from medicina_naturista.core.models import PendingSearch, SessionData, StoredReport
from medicina_naturista.core.sessions import SessionStore
from medicina_naturista.web.handlers import (
    _append,
    _ask,
    _download_html,
    _fragments_panel_html,
    _generate_panel_html,
    _parse_category_selection,
    _recommendation_text,
    _report_filename,
    _set_generate_panel,
    processing_button_update,
    ready_button_update,
)
from medicina_naturista.web.ui import (
    APP_CSS,
    ASSISTANT_HEADER_HTML,
    AUTO_SCROLL_JS,
    CATEGORY_FILTER_JS,
    COLLAPSE_FRAGMENTS_JS,
    COMPOSER_STATE_JS,
    HERO_HTML,
    MESSAGE_HELPER_HTML,
    THEME,
    category_filter_panel_html,
)

logger = logging.getLogger("naturist.web")
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
OWNER_COOKIE = "naturist_owner"
OWNER_COOKIE_MAX_AGE = 10 * 365 * 24 * 3600
OWNER_ONLY_MESSAGE = "Generarea rețetei nu este disponibilă momentan pentru acest cont."
WELCOME = "Bună ziua! 👋"
store = SessionStore(settings.temp_dir, settings.session_idle_seconds, settings.session_max_seconds)
retriever = Retriever(settings.index_dir, settings.documents_dir)
# Static starting markup for the "Setează sursele" panel, built once from
# the category tree Retriever loaded (None on an index built before category
# support existed — the panel then shows an explanatory notice instead).
# Rebuilding the index regenerates categories.json; picking it up here only
# takes restarting the application, same as the rest of the loaded index.
CATEGORY_FILTER_HTML = category_filter_panel_html(retriever.category_tree)
# Default value for the hidden #category-selection field: every known
# category, matching the panel's own default (every checkbox starts checked —
# see category_filter_panel_html). Computed here, not left as "[]", so the
# very first search — before category_filter.js has had a chance to run —
# already carries the same "search everywhere" selection the checkboxes show,
# instead of racing with the JS that would otherwise be the only thing to set it.
DEFAULT_CATEGORY_SELECTION = (
    json.dumps(sorted(retriever.category_tree.known_ids())) if retriever.category_tree is not None else "[]"
)
NO_CATEGORY_SELECTED_MESSAGE = (
    "Nicio sursă selectată. Bifați cel puțin o categorie în panoul „Setează sursele” înainte de căutare."
)
EMAIL_OFFER = (
    "Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit."
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


# Documents the given category ids actually cover, for the "Caut rapid în
# cele N documente" notice — the whole corpus (retriever.document_count) when
# the index has no category tree (nothing to restrict by), otherwise the sum
# of each selected category's own_documents (never total_documents, which
# would double-count a folder together with its own subfolders if both ended
# up selected). An id outside the known set (stale, or no tree at all) is
# simply not counted, same as everywhere else category ids are consumed.
def _document_count_for_categories(category_ids: set[str]) -> int:
    tree = getattr(retriever, "category_tree", None)
    if tree is None:
        return getattr(retriever, "document_count", 0)
    known = tree.known_ids()
    return sum(tree.nodes[category_id].own_documents for category_id in category_ids if category_id in known)


# Build the "Caut rapid în cele N documente..." notice for the categories
# currently selected on the session.
def _report_started_message(session: SessionData) -> str:
    count = _document_count_for_categories(session.selected_categories)
    return f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați."
ai = XAIClient(settings)
app = FastAPI(title="Chatbot naturist", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=[], allow_headers=[])
ORNAMENT_SVG = (
    Path(__file__).resolve().parent / "static" / "images" / "ornament-fitoterapie-antet.svg"
)

rate_lock = __import__("threading").Lock()
rate_events: dict[str, deque[float]] = defaultdict(deque)


# Extract and validate the application session cookie from a raw Cookie header.
def _cookie_from_header(header: str) -> str | None:
    try:
        cookies = SimpleCookie()
        cookies.load(header)
        value = cookies[COOKIE].value if COOKIE in cookies else None
        return value if value and COOKIE_RE.fullmatch(value) else None
    except Exception:
        return None


# Derive the owner cookie value from the secret key; empty when no OWNER_KEY is configured.
def _owner_token() -> str:
    key = os.getenv("OWNER_KEY", "")
    if not key:
        return ""
    return hmac.new(key.encode(), b"naturist-owner", hashlib.sha256).hexdigest()


# Tell whether the raw Cookie header carries a valid owner cookie (fails closed without OWNER_KEY).
def _is_owner(cookie_header: str) -> bool:
    expected = _owner_token()
    if not expected:
        return False
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        value = cookies[OWNER_COOKIE].value if OWNER_COOKIE in cookies else ""
    except Exception:
        return False
    return hmac.compare_digest(value, expected)


# Resolve the authenticated browser tab to its cookie and Gradio session identifiers.
def _identity(request: gr.Request) -> tuple[str, str]:
    if request is None or not request.session_hash:
        raise gr.Error("Sesiunea nu este disponibilă. Reîncărcați pagina.")
    cookie = _cookie_from_header(str(dict(request.headers).get("cookie", "")))
    if not cookie:
        raise gr.Error("Sesiunea a expirat. Reîncărcați pagina.")
    return cookie, str(request.session_hash)


# Return the current tab session or raise a user-facing expiration error.
def _current(request: gr.Request, create: bool = False) -> SessionData:
    cookie, tab = _identity(request)
    session = store.get(cookie, tab, create=create)
    if session is None:
        raise gr.Error("Sesiunea a expirat. Reîncărcați pagina.")
    return session




@app.middleware("http")
# Enforce origin and request-rate protections, then maintain the session cookie.
async def session_and_limits(request: Request, call_next):
    path = request.url.path
    if request.method in {"POST", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            logger.warning("http_request_rejected reason=origin_mismatch method=%s path=%s", request.method, path)
            return Response("Forbidden", status_code=403)
        if path.startswith(("/gradio_api/", "/api/")) or "/gradio_api/" in path:
            proxy = os.getenv("TRUST_PROXY", "false").lower() == "true"
            forwarded = request.headers.get("x-forwarded-for", "") if proxy else ""
            client_ip = forwarded.split(",")[0].strip() if forwarded else (
                request.client.host if request.client else "unknown"
            )
            now = time.monotonic()
            with rate_lock:
                events = rate_events[client_ip]
                while events and now - events[0] > 60:
                    events.popleft()
                if len(events) >= settings.max_requests_per_minute:
                    logger.warning(
                        "http_request_rejected reason=rate_limit method=%s path=%s limit=%s",
                        request.method,
                        path,
                        settings.max_requests_per_minute,
                    )
                    return Response("Prea multe cereri. Încercați mai târziu.", status_code=429)
                events.append(now)
    sid = request.cookies.get(COOKIE)
    if not sid or not COOKIE_RE.fullmatch(sid):
        sid = secrets.token_urlsafe(32)
        fresh = True
    else:
        fresh = False
    response = await call_next(request)
    if fresh and path != "/healthz":
        response.set_cookie(
            COOKIE, sid, httponly=True,
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            samesite="strict", path="/",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.on_event("startup")
# Start periodic session cleanup and log the application configuration.
async def startup() -> None:
    logger.info(
        "application_started index=%s documents=%s log_fragment_text=%s",
        settings.index_dir,
        settings.documents_dir,
        settings.log_fragment_text,
    )

    # Periodically remove expired sessions from the in-memory store.
    async def cleanup() -> None:
        while True:
            await asyncio.sleep(60)
            store.sweep()
    app.state.cleanup_task = asyncio.create_task(cleanup())


@app.on_event("shutdown")
# Stop background resources and close the AI HTTP client during shutdown.
async def shutdown() -> None:
    logger.info("application_shutdown active_sessions=%s", store.count())
    app.state.cleanup_task.cancel()
    ai.close()


@app.get("/healthz")
# Report application readiness only when the xAI credential is configured.
def healthz():
    try:
        configured = bool(settings.api_key())
    except (OSError, UnicodeError):
        configured = False
    if not configured:
        raise HTTPException(status_code=503, detail="Secretul xAI lipsește sau nu este un fișier valid.")
    return {"status": "ok", "index": "ready"}


@app.get("/owner")
# Mark this browser as the owner's by setting a long-lived cookie when the secret key matches.
def owner_login(key: str = ""):
    expected = os.getenv("OWNER_KEY", "")
    if not expected or not hmac.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(status_code=404)
    response = RedirectResponse(url="./", status_code=303)
    response.set_cookie(
        OWNER_COOKIE, _owner_token(), max_age=OWNER_COOKIE_MAX_AGE, httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict", path="/",
    )
    logger.info("owner_cookie_issued")
    return response


@app.get("/assets/ornament-fitoterapie-antet.svg")
async def ornament_asset() -> FileResponse:
    """Serve the shared botanical ornament to the Gradio page."""
    return FileResponse(ORNAMENT_SVG, media_type="image/svg+xml")


@app.get("/api/reports/{tab_id}/{report_id}")
# Return the PDF belonging to the current tab and report identifier.
def download(tab_id: str, report_id: str, request: Request):
    sid = request.cookies.get(COOKIE)
    session = store.get(sid or "", tab_id, create=False)
    report = session.reports.get(report_id) if session else None
    if report is None:
        logger.warning("report_download_rejected reason=not_found tab_id=%s", tab_id)
        raise HTTPException(status_code=404, detail="Raportul nu este disponibil pentru această sesiune.")
    filename = report.filename
    logger.info("report_downloaded tab_id=%s report_bytes=%s", tab_id, len(report.data))
    return Response(
        report.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Cache-Control": "no-store",
        },
    )


# Initialize a browser session and return its current chat history and download link.
def on_load(request: gr.Request):
    session = _current(request, create=True)
    with session.lock:
        if not session.history:
            _append(session, "assistant", WELCOME)
            question = session.profile.next_question()
            if question:
                _ask(session, question)
        logger.info("session_loaded tab_id=%s history_entries=%s", session.tab_id, len(session.history))
        return list(session.history)


# Store a user message and start a new health-problem context. Earlier searches,
# their "Generează rețeta" sections and their PDFs stay available in the chat.
# categories_json is the JSON array category_filter.js keeps in the hidden
# #category-selection field (see _parse_category_selection); it is read here,
# once per message, and stored on the session so the retrieval step chained
# after this one (on_find_fragments) applies exactly what was selected when
# the patient hit send — a later change to the panel does not retroactively
# affect a search already in flight.
def on_message(message: str, request: gr.Request, categories_json: str = "[]"):
    session = _current(request)
    message = (message or "").strip()
    if not message:
        return "", list(session.history)
    if len(message) > settings.max_chat_chars:
        raise gr.Error(f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        session.email_request_handled = False
        if session.report_bytes is not None and EMAIL_PATTERN.fullmatch(message):
            _append(session, "user", message)
            session.email_request_handled = True
            _append(session, "assistant", _send_report_email(session, message))
            return "", list(session.history)
        previous_health_problem = session.profile.health_problem
        _append(session, "user", message)
        session.profile.replace_health_problem(message)
        session.selected_categories = _parse_category_selection(categories_json)
        _append(session, "assistant", _report_started_message(session))
        logger.info(
            "user_message_accepted tab_id=%s chars=%s replaced_health_problem=%s health_context_entries=%s "
            "selected_categories=%s",
            session.tab_id,
            len(message),
            bool(previous_health_problem),
            len(session.profile.health_context),
            len(session.selected_categories),
        )
        return "", list(session.history)


# Email the finished report to the address typed in chat and return the chat reply.
def _send_report_email(session: SessionData, address: str) -> str:
    latest = session.reports.get(session.report_id or "")
    try:
        status = send_report(
            latest.health_problem if latest else session.profile.health_problem,
            session.report_bytes,
            latest.filename if latest else _report_filename(session),
            address,
        )
    except Exception as exc:
        logger.exception("report_stage_failed stage=email tab_id=%s type=%s", session.tab_id, type(exc).__name__)
        return "Nu am putut trimite documentul pe mail. Încercați din nou."
    logger.info("report_stage_completed stage=email tab_id=%s result=%s", session.tab_id, status)
    if status == EMAIL_SKIPPED:
        return "Trimiterea pe mail nu este configurată momentan."
    return f"✅ Am trimis documentul la {address}."


# Retrieve local evidence only — no AI request — and show it in the chat,
# followed by its own "Generează rețeta" section, so the patient can review the
# fragments before choosing to generate a report. Each search gets its own section.
def on_find_fragments(request: gr.Request):
    session = _current(request)
    with session.lock:
        if session.email_request_handled:
            session.email_request_handled = False
            return list(session.history)
        if not session.profile.report_ready:
            logger.info("fragments_skipped tab_id=%s reason=health_problem_missing", session.tab_id)
            _append(session, "assistant", "Descrieți problema de sănătate înainte de căutare.")
            return list(session.history)
        # An index without category support (no categories.json) has no
        # panel to select from, so it never requires a selection — only an
        # index that actually loaded a category tree enforces this. getattr
        # also covers test doubles standing in for `retriever` with no
        # category_tree attribute at all.
        if getattr(retriever, "category_tree", None) is not None and not session.selected_categories:
            logger.info("fragments_skipped tab_id=%s reason=no_category_selected", session.tab_id)
            _append(session, "assistant", NO_CATEGORY_SELECTED_MESSAGE)
            return list(session.history)
        logger.info("report_stage_started stage=retrieval tab_id=%s", session.tab_id)
        # Show only what the AI request can carry (MAX_CONTEXT_CHARS), so the UI
        # never lists fragments that would be dropped later.
        evidence = fit_evidence_to_context(retriever.collect(session))
        logger.info(
            "report_stage_completed stage=retrieval tab_id=%s evidence_entries=%s evidence_chars=%s",
            session.tab_id,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
        )
        if not evidence:
            _append(session, "assistant", "Nu am găsit fragmente relevante în sursele locale.")
            return list(session.history)
        search_id = secrets.token_hex(6)
        # The profile is snapshotted: the patient may describe another problem
        # before pressing this search's button.
        session.add_search(search_id, PendingSearch(profile=session.profile.as_dict(), evidence=evidence))
        # The panel (summary + fragment list) and the generate section are chat
        # messages, so they appear in chronological order after the search notice.
        _append(session, "assistant", _fragments_panel_html(evidence))
        _append(session, "assistant", _generate_panel_html(search_id))
        return list(session.history)


# Turn one search's "Generează rețeta" section into its in-progress state as soon as it is clicked.
def on_generate_start(search_id: str, request: gr.Request):
    session = _current(request)
    search_id = (search_id or "").strip()
    with session.lock:
        if search_id in session.searches:
            _set_generate_panel(session, search_id, _generate_panel_html(search_id, busy=True))
        return list(session.history), ""


# Reject non-owner visitors with a red notice; otherwise generate the report for the clicked search.
def on_generate_report(search_id: str, request: gr.Request):
    session = _current(request)
    search_id = (search_id or "").strip()
    if not _is_owner(str(dict(request.headers).get("cookie", ""))):
        logger.info("report_skipped tab_id=%s reason=not_owner", session.tab_id)
        with session.lock:
            if search_id in session.searches:
                _set_generate_panel(session, search_id, _generate_panel_html(search_id))
            return (
                list(session.history),
                f'<div class="owner-notice-panel" role="alert">{html.escape(OWNER_ONLY_MESSAGE)}</div>',
            )
    return _generate_report(search_id, request), ""


# Send the fragments the patient already reviewed to the AI, generate the PDF, and update the chat.
def _generate_report(search_id: str, request: gr.Request):
    session = _current(request)
    with session.lock:
        search = session.searches.get(search_id)
        if search is None:
            logger.info("report_skipped tab_id=%s reason=no_pending_evidence", session.tab_id)
            _append(session, "assistant", "Nu există fragmente pregătite. Descrieți din nou problema de sănătate.")
            return list(session.history)
        profile, evidence = search.profile, search.evidence
        try:
            logger.info("report_stage_started stage=ai tab_id=%s evidence_entries=%s", session.tab_id, len(evidence))
            sections = ai.generate(profile, evidence)
            logger.info(
                "report_stage_completed stage=ai tab_id=%s recommendation_items=%s",
                session.tab_id,
                sum(len(items) for items in sections.values()),
            )
            logger.info("report_stage_started stage=pdf tab_id=%s", session.tab_id)
            report = create_pdf(profile, sections, evidence)
            logger.info("report_stage_completed stage=pdf tab_id=%s bytes=%s", session.tab_id, len(report))
            report_id = secrets.token_urlsafe(18)
            session.add_report(
                report_id,
                StoredReport(report, _report_filename(session, profile), profile.get("health_problem", "")),
            )
            # The generated report replaces this search's section; the PDF section follows it in the chat.
            _set_generate_panel(session, search_id, None)
            _append(session, "assistant", _recommendation_text(sections, evidence))
            _append(session, "assistant", _download_html(session, report_id, profile))
            _append(session, "assistant", EMAIL_OFFER)
            session.searches.pop(search_id, None)
        except AIUnavailable as exc:
            logger.error("report_failed tab_id=%s stage=ai type=%s", session.tab_id, type(exc).__name__)
            _set_generate_panel(session, search_id, _generate_panel_html(search_id))
            _append(session, "assistant", str(exc))
        except Exception as exc:
            logger.exception(
                "report failed: type=%s message=%s",
                type(exc).__name__,
                str(exc) or "<empty>",
            )
            _set_generate_panel(session, search_id, _generate_panel_html(search_id))
            _append(session, "assistant", "Raportul nu a putut fi generat. Încercați din nou.")
        return list(session.history)


# Close the current session and return a final assistant message to the UI.
def on_end(request: gr.Request):
    cookie, tab = _identity(request)
    logger.info("session_end_requested tab_id=%s", tab)
    store.delete(cookie, tab)
    return [
        {"role": "assistant", "content": "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă."}
    ], ""


# Remove the browser session when the page is unloaded.
def on_unload(request: gr.Request) -> None:
    try:
        cookie, tab = _identity(request)
        logger.info("session_unload tab_id=%s", tab)
        store.delete(cookie, tab)
    except Exception:
        pass


with gr.Blocks(
    title="Tratamente Naturiste Adjuvante",
    analytics_enabled=False,
    delete_cache=(60, 60),
    fill_width=True,
) as demo:
    with gr.Column(elem_id="app-shell"):
        gr.HTML(HERO_HTML, elem_id="hero-component")
        with gr.Column(elem_id="conversation-card"):
            with gr.Row(elem_id="chat-header"):
                gr.HTML(ASSISTANT_HEADER_HTML)
            chatbot = gr.Chatbot(
                show_label=False,
                height=None,
                max_height=None,
                autoscroll=True,
                elem_id="medical-chatbot",
                render_markdown=True,
                sanitize_html=True,
                allow_file_downloads=False,
                buttons=["copy"],
                feedback_options=None,
                layout="bubble",
            )
            owner_notice = gr.HTML(elem_id="owner-notice")
            # Hidden controls: the "Generează rețeta" button inside each chat message
            # sets the target search id here and clicks the hidden button (see app.js).
            generate_target = gr.Textbox(elem_id="generate-target", elem_classes=["hidden-control"], show_label=False)
            generate_button = gr.Button("Generează rețeta", elem_id="generate-recipe", elem_classes=["hidden-control"])
            # The checked real category ids, kept in sync by category_filter.js
            # (see static/js/category_filter.js); read once per sent message by
            # on_message (see _parse_category_selection). Empty ("[]") means
            # every category — the panel's unopened default.
            category_selection = gr.Textbox(
                value=DEFAULT_CATEGORY_SELECTION,
                elem_id="category-selection",
                elem_classes=["hidden-control"],
                show_label=False,
            )
            gr.HTML(MESSAGE_HELPER_HTML, elem_id="message-helper")
            with gr.Row(elem_id="message-row"):
                message = gr.Textbox(
                    label="Descrierea problemei de sănătate",
                    show_label=False,
                    placeholder="Problema de sănătate...",
                    lines=1,
                    max_lines=1,
                    max_length=settings.max_chat_chars,
                    scale=1,
                    elem_id="health-message",
                    html_attributes={
                        "aria-label": "Descrieți problema de sănătate",
                        "aria-describedby": "message-helper",
                    },
                )
                send = gr.Button(
                    "📨 Trimite",
                    variant="primary",
                    size="lg",
                    scale=0,
                    elem_id="send-message",
                )
            # elem_id lands on Gradio's own wrapper (a direct flex child of this
            # Column, unlike anything inside CATEGORY_FILTER_HTML) — the same
            # pattern MESSAGE_HELPER_HTML/"message-helper" above uses, so the
            # panel's width/alignment CSS rule (#category-filter-panel in
            # app.css) actually applies. category_filter.js's panel() lookup
            # targets this same id. Placed below the composer, per the
            # request to keep "Setează sursele" under the message box.
            gr.HTML(CATEGORY_FILTER_HTML, elem_id="category-filter-panel")

    load_event = demo.load(on_load, outputs=[chatbot], queue=False)
    send_event = send.click(
        on_message,
        inputs=[message, category_selection],
        outputs=[message, chatbot],
        queue=False,
    )
    submit_event = message.submit(
        on_message,
        inputs=[message, category_selection],
        outputs=[message, chatbot],
        queue=False,
    )
    load_event.then(fn=None, js=CATEGORY_FILTER_JS, queue=False)
    load_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    for event in (send_event, submit_event):
        notice_event = event.then(fn=None, js=COLLAPSE_FRAGMENTS_JS, queue=False).then(
            fn=None, js=AUTO_SCROLL_JS, queue=False
        )
        processing_event = notice_event.then(
            lambda: (processing_button_update(), ""),
            outputs=[send, owner_notice],
            queue=False,
        )
        fragments_event = processing_event.then(
            on_find_fragments,
            outputs=[chatbot],
            queue=False,
        )
        fragments_event.then(ready_button_update, outputs=[send], queue=False).then(
            fn=None, js=AUTO_SCROLL_JS, queue=False
        )

    generate_event = generate_button.click(
        on_generate_start,
        inputs=[generate_target],
        outputs=[chatbot, owner_notice],
        queue=False,
    ).then(fn=None, js=COLLAPSE_FRAGMENTS_JS, queue=False).then(
        on_generate_report,
        inputs=[generate_target],
        outputs=[chatbot, owner_notice],
        queue=False,
    )
    generate_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    demo.unload(on_unload)

_gradio_root_path = os.getenv("GRADIO_ROOT_PATH") or None
app = gr.mount_gradio_app(
    app,
    demo,
    path="/",
    root_path=_gradio_root_path,
    blocked_paths=[
        str(CACHE_ROOT),
        str(settings.temp_dir.resolve()),
        str(settings.documents_dir.resolve()),
        str(settings.index_dir.resolve()),
        str((settings.index_dir.parent / "model_cache").resolve()),
        str((settings.index_dir.parents[1] / ".env").resolve()),
    ],
    show_error=False,
    footer_links=[],
    theme=THEME,
    css=APP_CSS,
    js=COMPOSER_STATE_JS,
)
