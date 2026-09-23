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
from fastapi.responses import Response

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
from web_app.reports import bibliography_label, build_reference_index, create_pdf, report_title
from web_app.retrieval import Retriever
from web_app.sessions import SessionData, SessionStore

logger = logging.getLogger("naturist")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
WELCOME = "Bună ziua!"
REPORT_STARTED = "Acum a început generarea recomandărilor naturiste. Vă rog să așteptați."
store = SessionStore(settings.temp_dir, settings.session_idle_seconds, settings.session_max_seconds)
retriever = Retriever(settings.index_dir, settings.documents_dir)
ai = XAIClient(settings)
app = FastAPI(title="Chatbot naturist", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=[], allow_headers=[])

rate_lock = __import__("threading").Lock()
rate_events: dict[str, deque[float]] = defaultdict(deque)


def _cookie_from_header(header: str) -> str | None:
    try:
        cookies = SimpleCookie()
        cookies.load(header)
        value = cookies[COOKIE].value if COOKIE in cookies else None
        return value if value and COOKIE_RE.fullmatch(value) else None
    except Exception:
        return None


def _identity(request: gr.Request) -> tuple[str, str]:
    if request is None or not request.session_hash:
        raise gr.Error("Sesiunea nu este disponibilă. Reîncărcați pagina.")
    cookie = _cookie_from_header(str(dict(request.headers).get("cookie", "")))
    if not cookie:
        raise gr.Error("Sesiunea a expirat. Reîncărcați pagina.")
    return cookie, str(request.session_hash)


def _current(request: gr.Request, create: bool = False) -> SessionData:
    cookie, tab = _identity(request)
    session = store.get(cookie, tab, create=create)
    if session is None:
        raise gr.Error("Sesiunea a expirat. Reîncărcați pagina.")
    return session


def _report_filename(session: SessionData) -> str:
    title = report_title(session.profile.as_dict())
    safe = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "-", title)
    safe = re.sub(r"\s+", " ", safe).strip(" .")
    return f"{safe or 'Recomandări naturiste'}.pdf"


def _download_html(session: SessionData) -> str:
    if not session.report_id:
        return ""
    prefix = os.getenv("GRADIO_ROOT_PATH", "").rstrip("/")
    url = f"{prefix}/api/reports/{quote(session.tab_id, safe='')}/{quote(session.report_id, safe='')}"
    filename = _report_filename(session)
    return (
        f'<a href="{html.escape(url, quote=True)}" download="{html.escape(filename, quote=True)}" '
        'class="pdf-download">Descarcă PDF</a>'
    )


def _append(session: SessionData, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    if len(session.history) > 60:
        session.history = session.history[-60:]


def _ask(session: SessionData, question: str) -> None:
    _append(session, "assistant", question)
    session.profile.add_transcript("assistant", question)


def _recommendation_text(sections: dict, evidence: dict) -> str:
    labels = (
        ("uz_intern", "Uz intern"),
        ("nutritie", "Nutriție"),
        ("uz_extern", "Uz extern"),
        ("alte_recomandari", "Alte Recomandări"),
        ("atentionari", "Atenționări"),
    )
    reference_numbers, references = build_reference_index(sections, evidence)
    lines = ["Raportul este gata. Recomandările susținute de surse:"]
    found = False
    for key, label in labels:
        items = sections.get(key) or []
        if not items:
            continue
        found = True
        lines.append(f"\n{label}:")
        for item in items:
            citations = [evidence[token]["source"] for token in item.get("evidence_ids", []) if token in evidence]
            unique_numbers = list(dict.fromkeys(reference_numbers[source] for source in citations))
            markers = "".join(f"[{number}]" for number in unique_numbers)
            lines.append(f"• {item['text']} {markers}".rstrip())
    if not found:
        lines.append("Nu au fost identificate recomandări specifice suficient susținute de fragmentele disponibile.")
    if references:
        lines.append("\nBibliografie:")
        lines.extend(
            f"{number} - {bibliography_label(source)}"
            for number, source in enumerate(references, start=1)
        )
    lines.append("\nFolosiți butonul Descarcă PDF pentru raportul complet.")
    return "\n".join(lines)[:14000]


@app.middleware("http")
async def session_and_limits(request: Request, call_next):
    path = request.url.path
    if request.method in {"POST", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
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
async def startup() -> None:
    async def cleanup() -> None:
        while True:
            await asyncio.sleep(60)
            store.sweep()
    app.state.cleanup_task = asyncio.create_task(cleanup())


@app.on_event("shutdown")
async def shutdown() -> None:
    app.state.cleanup_task.cancel()
    ai.close()


@app.get("/healthz")
def healthz():
    try:
        configured = bool(settings.api_key())
    except (OSError, UnicodeError):
        configured = False
    if not configured:
        raise HTTPException(status_code=503, detail="Secretul xAI lipsește sau nu este un fișier valid.")
    return {"status": "ok", "index": "ready"}


@app.get("/api/reports/{tab_id}/{report_id}")
def download(tab_id: str, report_id: str, request: Request):
    sid = request.cookies.get(COOKIE)
    session = store.get(sid or "", tab_id, create=False)
    if session is None or session.report_id != report_id or session.report_bytes is None:
        raise HTTPException(status_code=404, detail="Raportul nu este disponibil pentru această sesiune.")
    filename = _report_filename(session)
    return Response(
        session.report_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Cache-Control": "no-store",
        },
    )


def on_load(request: gr.Request):
    session = _current(request, create=True)
    with session.lock:
        if not session.history:
            _append(session, "assistant", WELCOME)
            question = session.profile.next_question()
            if question:
                _ask(session, question)
        return list(session.history), _download_html(session)


def on_message(message: str, request: gr.Request):
    session = _current(request)
    message = (message or "").strip()
    if not message:
        return "", list(session.history), _download_html(session)
    if len(message) > settings.max_chat_chars:
        raise gr.Error(f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        _append(session, "user", message)
        session.profile.add_transcript("user", message)
        session.clear_report()
        if not session.profile.health_problem:
            session.profile.set_health_problem(message)
        else:
            session.profile.add_health_context(message)
        session.auto_report_pending = True
        _append(session, "assistant", REPORT_STARTED)
        return "", list(session.history), _download_html(session)


def on_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not session.profile.report_ready:
            _append(session, "assistant", "Descrieți problema de sănătate înainte de generarea raportului.")
            return list(session.history), _download_html(session)
        try:
            evidence = retriever.collect(session)
            if not evidence:
                _append(session, "assistant", "Nu am găsit fragmente relevante în sursele locale.")
                return list(session.history), _download_html(session)
            sections = ai.generate(session.profile.as_dict(), evidence)
            report = create_pdf(session.profile.as_dict(), sections, evidence)
            session.report_bytes = report
            session.report_id = secrets.token_urlsafe(18)
            _append(session, "assistant", _recommendation_text(sections, evidence))
        except AIUnavailable as exc:
            _append(session, "assistant", str(exc))
        except Exception as exc:
            logger.error("report failed: %s", type(exc).__name__)
            _append(session, "assistant", "Raportul nu a putut fi generat. Încercați din nou.")
        return list(session.history), _download_html(session)


def on_auto_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not session.auto_report_pending:
            return list(session.history), _download_html(session)
        session.auto_report_pending = False
        return on_report(request)


def on_end(request: gr.Request):
    cookie, tab = _identity(request)
    store.delete(cookie, tab)
    return [
        {"role": "assistant", "content": "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă."}
    ], ""


def on_unload(request: gr.Request) -> None:
    try:
        cookie, tab = _identity(request)
        store.delete(cookie, tab)
    except Exception:
        pass


theme = gr.themes.Soft(
    font=[gr.themes.GoogleFont("Inter"), "Arial", "sans-serif"]
)

AUTO_SCROLL_JS = """
() => {
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

APP_CSS = """
.pdf-download {
    display: inline-block;
    background: #176c73;
    color: white !important;
    padding: 12px 18px;
    border-radius: 8px;
    font-weight: 700;
    text-decoration: none;
}

#medical-chatbot,
#medical-chatbot > div,
#medical-chatbot .wrap,
#medical-chatbot .bubble-wrap {
    height: auto !important;
    max-height: none !important;
    min-height: 0 !important;
    overflow: visible !important;
}

#message-row {
    align-items: end;
    gap: 10px;
}

#send-message {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 88px !important;
    max-width: 110px !important;
    align-self: end;
    margin-bottom: 1px;
}

#session-actions {
    justify-content: flex-end;
    margin-top: 10px;
}

#end-session {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 130px !important;
    max-width: 170px !important;
}

@media (max-width: 640px) {
    #message-row { flex-wrap: nowrap; }
    #send-message { min-width: 76px !important; }
}
"""


with gr.Blocks(title="Recomandări naturiste", analytics_enabled=False, delete_cache=(60, 60)) as demo:
    gr.Markdown("# Recomandări naturiste")
    gr.Markdown(
        "Discutați liber și primiți un raport informativ, bazat pe sursele locale. "
        "Nu înlocuiește îngrijirea medicală."
    )
    chatbot = gr.Chatbot(
        height=None,
        max_height=None,
        autoscroll=True,
        elem_id="medical-chatbot",
        render_markdown=False,
        sanitize_html=True,
        allow_file_downloads=False,
    )
    with gr.Row(elem_id="message-row"):
        message = gr.Textbox(
            label="Mesaj",
            placeholder="Descrieți problema de sănătate...",
            lines=2,
            max_lines=5,
            scale=1,
        )
        send = gr.Button("Trimite", variant="primary", size="sm", scale=0, elem_id="send-message")
    download_box = gr.HTML()
    with gr.Row(elem_id="session-actions"):
        end = gr.Button("Închide sesiunea", size="sm", scale=0, elem_id="end-session")
    load_event = demo.load(on_load, outputs=[chatbot, download_box], queue=False)
    send_event = send.click(
        on_message, inputs=[message], outputs=[message, chatbot, download_box], queue=False
    )
    submit_event = message.submit(
        on_message, inputs=[message], outputs=[message, chatbot, download_box], queue=False
    )
    end_event = end.click(on_end, outputs=[chatbot, download_box], queue=False)
    for event in (load_event, end_event):
        event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
    for event in (send_event, submit_event):
        notice_event = event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
        report_event = notice_event.then(
            on_auto_report,
            outputs=[chatbot, download_box],
            queue=False,
        )
        report_event.then(fn=None, js=AUTO_SCROLL_JS, queue=False)
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
)
