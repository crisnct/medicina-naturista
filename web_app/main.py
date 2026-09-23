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
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from web_app.config import settings

CACHE_ROOT = Path(os.getenv("GRADIO_TEMP_DIR", "/tmp/gradio-cache" if os.name != "nt" else str(settings.temp_dir.parent / ".gradio_tmp"))).resolve()
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["GRADIO_TEMP_DIR"] = str(CACHE_ROOT)
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

import gradio as gr  # noqa: E402

from web_app.ai import AIUnavailable, XAIClient
from web_app.documents import DocumentError, ingest
from web_app.reports import create_pdf
from web_app.retrieval import Retriever
from web_app.sessions import SessionData, SessionStore

logger = logging.getLogger("naturist")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
WELCOME = "Bună ziua! Descrieți liber ce probleme sau simptome doriți să luăm în considerare. Puteți încărca și documente."
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


def _profile_text(session: SessionData) -> str:
    profile = session.profile
    known = [
        f"Vârstă: {profile.age if profile.age is not None else '—'}",
        f"Sex: {profile.sex or '—'}",
        f"Greutate: {profile.weight_kg if profile.weight_kg is not None else '—'} kg",
        f"Înălțime: {profile.height_cm if profile.height_cm is not None else '—'} cm",
        f"Probleme: {', '.join(profile.health_conditions) or '—'}",
        f"Simptome: {', '.join(profile.symptoms) or '—'}",
    ]
    return " | ".join(known)


def _files_text(session: SessionData) -> str:
    return "Fișiere în sesiune: " + (", ".join(item.name for item in session.documents) or "niciunul")


def _download_html(session: SessionData) -> str:
    if not session.report_id:
        return ""
    url = f"/api/reports/{quote(session.tab_id, safe='')}/{quote(session.report_id, safe='')}"
    return f'<a href="{html.escape(url, quote=True)}" download="recomandari-naturiste.pdf" class="pdf-download">Descarcă PDF</a>'


def _append(session: SessionData, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    if len(session.history) > 60:
        session.history = session.history[-60:]


def _recommendation_text(sections: dict, evidence: dict) -> str:
    labels = (
        ("uz_intern", "Uz intern"),
        ("nutritie", "Nutriție"),
        ("uz_extern", "Uz extern"),
        ("alte_recomandari", "Alte Recomandări"),
        ("atentionari", "Atenționări"),
    )
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
            lines.append(f"• {item['text']} ({'; '.join(citations)})")
    if not found:
        lines.append("Nu au fost identificate recomandări specifice suficient susținute de fragmentele disponibile.")
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
    return Response(
        session.report_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="recomandari-naturiste.pdf"',
            "Cache-Control": "no-store",
        },
    )


def on_load(request: gr.Request):
    session = _current(request, create=True)
    with session.lock:
        if not session.history:
            _append(session, "assistant", WELCOME)
        return list(session.history), _profile_text(session), _files_text(session), _download_html(session)


def on_message(message: str, request: gr.Request):
    session = _current(request)
    message = (message or "").strip()
    if not message:
        return "", list(session.history), _profile_text(session), _download_html(session)
    if len(message) > settings.max_chat_chars:
        raise gr.Error(f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        _append(session, "user", message)
        session.clear_report()
        try:
            unknown_answer = session.profile.mark_unknown_answer(message)
            if not unknown_answer:
                update = ai.extract_profile(message, session.profile.asked_field)
                session.profile.merge(update)
            question = session.profile.next_question()
            if question:
                _append(session, "assistant", question)
            else:
                _append(session, "assistant", "Am notat informațiile oferite. Puteți adăuga detalii sau genera raportul PDF.")
        except AIUnavailable as exc:
            _append(session, "assistant", str(exc))
        except Exception as exc:
            logger.error("chat failed: %s", type(exc).__name__)
            _append(session, "assistant", "Nu am putut procesa mesajul. Încercați din nou.")
        return "", list(session.history), _profile_text(session), _download_html(session)


def on_upload(paths: list[str] | str | None, request: gr.Request):
    session = _current(request)
    values = [paths] if isinstance(paths, str) else (paths or [])
    outcomes: list[str] = []
    with session.lock:
        for value in values:
            try:
                document = ingest(Path(value), session, settings, CACHE_ROOT, retriever.embed_passages)
                session.documents.append(document)
                session.clear_report()
                try:
                    excerpt = "\n".join(item["text"] for item in document.chunks)[:8500]
                    facts = ai.extract_document_facts(document.name, excerpt)
                    session.profile.merge(facts)
                    document.summary = str(facts.get("summary") or "")[:400]
                except AIUnavailable:
                    outcomes.append(f"{document.name}: text extras local; sumarul AI nu este momentan disponibil.")
                else:
                    outcomes.append(f"{document.name}: procesat.")
            except DocumentError as exc:
                outcomes.append(f"{Path(value).name}: {exc}")
            except Exception as exc:
                logger.error("upload failed: %s", type(exc).__name__)
                outcomes.append(f"{Path(value).name}: fișierul nu a putut fi procesat.")
        if outcomes:
            _append(session, "assistant", "\n".join(outcomes))
        return list(session.history), _files_text(session), _profile_text(session)


def on_report(request: gr.Request):
    session = _current(request)
    with session.lock:
        if not (session.profile.health_conditions or session.profile.symptoms):
            _append(session, "assistant", "Am nevoie de cel puțin o problemă sau un simptom descris înainte de raport.")
            return list(session.history), _download_html(session)
        try:
            evidence = retriever.collect(session)
            if not evidence:
                _append(session, "assistant", "Nu am găsit fragmente relevante în sursele permise. Puteți adăuga detalii sau documente.")
                return list(session.history), _download_html(session)
            sections = ai.generate(session.profile.as_dict(), evidence)
            sections = ai.verify(sections, evidence)
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


def on_end(request: gr.Request):
    cookie, tab = _identity(request)
    store.delete(cookie, tab)
    return [{"role": "assistant", "content": "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă."}], "", "", ""


def on_unload(request: gr.Request) -> None:
    try:
        cookie, tab = _identity(request)
        store.delete(cookie, tab)
    except Exception:
        pass


with gr.Blocks(
    title="Recomandări naturiste",
    analytics_enabled=False,
    delete_cache=(60, 60),
) as demo:
    gr.Markdown("# Recomandări naturiste")
    gr.Markdown("Discutați liber și primiți un raport informativ, bazat pe sursele locale. Nu înlocuiește îngrijirea medicală.")
    chatbot = gr.Chatbot(height=470, render_markdown=False, sanitize_html=True, allow_file_downloads=False)
    profile_box = gr.Textbox(label="Profil colectat", interactive=False)
    files_box = gr.Textbox(label="Fișiere încărcate", interactive=False)
    message = gr.Textbox(label="Mesaj", placeholder="Descrieți ce vă preocupă...", lines=2, max_lines=5)
    with gr.Row():
        send = gr.Button("Trimite", variant="primary")
        upload = gr.UploadButton("Atașează fișiere", file_types=list({".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg"}), file_count="multiple", type="filepath")
        generate = gr.Button("Generează raportul")
    download_box = gr.HTML()
    end = gr.Button("Închide sesiunea")
    demo.load(on_load, outputs=[chatbot, profile_box, files_box, download_box], queue=False)
    send.click(on_message, inputs=[message], outputs=[message, chatbot, profile_box, download_box], queue=False)
    message.submit(on_message, inputs=[message], outputs=[message, chatbot, profile_box, download_box], queue=False)
    upload.upload(on_upload, inputs=[upload], outputs=[chatbot, files_box, profile_box], queue=False)
    generate.click(on_report, outputs=[chatbot, download_box], queue=False)
    end.click(on_end, outputs=[chatbot, profile_box, files_box, download_box], queue=False)
    demo.unload(on_unload)

app = gr.mount_gradio_app(
    app, demo, path="/",
    blocked_paths=[
        str(CACHE_ROOT), str(settings.temp_dir.resolve()), str(settings.documents_dir.resolve()),
        str(settings.index_dir.resolve()), str((settings.index_dir.parent / "model_cache").resolve()),
        str((settings.index_dir.parent / ".env").resolve()),
    ],
    max_file_size=settings.max_upload_bytes,
    show_error=False,
    footer_links=[],
    theme=gr.themes.Soft(font=("Arial", "Helvetica", "sans-serif")),
    css=".pdf-download { display:inline-block; background:#176c73; color:white !important; padding:12px 18px; border-radius:8px; font-weight:700; text-decoration:none; }",
)
