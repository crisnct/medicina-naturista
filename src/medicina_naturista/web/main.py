"""Gradio conversation UI mounted on a small FastAPI application."""
from __future__ import annotations

import asyncio
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
from fastapi.responses import FileResponse, Response

from medicina_naturista.config import settings

CACHE_ROOT = Path(os.getenv(
    "GRADIO_TEMP_DIR",
    "/tmp/gradio-cache" if os.name != "nt" else str(settings.temp_dir.parent / "tmp" / "gradio-cache"),
)).resolve()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(CACHE_ROOT)
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402

from medicina_naturista.ai.client import AIUnavailable, XAIClient
from medicina_naturista.integrations.gmail import send_report
from medicina_naturista.reporting.pdf import create_pdf
from medicina_naturista.ai.retrieval import Retriever
from medicina_naturista.core.models import SessionData
from medicina_naturista.core.sessions import SessionStore
from medicina_naturista.web.handlers import (
    _append,
    _ask,
    _download_html,
    _fragments_panel_html,
    _recommendation_text,
    _report_filename,
    generate_button_processing_update,
    generate_button_ready_update,
    generate_row_hidden_update,
    generate_row_visible_update,
    processing_button_update,
    ready_button_update,
)
from medicina_naturista.web.ui import (
    APP_CSS,
    ASSISTANT_HEADER_HTML,
    AUTO_SCROLL_JS,
    COMPOSER_STATE_JS,
    HERO_HTML,
    MESSAGE_HELPER_HTML,
    THEME,
)

logger = logging.getLogger("naturist.web")
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
WELCOME = "Bună ziua! 👋"
store = SessionStore(settings.temp_dir, settings.session_idle_seconds, settings.session_max_seconds)
retriever = Retriever(settings.index_dir, settings.documents_dir)
REPORT_STARTED = (
    f"🔍 Caut în cele {retriever.document_count} documente interne disponibile. Vă rog să așteptați."
)
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


@app.get("/assets/ornament-fitoterapie-antet.svg")
async def ornament_asset() -> FileResponse:
    """Serve the shared botanical ornament to the Gradio page."""
    return FileResponse(ORNAMENT_SVG, media_type="image/svg+xml")


@app.get("/api/reports/{tab_id}/{report_id}")
# Return the PDF belonging to the current tab and report identifier.
def download(tab_id: str, report_id: str, request: Request):
    sid = request.cookies.get(COOKIE)
    session = store.get(sid or "", tab_id, create=False)
    if session is None or session.report_id != report_id or session.report_bytes is None:
        logger.warning("report_download_rejected reason=not_found tab_id=%s", tab_id)
        raise HTTPException(status_code=404, detail="Raportul nu este disponibil pentru această sesiune.")
    filename = _report_filename(session)
    logger.info("report_downloaded tab_id=%s report_bytes=%s", tab_id, len(session.report_bytes))
    return Response(
        session.report_bytes,
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
        return list(session.history), _download_html(session)


# Store a user message and reset any state tied to a previous health problem.
def on_message(message: str, request: gr.Request):
    session = _current(request)
    message = (message or "").strip()
    if not message:
        return "", list(session.history), _download_html(session), "", generate_row_hidden_update()
    if len(message) > settings.max_chat_chars:
        raise gr.Error(f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        previous_health_problem = session.profile.health_problem
        _append(session, "user", message)
        session.clear_report()
        session.pending_evidence = None
        session.profile.replace_health_problem(message)
        _append(session, "assistant", REPORT_STARTED)
        logger.info(
            "user_message_accepted tab_id=%s chars=%s replaced_health_problem=%s health_context_entries=%s",
            session.tab_id,
            len(message),
            bool(previous_health_problem),
            len(session.profile.health_context),
        )
        return "", list(session.history), _download_html(session), "", generate_row_hidden_update()


# Retrieve local evidence only — no AI request — and show it to the patient
# for review, grouped by document, before they choose to generate a report.
def on_find_fragments(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not session.profile.report_ready:
            logger.info("fragments_skipped tab_id=%s reason=health_problem_missing", session.tab_id)
            _append(session, "assistant", "Descrieți problema de sănătate înainte de căutare.")
            return list(session.history), "", generate_row_hidden_update(), generate_button_ready_update()
        logger.info("report_stage_started stage=retrieval tab_id=%s", session.tab_id)
        evidence = retriever.collect(session)
        logger.info(
            "report_stage_completed stage=retrieval tab_id=%s evidence_entries=%s evidence_chars=%s",
            session.tab_id,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
        )
        if not evidence:
            session.pending_evidence = None
            _append(session, "assistant", "Nu am găsit fragmente relevante în sursele locale.")
            return list(session.history), "", generate_row_hidden_update(), generate_button_ready_update()
        session.pending_evidence = evidence
        # The "found N fragments in M documents" summary is rendered inside
        # the fragments panel itself (see _fragments_panel_html), not posted
        # as a separate chat message — that lets it sit directly above the
        # fragment list with its own styling instead of blending in with
        # every other assistant chat bubble.
        return (
            list(session.history),
            _fragments_panel_html(evidence),
            generate_row_visible_update(),
            generate_button_ready_update(),
        )


# Send the fragments the patient already reviewed to the AI, generate the PDF, and update the chat.
def on_generate_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        evidence = session.pending_evidence
        if not session.profile.report_ready or not evidence:
            logger.info("report_skipped tab_id=%s reason=no_pending_evidence", session.tab_id)
            _append(session, "assistant", "Nu există fragmente pregătite. Descrieți din nou problema de sănătate.")
            return (
                list(session.history),
                _download_html(session),
                generate_row_hidden_update(),
                generate_button_ready_update(),
            )
        try:
            logger.info("report_stage_started stage=ai tab_id=%s evidence_entries=%s", session.tab_id, len(evidence))
            sections = ai.generate(session.profile.as_dict(), evidence)
            logger.info(
                "report_stage_completed stage=ai tab_id=%s recommendation_items=%s",
                session.tab_id,
                sum(len(items) for items in sections.values()),
            )
            logger.info("report_stage_started stage=pdf tab_id=%s", session.tab_id)
            report = create_pdf(session.profile.as_dict(), sections, evidence)
            logger.info("report_stage_completed stage=pdf tab_id=%s bytes=%s", session.tab_id, len(report))
            session.report_bytes = report
            session.report_id = secrets.token_urlsafe(18)
            logger.info("report_stage_started stage=email tab_id=%s", session.tab_id)
            try:
                email_status = send_report(
                    session.profile.health_problem,
                    session.report_bytes,
                    _report_filename(session),
                )
            except Exception as exc:
                # Email is best-effort: the already stored PDF and chat history
                # must remain available when Google API delivery is unavailable.
                logger.exception(
                    "report_stage_failed stage=email tab_id=%s type=%s",
                    session.tab_id,
                    type(exc).__name__,
                )
            else:
                logger.info(
                    "report_stage_completed stage=email tab_id=%s result=%s",
                    session.tab_id,
                    email_status,
                )
            _append(session, "assistant", _recommendation_text(sections, evidence))
            session.pending_evidence = None
        except AIUnavailable as exc:
            logger.error("report_failed tab_id=%s stage=ai type=%s", session.tab_id, type(exc).__name__)
            _append(session, "assistant", str(exc))
            return (
                list(session.history),
                _download_html(session),
                generate_row_visible_update(),
                generate_button_ready_update(),
            )
        except Exception as exc:
            logger.exception(
                "report failed: type=%s message=%s",
                type(exc).__name__,
                str(exc) or "<empty>",
            )
            _append(session, "assistant", "Raportul nu a putut fi generat. Încercați din nou.")
            return (
                list(session.history),
                _download_html(session),
                generate_row_visible_update(),
                generate_button_ready_update(),
            )
        return (
            list(session.history),
            _download_html(session),
            generate_row_hidden_update(),
            generate_button_ready_update(),
        )


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
            fragments_panel = gr.HTML(elem_id="fragments-panel")
            with gr.Row(elem_id="generate-recipe-panel", visible=False) as generate_row:
                gr.HTML(
                    '<div class="generate-recipe-copy">'
                    '<span class="generate-recipe-icon" aria-hidden="true">💊</span>'
                    '<span><strong>Trimite-le la AI pentru a le combina și generează apoi '
                    'documentul cu recomandări</strong></span>'
                    '</div>',
                    elem_id="generate-recipe-copy-html",
                )
                generate_button = gr.Button(
                    "💊 Generează rețeta",
                    elem_id="generate-recipe",
                )
            download_box = gr.HTML(elem_id="report-download")
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

    load_event = demo.load(on_load, outputs=[chatbot, download_box], queue=False)
    send_event = send.click(
        on_message,
        inputs=[message],
        outputs=[message, chatbot, download_box, fragments_panel, generate_row],
        queue=False,
    )
    submit_event = message.submit(
        on_message,
        inputs=[message],
        outputs=[message, chatbot, download_box, fragments_panel, generate_row],
        queue=False,
    )
    load_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    for event in (send_event, submit_event):
        notice_event = event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
        processing_event = notice_event.then(
            processing_button_update,
            outputs=[send],
            queue=False,
        )
        fragments_event = processing_event.then(
            on_find_fragments,
            outputs=[chatbot, fragments_panel, generate_row, generate_button],
            queue=False,
        )
        fragments_event.then(ready_button_update, outputs=[send], queue=False).then(
            fn=None, js=AUTO_SCROLL_JS, queue=False
        )

    generate_event = generate_button.click(
        generate_button_processing_update, outputs=[generate_button], queue=False
    ).then(fn=None, js=AUTO_SCROLL_JS, queue=False).then(
        on_generate_report,
        outputs=[chatbot, download_box, generate_row, generate_button],
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
