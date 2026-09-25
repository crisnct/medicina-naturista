"""Gradio conversation UI mounted on a small FastAPI application."""
from __future__ import annotations

import asyncio
import html
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

from web_app.config import settings

CACHE_ROOT = Path(os.getenv(
    "GRADIO_TEMP_DIR",
    "/tmp/gradio-cache" if os.name != "nt" else str(settings.temp_dir.parent / ".gradio_tmp"),
)).resolve()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(CACHE_ROOT)
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402

from web_app.ai import AIUnavailable, XAIClient
from web_app.mailer import send_report
from web_app.reports import (
    bibliography_label,
    build_reference_index,
    create_pdf,
    nutrition_display_groups,
    report_title,
    sort_sections_by_source_count,
)
from web_app.retrieval import Retriever
from web_app.sessions import SessionData, SessionStore

logger = logging.getLogger("naturist.web")
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
WELCOME = "Bună ziua! 👋"
REPORT_STARTED = "⏳ Pregătesc recomandările naturiste pe baza surselor locale. Vă rog să așteptați."
store = SessionStore(settings.temp_dir, settings.session_idle_seconds, settings.session_max_seconds)
retriever = Retriever(settings.index_dir, settings.documents_dir)
ai = XAIClient(settings)
app = FastAPI(title="Chatbot naturist", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=[], allow_headers=[])
ORNAMENT_SVG = Path(__file__).with_name("ornament-fitoterapie-antet.svg")

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
        "application_started index=%s documents=%s max_evidence=%s log_fragment_text=%s",
        settings.index_dir,
        settings.documents_dir,
        settings.max_evidence,
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


# Store a user message, update the health profile, and schedule report generation.
def on_message(message: str, request: gr.Request):
    session = _current(request)
    message = (message or "").strip()
    if not message:
        return "", list(session.history), _download_html(session)
    if len(message) > settings.max_chat_chars:
        raise gr.Error(f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        previous_health_problem = session.profile.health_problem
        _append(session, "user", message)
        session.clear_report()
        session.profile.replace_health_problem(message)
        session.auto_report_pending = True
        _append(session, "assistant", REPORT_STARTED)
        logger.info(
            "user_message_accepted tab_id=%s chars=%s replaced_health_problem=%s health_context_entries=%s",
            session.tab_id,
            len(message),
            bool(previous_health_problem),
            len(session.profile.health_context),
        )
        return "", list(session.history), _download_html(session)


# Retrieve evidence, generate AI sections, create the PDF, and update the chat.
def on_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not session.profile.report_ready:
            logger.info("report_skipped tab_id=%s reason=health_problem_missing", session.tab_id)
            _append(session, "assistant", "Descrieți problema de sănătate înainte de generarea raportului.")
            return list(session.history), _download_html(session)
        try:
            logger.info("report_stage_started stage=retrieval tab_id=%s", session.tab_id)
            evidence = retriever.collect(session)
            logger.info(
                "report_stage_completed stage=retrieval tab_id=%s evidence_entries=%s evidence_chars=%s",
                session.tab_id,
                len(evidence),
                sum(len(item["text"]) for item in evidence.values()),
            )
            if not evidence:
                _append(session, "assistant", "Nu am găsit fragmente relevante în sursele locale.")
                return list(session.history), _download_html(session)
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
        except AIUnavailable as exc:
            logger.error("report_failed tab_id=%s stage=ai type=%s", session.tab_id, type(exc).__name__)
            _append(session, "assistant", str(exc))
        except Exception as exc:
            logger.exception(
                "report failed: type=%s message=%s",
                type(exc).__name__,
                str(exc) or "<empty>",
            )
            _append(session, "assistant", "Raportul nu a putut fi generat. Încercați din nou.")
        return list(session.history), _download_html(session)


# Generate the pending report once after the user submits a message.
def on_auto_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not session.auto_report_pending:
            logger.info("auto_report_skipped tab_id=%s reason=not_pending", session.tab_id)
            return list(session.history), _download_html(session)
        session.auto_report_pending = False
        logger.info("auto_report_triggered tab_id=%s", session.tab_id)
        return on_report(request)


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


theme = gr.themes.Soft(font=["Arial", "sans-serif"])

AUTO_SCROLL_JS = """() => {
    const scrollToLatestMessage = () => {
        const chat = document.getElementById("medical-chatbot");
        const messages = chat?.querySelectorAll('[data-testid="bot"], [data-testid="user"], .message');
        const latest = messages?.length ? messages[messages.length - 1] : chat?.lastElementChild;
        if (latest) {
            latest.scrollIntoView({behavior: "smooth", block: "end"});
        } else {
            window.scrollTo({top: document.documentElement.scrollHeight, behavior: "smooth"});
        }
    };
    requestAnimationFrame(() => setTimeout(scrollToLatestMessage, 80));
}
"""

COMPOSER_STATE_JS = """() => {
    const root = document.getElementById("app-shell") || document;
    const getField = () => root.querySelector("#health-message input, #health-message textarea");
    const getButton = () => root.querySelector("#send-message");

    const syncButton = () => {
        const field = getField();
        const button = getButton();
        if (!field || !button) return;
        const processing = button.textContent.includes("Se pregătește");
        const disabled = processing || field.value.trim().length === 0;
        button.disabled = disabled;
        button.setAttribute("aria-disabled", String(disabled));
    };

    if (!window.__naturistComposerBound) {
        window.__naturistComposerBound = true;
        document.addEventListener("input", (event) => {
            if (event.target.matches?.("#health-message input, #health-message textarea")) syncButton();
        });
        document.addEventListener("click", (event) => {
            if (event.target.closest?.("#send-message")) {
                window.setTimeout(syncButton, 120);
            }
        });
        new MutationObserver(() => window.requestAnimationFrame(syncButton)).observe(root, {
            childList: true,
            subtree: true,
        });
    }
    syncButton();
}
"""

APP_CSS = """
:root {
    --nature-bg: #fff9f2;
    --nature-surface: #ffffff;
    --nature-primary: #2f7d6d;
    --nature-primary-hover: #246657;
    --nature-accent: #ed8a68;
    --nature-text: #24332e;
    --nature-muted: #66736e;
    --nature-border: #dde9e2;
    --nature-soft: #f1f8f4;
    --nature-focus: #be5d3f;
}

body,
.gradio-container {
    min-height: 100vh;
    font-family: Arial, sans-serif !important;
    color: var(--nature-text) !important;
    background:
        radial-gradient(circle at 8% 10%, rgba(237, 138, 104, 0.12), transparent 24rem),
        radial-gradient(circle at 94% 4%, rgba(47, 125, 109, 0.13), transparent 27rem),
        var(--nature-bg) !important;
}

.gradio-container {
    padding: 24px 16px 48px !important;
}

.gradio-container .main,
.gradio-container .wrap,
.gradio-container main.contain {
    width: 100% !important;
    max-width: none !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

#app-shell {
    width: min(100%, 880px) !important;
    max-width: 880px !important;
    margin: 0 auto !important;
    gap: 20px !important;
}

#app-shell .html-container {
    padding: 0 !important;
}

#hero-panel {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    box-sizing: border-box;
    width: 100%;
    padding: 34px 38px 30px;
    border: 1px solid rgba(47, 125, 109, 0.18);
    border-radius: 20px;
    background-color: #f4f9f7;
    background-image: url("/assets/ornament-fitoterapie-antet.svg");
    background-position: center;
    background-repeat: no-repeat;
    background-size: 100% 100%;
    box-shadow: 0 18px 46px rgba(36, 51, 46, 0.08);
}

#hero-component {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

#hero-panel::before,
#hero-panel::after {
    content: "";
    position: absolute;
    z-index: -1;
    border-radius: 60% 40% 64% 36%;
    transform: rotate(-24deg);
}

#hero-panel::before {
    width: 170px;
    height: 105px;
    right: -40px;
    top: -28px;
    background: rgba(47, 125, 109, 0.13);
}

#hero-panel::after {
    width: 110px;
    height: 70px;
    right: 72px;
    bottom: -38px;
    background: rgba(237, 138, 104, 0.16);
}

.hero-kicker {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    padding: 8px 12px;
    border: 1px solid rgba(47, 125, 109, 0.2);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.78);
    color: var(--nature-primary);
    font-size: 14px;
    font-weight: 700;
}

#hero-title {
    max-width: 620px;
    margin: 0;
    color: var(--nature-text);
    font-size: clamp(30px, 5vw, 44px);
    line-height: 1.08;
    letter-spacing: -0.035em;
}

.hero-title-block {
    width: fit-content;
    max-width: min(100%, 620px);
}

.hero-byline {
    margin: 7px 3px 0;
    color: var(--nature-primary);
    font-size: clamp(16px, 2.2vw, 20px);
    font-weight: 700;
    line-height: 1.2;
    text-align: right;
}

.hero-description {
    max-width: 615px;
    margin: 16px 0 20px;
    color: var(--nature-muted);
    font-size: 18px;
    line-height: 1.55;
}

.medical-disclaimer {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    width: fit-content;
    margin: 0;
    padding: 10px 14px;
    border-left: 4px solid var(--nature-accent);
    border-radius: 10px;
    background: #fff7f2;
    color: #5e4a42;
    font-size: 15px;
    line-height: 1.45;
}

#conversation-card {
    --chat-content-width: 88%;
    gap: 14px !important;
    padding: 22px !important;
    border: 1px solid var(--nature-border) !important;
    border-radius: 20px !important;
    background: var(--nature-surface) !important;
    box-shadow: 0 18px 46px rgba(36, 51, 46, 0.08) !important;
}

#chat-header {
    align-items: center !important;
    justify-content: space-between !important;
    gap: 16px !important;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--nature-border);
}

.assistant-identity {
    display: flex;
    align-items: center;
    gap: 11px;
}

.assistant-avatar {
    display: grid;
    width: 44px;
    height: 44px;
    flex: 0 0 44px;
    place-items: center;
    border-radius: 14px;
    background: var(--nature-soft);
    font-size: 23px;
}

.assistant-identity strong,
.assistant-identity small {
    display: block;
}

.assistant-identity strong {
    color: var(--nature-text);
    font-size: 18px;
}

.assistant-identity small {
    margin-top: 2px;
    color: var(--nature-muted);
    font-size: 13px;
}

#end-session {
    flex: 0 0 auto !important;
    min-width: 174px !important;
    max-width: 190px !important;
    min-height: 44px !important;
    border: 1px solid var(--nature-border) !important;
    border-radius: 12px !important;
    background: #fff !important;
    color: var(--nature-muted) !important;
    font-weight: 700 !important;
}

#end-session:hover {
    border-color: #c86c50 !important;
    background: #fff7f2 !important;
    color: #9c452f !important;
}

#medical-chatbot,
#medical-chatbot > div,
#medical-chatbot .wrap,
#medical-chatbot .wrapper,
#medical-chatbot .bubble-wrap {
    height: auto !important;
    max-height: none !important;
    min-height: 0 !important;
    overflow: visible !important;
}

#medical-chatbot {
    width: var(--chat-content-width) !important;
    max-width: var(--chat-content-width) !important;
    align-self: flex-start !important;
    margin: 0 auto 0 0 !important;
    border: 0 !important;
    background: transparent !important;
}

#medical-chatbot .wrap,
#medical-chatbot .wrapper {
    flex: 0 0 auto !important;
}

#medical-chatbot button[aria-label="Clear"] {
    display: none !important;
}

/* Follow the familiar chat convention: assistant left, user right. */
#medical-chatbot .message-row.bot-row,
#medical-chatbot .message-row.bot,
#medical-chatbot .message-wrap.bot,
#medical-chatbot [data-testid="bot"] {
    justify-content: flex-start !important;
    margin-left: 0 !important;
    margin-right: auto !important;
}

#medical-chatbot .message-row.user-row,
#medical-chatbot .message-row.user,
#medical-chatbot .message-wrap.user {
    width: 100% !important;
    max-width: 100% !important;
    justify-content: flex-end !important;
    margin-left: auto !important;
    margin-right: 0 !important;
}

#medical-chatbot .message-row.user-row > .flex-wrap {
    display: flex !important;
    width: 100% !important;
    max-width: 100% !important;
    justify-content: flex-end !important;
}

#medical-chatbot [data-testid="bot"] .message,
#medical-chatbot .bot .message {
    width: 100% !important;
    max-width: 100% !important;
    border: 1px solid var(--nature-border) !important;
    border-radius: 6px 16px 16px 16px !important;
    background: var(--nature-soft) !important;
    color: var(--nature-text) !important;
    line-height: 1.6 !important;
}

#medical-chatbot [data-testid="user"] .message,
#medical-chatbot .user .message {
    max-width: 72% !important;
    border: 1px solid var(--nature-primary) !important;
    border-radius: 16px 6px 16px 16px !important;
    background: var(--nature-primary) !important;
    color: #fff !important;
    line-height: 1.55 !important;
}

#medical-chatbot .bot.message > .message {
    width: 100% !important;
    max-width: 100% !important;
    margin-left: 0 !important;
    margin-right: auto !important;
}

#medical-chatbot .bot.message,
#medical-chatbot .message-row.bot-row,
#medical-chatbot .message-row.bot-row > .flex-wrap {
    width: 100% !important;
    max-width: 100% !important;
}

#medical-chatbot .bot.message {
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

#medical-chatbot .user.message > .message {
    display: block !important;
    box-sizing: border-box !important;
    width: auto !important;
    min-width: 96px !important;
    max-width: 100% !important;
    flex: 0 1 auto !important;
    margin: 0 !important;
    padding: 12px 16px !important;
    border: 1px solid var(--nature-primary) !important;
    border-radius: 16px 6px 16px 16px !important;
    background: var(--nature-primary) !important;
    box-shadow: 0 6px 16px rgba(47, 125, 109, 0.16) !important;
}

#medical-chatbot .user.message {
    display: block !important;
    width: auto !important;
    min-width: 0 !important;
    max-width: 72% !important;
    flex: 0 1 auto !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
}

#medical-chatbot .user.message > .message [data-testid="user"],
#medical-chatbot [data-testid="user"] .message-content {
    width: auto !important;
    min-width: 0 !important;
}

#medical-chatbot [data-testid="user"] {
    margin: 0 !important;
    color: #fff !important;
}

#medical-chatbot [data-testid="user"] .message-content {
    overflow-wrap: anywhere !important;
    word-break: normal !important;
}

#medical-chatbot [data-testid="user"] *,
#medical-chatbot [data-testid="user"] p {
    color: #fff !important;
}

#medical-chatbot [data-testid="user"] p {
    margin: 0 !important;
}

#medical-chatbot .message-buttons {
    opacity: 0 !important;
    transition: opacity 150ms ease !important;
}

#medical-chatbot .message-row:hover + .message-buttons,
#medical-chatbot .message-buttons:hover,
#medical-chatbot .message-buttons:focus-within {
    opacity: 1 !important;
}

#medical-chatbot .message-buttons-right {
    width: 100% !important;
    justify-content: flex-end !important;
    padding-right: 4px !important;
}

#medical-chatbot .message p,
#medical-chatbot .message li {
    font-size: 16px !important;
}

#medical-chatbot .message h2,
#medical-chatbot .message h3,
#medical-chatbot .message p,
#medical-chatbot .message ul,
#medical-chatbot .message ol {
    margin-top: 0.65em;
    margin-bottom: 0.65em;
}

#report-download {
    width: var(--chat-content-width) !important;
    max-width: var(--chat-content-width) !important;
    align-self: flex-start !important;
    min-height: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
}

#report-download:not(:has(.report-ready-panel)) {
    display: none !important;
}

.report-ready-panel {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    padding: 16px 18px;
    border: 1px solid #bfd8c9;
    border-radius: 16px;
    background: #eff8f3;
}

.report-ready-copy {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--nature-text);
}

.report-ready-icon {
    font-size: 24px;
}

.report-ready-copy strong,
.report-ready-copy small {
    display: block;
}

.report-ready-copy small {
    margin-top: 3px;
    color: var(--nature-muted);
    font-size: 13px;
}

.pdf-download {
    display: inline-flex;
    min-height: 46px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 11px 17px;
    border-radius: 12px;
    background: var(--nature-primary);
    box-shadow: 0 8px 18px rgba(47, 125, 109, 0.2);
    color: #fff !important;
    font-weight: 700;
    text-decoration: none !important;
    transition: background-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
}

.pdf-download:hover {
    background: var(--nature-primary-hover);
    box-shadow: 0 10px 22px rgba(47, 125, 109, 0.26);
    transform: translateY(-1px);
}

#message-helper {
    width: var(--chat-content-width) !important;
    max-width: var(--chat-content-width) !important;
    align-self: flex-start !important;
    padding: 0 2px !important;
    color: var(--nature-muted);
    font-size: 14px;
    line-height: 1.45;
}

#message-row {
    width: var(--chat-content-width) !important;
    max-width: var(--chat-content-width) !important;
    align-self: flex-start !important;
    align-items: stretch !important;
    gap: 12px !important;
    padding: 0 !important;
}

#health-message {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    min-width: 0 !important;
}

#health-message > div {
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
}

#health-message textarea {
    box-sizing: border-box !important;
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    padding: 14px 16px !important;
    border: 1px solid var(--nature-border) !important;
    border-radius: 14px !important;
    background: #fffdf9 !important;
    color: var(--nature-text) !important;
    font: 16px/1.5 Arial, sans-serif !important;
    resize: none !important;
    overflow: hidden !important;
}

#health-message textarea::placeholder {
    color: #88938e !important;
}

#health-message textarea:focus {
    border-color: var(--nature-primary) !important;
    box-shadow: 0 0 0 3px rgba(47, 125, 109, 0.18) !important;
}

#send-message {
    display: flex !important;
    width: 180px !important;
    min-width: 180px !important;
    max-width: 180px !important;
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    align-self: stretch !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 16px !important;
    border: 0 !important;
    border-radius: 14px !important;
    background: var(--nature-primary) !important;
    box-shadow: 0 8px 18px rgba(47, 125, 109, 0.22) !important;
    color: #fff !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    white-space: nowrap !important;
    line-height: 1 !important;
}

#send-message:hover:not(:disabled) {
    background: var(--nature-primary-hover) !important;
    transform: translateY(-1px);
}

#send-message:disabled {
    cursor: not-allowed !important;
    background: #9cb9b0 !important;
    box-shadow: none !important;
    opacity: 0.75 !important;
}

#end-session:focus-visible,
#send-message:focus-visible,
.pdf-download:focus-visible {
    outline: 3px solid var(--nature-focus) !important;
    outline-offset: 3px !important;
}

@media (max-width: 640px) {
    .gradio-container.gradio-container-6-28-0 {
        padding: 12px 10px 28px !important;
    }

    #app-shell {
        gap: 14px !important;
    }

    #hero-panel {
        padding: 26px 22px 22px;
        border-radius: 16px;
    }

    .hero-description {
        font-size: 16px;
    }

    #conversation-card {
        --chat-content-width: 100%;
        padding: 16px !important;
        border-radius: 16px !important;
    }

    #chat-header {
        align-items: flex-start !important;
        flex-direction: column !important;
    }

    #end-session {
        width: 100% !important;
        max-width: none !important;
    }

    #medical-chatbot [data-testid="user"] .message,
    #medical-chatbot .user .message {
        max-width: 88% !important;
    }

    .report-ready-panel,
    #message-row {
        align-items: stretch !important;
        flex-direction: column !important;
    }

    .pdf-download,
    #send-message {
        width: 100% !important;
        min-width: 100% !important;
        max-width: none !important;
    }

    #send-message {
        height: 56px !important;
        min-height: 56px !important;
        max-height: 56px !important;
    }
}

@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
    }
}
"""


def _processing_button_update():
    return gr.update(value="⏳ Se pregătește...", interactive=False)


def _ready_button_update():
    return gr.update(value="📨 Trimite", interactive=True)


HERO_HTML = """
<section id="hero-panel" aria-labelledby="hero-title">
    <div class="hero-kicker"><span aria-hidden="true">🌿</span> Ghid naturist bazat pe surse locale</div>
    <div class="hero-title-block">
        <h1 id="hero-title">Tratamente Naturiste Adjuvante</h1>
        <p class="hero-byline">de la Dr. Cuișor</p>
    </div>
    <p class="hero-description">
        Descrieți problema cu care vă confruntați și primiți un raport informativ, clar și ușor de consultat.
    </p>
    <p class="medical-disclaimer">
        <span aria-hidden="true">ℹ️</span>
        <span>Informațiile sunt orientative și nu înlocuiesc consultul sau îngrijirea medicală.</span>
    </p>
</section>
"""

ASSISTANT_HEADER_HTML = """
<div class="assistant-identity">
    <span class="assistant-avatar" aria-hidden="true">🩺</span>
    <span><strong>Dr. Cuișor</strong><small>Răspunsuri bazate pe surse locale</small></span>
</div>
"""

MESSAGE_HELPER_HTML = """
<div><span aria-hidden="true">📝</span> Specificați strict problema de sănătate și nimic altceva..</div>
"""


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
                end = gr.Button(
                    "🔒 Închide sesiunea",
                    variant="secondary",
                    size="sm",
                    scale=0,
                    elem_id="end-session",
                )
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
            download_box = gr.HTML(elem_id="report-download")
            gr.HTML(MESSAGE_HELPER_HTML, elem_id="message-helper")
            with gr.Row(elem_id="message-row"):
                message = gr.Textbox(
                    label="Descrierea problemei de sănătate",
                    show_label=False,
                    placeholder="Pentru ce problemă de sănătate doriți recomandări de tratamente naturiste...",
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
        on_message, inputs=[message], outputs=[message, chatbot, download_box], queue=False
    )
    submit_event = message.submit(
        on_message, inputs=[message], outputs=[message, chatbot, download_box], queue=False
    )
    end_event = end.click(on_end, outputs=[chatbot, download_box], queue=False)
    load_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    end_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    for event in (send_event, submit_event):
        notice_event = event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
        processing_event = notice_event.then(
            _processing_button_update,
            outputs=[send],
            queue=False,
        )
        report_event = processing_event.then(
            on_auto_report,
            outputs=[chatbot, download_box],
            queue=False,
        )
        report_event.then(_ready_button_update, outputs=[send], queue=False).then(
            fn=None, js=AUTO_SCROLL_JS, queue=False
        )
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
        str((settings.index_dir.parent / ".env").resolve()),
    ],
    show_error=False,
    footer_links=[],
    theme=theme,
    css=APP_CSS,
    js=COMPOSER_STATE_JS,
)
