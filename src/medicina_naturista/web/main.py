"""JSON API for the React chat UI, served by FastAPI (which also serves the
built frontend as static files — see the bottom of this module)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from medicina_naturista.config import settings

from medicina_naturista.ai.client import AIUnavailable, XAIClient
from medicina_naturista.integrations.gmail import EMAIL_SKIPPED, send_report
from medicina_naturista.reporting.pdf import create_pdf
from medicina_naturista.ai.conditions import resolve_query
from medicina_naturista.ai.retrieval import Retriever
from medicina_naturista.ai.search import warm_up as warm_up_search
from medicina_naturista.core.models import PendingSearch, SessionData, StoredReport
from medicina_naturista.core.sessions import SessionStore
from medicina_naturista.web.handlers import (
    _append,
    _ask,
    _download_message,
    _fragments_message,
    _generate_message,
    _recommendation_text,
    _replace_generate_message,
    _report_filename,
    _text,
)

logger = logging.getLogger("naturist.web")
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
# Client-generated per-tab identifier (crypto.randomUUID(), kept in the
# browser's sessionStorage) sent on every request as the X-Tab-Id header —
# the replacement for Gradio's own per-connection request.session_hash.
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_COOKIE = "naturist_owner"
OWNER_COOKIE_MAX_AGE = 10 * 365 * 24 * 3600
OWNER_ONLY_MESSAGE = "Generarea rețetei nu este disponibilă momentan pentru acest cont."
WELCOME = "Bună ziua! 👋"
store = SessionStore(settings.temp_dir, settings.session_idle_seconds, settings.session_max_seconds)
retriever = Retriever(settings.documents_dir)
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


# Build the "Caut rapid în cele N documente" notice for the categories
# currently selected on the session.
def _report_started_message(session: SessionData) -> dict:
    count = _document_count_for_categories(session.selected_categories)
    return _text("assistant", f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați.")


# Chat notice naming the condition(s) the health problem was recognised as in
# the condition dictionary, with every synonym the search will use (the same
# resolution rank() runs, so every comma-separated expression counts). None when
# nothing was recognised.
def _condition_identified_message(health_problem: str) -> dict | None:
    conditions = resolve_query(health_problem).conditions
    if not conditions:
        return None
    lines = []
    for condition in conditions:
        line = f"✅ Am identificat afecțiunea: **{condition.name}**."
        if len(condition.terms) > 1:
            line += f" O caut și după denumirile: {', '.join(condition.terms[1:])}."
        lines.append(line)
    return _text("assistant", "\n".join(lines))


# Serialize one category node (and, recursively, its children) into the plain
# JSON shape the frontend's category tree component consumes.
def _category_node_payload(tree, node_id: str) -> dict:
    node = tree.nodes[node_id]
    return {
        "id": node.id,
        "label": node.label,
        "ownDocuments": node.own_documents,
        "totalDocuments": node.total_documents,
        "isReal": node.own_documents > 0,
        "children": [_category_node_payload(tree, child_id) for child_id in node.children],
    }


ai = XAIClient(settings)


@asynccontextmanager
# Start periodic session cleanup on startup and close background resources on shutdown.
async def lifespan(app: FastAPI):
    logger.info(
        "application_started documents=%s log_fragment_text=%s",
        settings.documents_dir,
        settings.log_fragment_text,
    )

    # Periodically remove expired sessions from the in-memory store.
    async def cleanup() -> None:
        while True:
            await asyncio.sleep(60)
            store.sweep()

    cleanup_task = asyncio.create_task(cleanup())
    # Load the embedding model and warm the index now, not on the first patient's search.
    try:
        await asyncio.to_thread(warm_up_search)
    except Exception:
        logger.warning("search_warm_up_failed", exc_info=True)
    try:
        yield
    finally:
        logger.info("application_shutdown active_sessions=%s", store.count())
        cleanup_task.cancel()
        ai.close()


app = FastAPI(title="Chatbot naturist", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=[], allow_headers=[])

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


# Resolve the authenticated browser tab to its cookie and client-generated tab identifiers.
def _identity(request: Request) -> tuple[str, str]:
    cookie = _cookie_from_header(request.headers.get("cookie", ""))
    if not cookie:
        raise HTTPException(status_code=401, detail="Sesiunea a expirat. Reîncărcați pagina.")
    tab = request.headers.get("x-tab-id", "")
    if not TAB_ID_RE.fullmatch(tab):
        raise HTTPException(status_code=400, detail="Identificator de tab lipsă sau invalid.")
    return cookie, tab


# Return the current tab session or raise a user-facing expiration error.
def _current(request: Request, create: bool = False) -> SessionData:
    cookie, tab = _identity(request)
    session = store.get(cookie, tab, create=create)
    if session is None:
        raise HTTPException(status_code=409, detail="Sesiunea a expirat. Reîncărcați pagina.")
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
        if path.startswith("/api/"):
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


@app.get("/api/session")
# Initialize a browser session and return its current chat history.
def get_session(request: Request):
    session = _current(request, create=True)
    with session.lock:
        if not session.history:
            question = session.profile.next_question()
            if question:
                # Greeting and first question are one chat bubble; the transcript keeps the bare question.
                _append(session, _text("assistant", f"{WELCOME}\n\n{question}"))
                session.profile.add_transcript("assistant", question)
            else:
                _append(session, _text("assistant", WELCOME))
        logger.info("session_loaded tab_id=%s history_entries=%s", session.tab_id, len(session.history))
        return {"history": list(session.history)}


@app.get("/api/categories")
# Return the category tree (or null when the index has no categories yet)
# and the default selection — every known category id, matching "search
# everywhere" — so the frontend's filter panel starts fully checked.
def get_categories():
    tree = retriever.category_tree
    if tree is None:
        return {"tree": None, "defaultSelection": []}
    return {
        "tree": _category_node_payload(tree, tree.root_id),
        "defaultSelection": sorted(tree.known_ids()),
    }


class MessageRequest(BaseModel):
    message: str = ""
    categories: list[str] = Field(default_factory=list)


# Email the finished report to the address typed in chat and return the chat reply.
def _send_report_email(session: SessionData, address: str) -> dict:
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
        return _text("assistant", "Nu am putut trimite documentul pe mail. Încercați din nou.")
    logger.info("report_stage_completed stage=email tab_id=%s result=%s", session.tab_id, status)
    if status == EMAIL_SKIPPED:
        return _text("assistant", "Trimiterea pe mail nu este configurată momentan.")
    return _text("assistant", f"✅ Am trimis documentul la {address}.")


@app.post("/api/messages")
# Store a user message and return immediately (echo + a short status notice,
# or a rejection) — kept as its own fast round trip, separate from
# POST /api/search's slower retrieval, so the frontend can render the user's
# own message and the "Caut rapid..." notice right away instead of holding
# them back for however long the search underneath takes.
def post_message(payload: MessageRequest, request: Request):
    session = _current(request)
    message = (payload.message or "").strip()
    if not message:
        return {"messages": [], "startSearch": False}
    if len(message) > settings.max_chat_chars:
        raise HTTPException(status_code=422, detail=f"Mesajul depășește limita de {settings.max_chat_chars} caractere.")
    with session.lock:
        before = len(session.history)
        if session.report_bytes is not None and EMAIL_PATTERN.fullmatch(message):
            _append(session, _text("user", message))
            _append(session, _send_report_email(session, message))
            return {"messages": list(session.history[before:]), "startSearch": False}

        previous_health_problem = session.profile.health_problem
        _append(session, _text("user", message))
        session.profile.replace_health_problem(message)
        session.selected_categories = set(payload.categories)
        logger.info(
            "user_message_accepted tab_id=%s chars=%s replaced_health_problem=%s health_context_entries=%s "
            "selected_categories=%s",
            session.tab_id,
            len(message),
            bool(previous_health_problem),
            len(session.profile.health_context),
            len(session.selected_categories),
        )

        if not session.profile.report_ready:
            _append(session, _text("assistant", "Descrieți problema de sănătate înainte de căutare."))
            return {"messages": list(session.history[before:]), "startSearch": False}
        if getattr(retriever, "category_tree", None) is not None and not session.selected_categories:
            logger.info("fragments_skipped tab_id=%s reason=no_category_selected", session.tab_id)
            _append(session, _text("assistant", NO_CATEGORY_SELECTED_MESSAGE))
            return {"messages": list(session.history[before:]), "startSearch": False}

        identified = _condition_identified_message(session.profile.health_problem)
        if identified is not None:
            _append(session, identified)
        _append(session, _report_started_message(session))
        return {"messages": list(session.history[before:]), "startSearch": True}


@app.post("/api/search")
# Run retrieval for the health problem/categories POST /api/messages already
# stored on the session, and append the resulting fragments+generate section
# (or a "nothing found" notice). Split out from post_message so the frontend
# can show the fast echo/notice before this slower call even starts.
def post_search(request: Request):
    session = _current(request)
    with session.lock:
        before = len(session.history)
        logger.info("report_stage_started stage=retrieval tab_id=%s", session.tab_id)
        evidence = retriever.collect(session)
        logger.info(
            "report_stage_completed stage=retrieval tab_id=%s evidence_entries=%s evidence_chars=%s",
            session.tab_id,
            len(evidence),
            sum(len(item["text"]) for item in evidence.values()),
        )
        if not evidence:
            _append(session, _text("assistant", "Nu am găsit fragmente relevante în sursele locale."))
            return {"messages": list(session.history[before:])}

        search_id = secrets.token_hex(6)
        session.add_search(search_id, PendingSearch(profile=session.profile.as_dict(), evidence=evidence))
        _append(session, _fragments_message(search_id, evidence))
        _append(session, _generate_message(search_id))
        return {"messages": list(session.history[before:])}


# Send the fragments the patient already reviewed to the AI, generate the PDF, and update the chat.
def _generate_report(session: SessionData, search_id: str) -> list[dict]:
    with session.lock:
        before = len(session.history)
        search = session.searches.get(search_id)
        if search is None:
            logger.info("report_skipped tab_id=%s reason=no_pending_evidence", session.tab_id)
            _append(session, _text("assistant", "Nu există fragmente pregătite. Descrieți din nou problema de sănătate."))
            return list(session.history[before:])
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
            recommendation = _text("assistant", _recommendation_text(sections, evidence))
            download = _download_message(session, report_id, profile)
            email_offer = _text("assistant", EMAIL_OFFER)
            _replace_generate_message(session, search_id, [recommendation, download, email_offer])
            session.searches.pop(search_id, None)
            return [recommendation, download, email_offer]
        except AIUnavailable as exc:
            logger.error("report_failed tab_id=%s stage=ai type=%s", session.tab_id, type(exc).__name__)
            _append(session, _text("assistant", str(exc)))
            return list(session.history[before:])
        except Exception as exc:
            logger.exception("report failed: type=%s message=%s", type(exc).__name__, str(exc) or "<empty>")
            _append(session, _text("assistant", "Raportul nu a putut fi generat. Încercați din nou."))
            return list(session.history[before:])


@app.post("/api/searches/{search_id}/generate")
# Reject non-owner visitors with a notice; otherwise generate the report for the clicked search.
def generate(search_id: str, request: Request):
    session = _current(request)
    if not _is_owner(request.headers.get("cookie", "")):
        logger.info("report_skipped tab_id=%s reason=not_owner", session.tab_id)
        return {"messages": [], "ownerNotice": OWNER_ONLY_MESSAGE}
    return {"messages": _generate_report(session, search_id), "ownerNotice": None}


@app.post("/api/session/end")
# Close the current session and return a final assistant message to the UI.
def end_session(request: Request):
    cookie, tab = _identity(request)
    logger.info("session_end_requested tab_id=%s", tab)
    store.delete(cookie, tab)
    return {"messages": [_text("assistant", "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă.")]}


@app.post("/api/session/unload", status_code=204)
# Remove the browser session when the page is unloaded (sent via
# navigator.sendBeacon from the frontend's pagehide handler).
def unload_session(request: Request):
    try:
        cookie, tab = _identity(request)
        logger.info("session_unload tab_id=%s", tab)
        store.delete(cookie, tab)
    except HTTPException:
        pass
    return Response(status_code=204)


if settings.frontend_dist_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(settings.frontend_dist_dir), html=True), name="frontend")
else:
    logger.warning(
        "frontend_dist_missing path=%s — run `npm run build` in frontend/ before serving in production",
        settings.frontend_dist_dir,
    )
