"""FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import logging
import re
import secrets
from contextlib import asynccontextmanager, suppress
from http.cookies import CookieError, SimpleCookie
from urllib.parse import quote, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from backend.ai.client import AIUnavailable, create_ai_client
from backend.ai.condition_ai import identify_conditions, resolved_for
from backend.ai.condition_ai import warm_up as warm_up_condition_ai
from backend.ai.conditions import ResolvedQuery, resolve_query
from backend.ai.retrieval import Retriever
from backend.ai.search import ALL_SIGNALS, SearchSignals
from backend.ai.search import warm_up as warm_up_search
from backend.config import Settings, configure_settings
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import (
    CommitChange,
    OperationResult,
    PendingSearch,
    SessionData,
    StoredReport,
)
from backend.core.owner_auth import OwnerAuth, PostgresOwnerSessionRepository
from backend.core.rate_limits import RateLimiter
from backend.core.sessions import SessionStore
from backend.integrations.gmail import EMAIL_SKIPPED, send_report
from backend.reporting.pdf import create_pdf
from backend.web.access_logs import OwnerAccessLogFilter
from backend.web.body_limit import ApiBodyLimitMiddleware
from backend.web.dependencies import Dependencies
from backend.web.handlers import (
    _download_message,
    _fragments_message,
    _generate_message,
    _recommendation_text,
    _report_filename,
    _text,
)

logger = logging.getLogger("naturist.web")
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_COOKIE = "naturist_owner"
CSRF_COOKIE = "naturist_owner_csrf"
OWNER_COOKIE_MAX_AGE = 31536000
OWNER_ONLY_MESSAGE = (
    "Generarea rețetei este disponibilă doar pentru autorul acestui chatbot."
)
NO_FRAGMENT_ABOVE_MIN_SCORE = (
    "Niciun fragment nu atinge scorul minim selectat. Alegeți un prag mai mic."
)
WELCOME = "Bună ziua! 👋"
NO_CATEGORY_SELECTED_MESSAGE = "Nicio sursă selectată. Bifați cel puțin o categorie în panoul „Căutare avansată” înainte de căutare."
CONDITION_AI_NOTICE = "🤖 Nu am găsit afecțiunea în dicționarul meu. Încerc să o identific cu ajutorul AI. Vă rog să așteptați."
CONDITION_NOT_IDENTIFIED_MESSAGE = "⚠️ Nu am putut identifica afecțiunea din mesaj."
CONDITION_NOT_IDENTIFIED_CONTINUES = (
    f"{CONDITION_NOT_IDENTIFIED_MESSAGE} Caut după textul mesajului."
)
CONDITION_NOT_IDENTIFIED_STOPS = f"{CONDITION_NOT_IDENTIFIED_MESSAGE} Scrieți denumirea afecțiunii (ex. gripă, hipertensiune)."
EMAIL_OFFER = "Dacă doriți să trimiteți documentul pe mail la cineva, spuneți-mi la ce adresă să îl trimit."
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
router = APIRouter()


# Documents the given category ids actually cover, for the "Caut rapid în
# cele N documente" notice — the whole corpus (retriever.document_count) when
# the index has no category tree (nothing to restrict by), otherwise the sum
# of each selected category's own_documents (never total_documents, which
# would double-count a folder together with its own subfolders if both ended
# up selected). An id outside the known set (stale, or no tree at all) is
# simply not counted, same as everywhere else category ids are consumed.
def _document_count_for_categories(category_ids: set[str], retriever) -> int:
    tree = getattr(retriever, "category_tree", None)
    if tree is None:
        return getattr(retriever, "document_count", 0)
    known = tree.known_ids()
    return sum(
        tree.nodes[category_id].own_documents
        for category_id in category_ids
        if category_id in known
    )


# Whether the message goes to the condition AI: the conditions signal is on, a
# backend is configured and the dictionary names no condition in any segment.
def _needs_condition_ai(
    health_problem: str, signals: SearchSignals, settings: Settings
) -> bool:
    return bool(
        signals.conditions
        and settings.condition_ai_backends
        and not resolve_query(health_problem).conditions
    )


# Build the "Caut rapid în cele N documente" notice for the categories
# currently selected on the session.
def _report_started_message(session, retriever) -> dict:
    count = _document_count_for_categories(session.selected_categories, retriever)
    return _text(
        "assistant",
        f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați.",
    )


# Chat notice naming the condition(s) the health problem was recognised as in
# the condition dictionary (the same resolution rank() runs, so every
# comma-separated expression counts). With the conditions signal on, every
# recognised condition is named; the part "O caut și după denumirile: …" lists
# its synonyms and is there only with the lexical signal on, and only for a
# condition that is a whole expression of the message (an exact term or a
# near-identical spelling of one) — the only case in which the lexical search
# uses the synonyms (see ai/search.py's lexical_queries()). With the lexical
# signal alone, only those conditions are named; with neither, nothing is.
# None when nothing is to be named. `health_problem` is the typed text, or the
# message already resolved (dictionary plus AI conditions, see resolved_for());
# `by_ai` marks the conditions as identified by the AI rather than the dictionary.
def _condition_identified_message(
    health_problem: str | ResolvedQuery,
    signals: SearchSignals = ALL_SIGNALS,
    by_ai: bool = False,
) -> dict | None:
    resolved = (
        health_problem
        if isinstance(health_problem, ResolvedQuery)
        else resolve_query(health_problem)
    )
    whole = {
        condition.name
        for segment in resolved.segments
        if segment.whole_condition
        for condition in segment.conditions
    }
    if signals.conditions:
        conditions = resolved.conditions
    elif signals.lexical:
        conditions = tuple(
            condition for condition in resolved.conditions if condition.name in whole
        )
    else:
        return None
    if not conditions:
        return None
    lines = []
    for condition in conditions:
        label = (
            "Am identificat afecțiunea (cu ajutorul AI)"
            if by_ai
            else "Am identificat afecțiunea"
        )
        line = f"✅ {label}: **{condition.name}**."
        if signals.lexical and condition.name in whole and len(condition.terms) > 1:
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
        "children": [
            _category_node_payload(tree, child_id) for child_id in node.children
        ],
    }


class SignalsPayload(BaseModel):
    conditions: bool = True
    lexical: bool = True
    semantic: bool = True

    @model_validator(mode="after")
    def _at_least_one(self) -> "SignalsPayload":
        if not (self.conditions or self.lexical or self.semantic):
            raise ValueError("Bifați cel puțin un tip de căutare.")
        return self

    def to_signals(self) -> SearchSignals:
        return SearchSignals(
            conditions=self.conditions, lexical=self.lexical, semantic=self.semantic
        )


class MessageRequest(BaseModel):
    message: str = ""
    categories: list[str] = Field(default_factory=list)
    signals: SignalsPayload = Field(default_factory=SignalsPayload)


# The "Scor minim" chosen next to "Generează rețeta": only fragments whose
# relevance_percent is at least this value are sent to the AI (0 = all).
class GenerateRequest(BaseModel):
    minScore: float = Field(default=0, ge=0, le=100)


def _deps(request: Request) -> Dependencies:
    return request.app.state.dependencies


def _identity(request: Request) -> tuple[str, str]:
    cookie = request.cookies.get(COOKIE, "")
    if not COOKIE_RE.fullmatch(cookie):
        cookie = getattr(request.state, "session_cookie", "")
    if not COOKIE_RE.fullmatch(cookie):
        raise HTTPException(401, "Sesiunea a expirat. Reîncărcați pagina.")
    tab = request.headers.get("x-tab-id", "")
    if not TAB_ID_RE.fullmatch(tab):
        raise HTTPException(400, "Identificator de tab lipsă sau invalid.")
    return cookie, tab


def _current(request: Request, create: bool = False) -> SessionData:
    cookie, tab = _identity(request)
    deps = _deps(request)
    session = deps.store.get(cookie, tab, create=create, client_ip=_client_ip(request))
    if session is None:
        raise ApplicationError(
            "SESSION_EXPIRED", "Sesiunea a expirat. Reîncărcați pagina."
        )
    return session


def _client_ip(request: Request) -> str:
    # ASGI's peer is normalized by the server's explicit trusted proxy allowlist.
    # Never interpret a client-supplied X-Forwarded-For header here.
    return request.client.host if request.client else "unknown"


def _revision(request: Request) -> int | None:
    value = request.headers.get("x-context-revision")
    if value is None:
        return None
    try:
        revision = int(value)
        if revision < 0:
            raise ValueError
        return revision
    except ValueError:
        raise HTTPException(400, "Revizie invalidă.") from None


def _cancelled(**extra):
    return {**OperationResult(cancelled=True).as_dict(), **extra}


@router.get("/healthz")
def healthz(request: Request):
    ai = _deps(request).ai
    try:
        configured = ai.is_configured()
    except (OSError, UnicodeError):
        configured = False
    if not configured:
        raise HTTPException(
            503,
            f"Secretul {ai.provider.label} ({ai.provider.api_key_env}) lipsește sau nu este un fișier valid.",
        )
    return {"status": "ok", "index": "ready"}


@router.get("/api/reports/{tab_id}/{report_id}")
def download(tab_id: str, report_id: str, request: Request):
    store = _deps(request).store
    session = store.get(request.cookies.get(COOKIE, ""), tab_id)
    report = store.report(session, report_id) if session else None
    if report is None:
        raise HTTPException(404, "Raportul nu este disponibil pentru această sesiune.")
    return Response(
        report.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report.filename, safe='')}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/session")
def get_session(request: Request):
    deps = _deps(request)
    session = _current(request, create=True)
    if not deps.store.history(session):
        operation = deps.store.begin_operation(session, "initialize")
        try:
            profile = operation.snapshot.profile
            question = profile.next_question()
            if question:
                profile.add_transcript("assistant", question)
            deps.store.commit_operation(
                operation,
                CommitChange(
                    messages=[
                        _text(
                            "assistant",
                            f"{WELCOME}\n\n{question}" if question else WELCOME,
                        )
                    ],
                    profile=profile,
                ),
            )
        finally:
            deps.store.finish_operation(operation)
    return {"history": deps.store.history(session)}


@router.get("/api/categories")
def get_categories(request: Request):
    tree = _deps(request).retriever.category_tree
    if tree is None:
        return {"tree": None, "defaultSelection": []}
    return {
        "tree": _category_node_payload(tree, tree.root_id),
        "defaultSelection": sorted(tree.known_ids()),
    }


@router.post("/api/messages")
def post_message(payload: MessageRequest, request: Request):
    deps = _deps(request)
    session = _current(request)
    message = payload.message.strip()
    if not message:
        return {
            **OperationResult().as_dict(),
            "startSearch": False,
            "identifyCondition": False,
        }
    if len(message) > deps.settings.max_chat_chars:
        raise HTTPException(
            422,
            f"Mesajul depășește limita de {deps.settings.max_chat_chars} caractere.",
        )
    # The report is selected by the registry, never read across an external call.
    kind = "email" if EMAIL_PATTERN.fullmatch(message) else "message"
    operation = deps.store.begin_operation(session, kind)
    try:
        snapshot = operation.snapshot
        if kind == "email" and snapshot.report:
            deps.store.checkpoint(operation)
            report = snapshot.report
            try:
                status = (deps.email or send_report)(
                    report.health_problem, report.data, report.filename, message
                )
                reply = (
                    "Trimiterea pe mail nu este configurată momentan."
                    if status == EMAIL_SKIPPED
                    else f"✅ Am trimis documentul la {message}."
                )
            except Exception as exc:
                logger.error(
                    "report_stage_failed stage=email type=%s", type(exc).__name__
                )
                reply = "Nu am putut trimite documentul pe mail. Încercați din nou."
            result = deps.store.commit_operation(
                operation,
                CommitChange(
                    messages=[_text("user", message), _text("assistant", reply)]
                ),
            )
            return {
                **result.as_dict(),
                "startSearch": False,
                "identifyCondition": False,
            }
        if kind == "email":
            # An address without a report remains ordinary chat text.
            deps.store.finish_operation(operation)
            operation = deps.store.begin_operation(session, "message")
            snapshot = operation.snapshot
        profile = snapshot.profile
        profile.replace_health_problem(message)
        signals = payload.signals.to_signals()
        categories = set(payload.categories)
        messages = [_text("user", message)]
        start_search, identify = True, False
        if (
            getattr(deps.retriever, "category_tree", None) is not None
            and not categories
        ):
            messages.append(_text("assistant", NO_CATEGORY_SELECTED_MESSAGE))
            start_search = False
        elif _needs_condition_ai(profile.health_problem, signals, deps.settings):
            messages.append(_text("assistant", CONDITION_AI_NOTICE))
            identify = True
        else:
            identified = _condition_identified_message(profile.health_problem, signals)
            if identified:
                messages.append(identified)
            count = _document_count_for_categories(categories, deps.retriever)
            messages.append(
                _text(
                    "assistant",
                    f"🔍 Caut rapid în cele {count} documente interne disponibile. Vă rog să așteptați.",
                )
            )
        result = deps.store.commit_operation(
            operation, CommitChange(messages, profile, True, categories, signals)
        )
        if not result.cancelled:
            logger.info(
                "user_message_accepted chars=%s selected_categories=%s signals=%s",
                len(message),
                len(categories),
                signals.code,
            )
        return {
            **result.as_dict(),
            "startSearch": start_search and not result.cancelled,
            "identifyCondition": identify and not result.cancelled,
            "contextRevision": snapshot.context_revision + 1,
        }
    except OperationCancelled:
        return _cancelled(startSearch=False, identifyCondition=False)
    finally:
        deps.store.finish_operation(operation)


@router.post("/api/condition")
def post_condition(request: Request):
    deps = _deps(request)
    try:
        operation = deps.store.begin_operation(
            _current(request), "condition", expected_revision=_revision(request)
        )
    except OperationCancelled:
        return _cancelled(startSearch=False)
    try:
        snapshot = operation.snapshot
        if not _needs_condition_ai(
            snapshot.profile.health_problem, snapshot.search_signals, deps.settings
        ):
            deps.store.checkpoint(operation)
            return {**OperationResult().as_dict(), "startSearch": True}
        deps.store.checkpoint(operation)
        result = (deps.identify or identify_conditions)(
            resolve_query(snapshot.profile.health_problem)
        )
        deps.store.checkpoint(operation)
        profile = snapshot.profile
        profile.ai_conditions = copy.deepcopy(result.answers)
        messages, start_search = [], True
        if result.identified:
            identified = _condition_identified_message(
                resolved_for(profile), snapshot.search_signals, by_ai=True
            )
            if identified:
                messages.append(identified)
        elif not (snapshot.search_signals.lexical or snapshot.search_signals.semantic):
            messages.append(_text("assistant", CONDITION_NOT_IDENTIFIED_STOPS))
            start_search = False
        else:
            messages.append(_text("assistant", CONDITION_NOT_IDENTIFIED_CONTINUES))
        if start_search:
            messages.append(_report_started_message(snapshot, deps.retriever))
        committed = deps.store.commit_operation(
            operation, CommitChange(messages=messages, profile=profile)
        )
        return {
            **committed.as_dict(),
            "startSearch": start_search and not committed.cancelled,
        }
    except OperationCancelled:
        return _cancelled(startSearch=False)
    finally:
        deps.store.finish_operation(operation)


@router.post("/api/search")
def post_search(request: Request):
    deps = _deps(request)
    try:
        operation = deps.store.begin_operation(
            _current(request), "search", expected_revision=_revision(request)
        )
    except OperationCancelled:
        return _cancelled()
    try:
        snapshot = operation.snapshot
        signals = snapshot.search_signals
        if (
            signals.conditions
            and not (signals.lexical or signals.semantic)
            and not resolved_for(snapshot.profile).conditions
        ):
            return deps.store.commit_operation(
                operation,
                CommitChange(
                    messages=[_text("assistant", CONDITION_NOT_IDENTIFIED_STOPS)]
                ),
            ).as_dict()
        deps.store.checkpoint(operation)
        evidence = deps.retriever.collect(snapshot, deps.ai.context_budget())
        deps.store.checkpoint(operation)
        if not evidence:
            return deps.store.commit_operation(
                operation,
                CommitChange(
                    messages=[
                        _text(
                            "assistant",
                            "Nu am găsit fragmente relevante în sursele locale. Încercați o căutare semantică sau introduceți altă denumire a afecțiunii.",
                        )
                    ]
                ),
            ).as_dict()
        search_id = secrets.token_hex(6)
        return deps.store.commit_operation(
            operation,
            CommitChange(
                messages=[
                    _fragments_message(search_id, evidence, signals),
                    _generate_message(search_id),
                ],
                search=(
                    search_id,
                    PendingSearch(
                        profile=snapshot.profile.as_dict(),
                        evidence=evidence,
                        signals=signals,
                    ),
                ),
            ),
        ).as_dict()
    except OperationCancelled:
        return _cancelled()
    finally:
        deps.store.finish_operation(operation)


def _evidence_above(evidence: dict[str, dict], min_score: float) -> dict[str, dict]:
    return {
        eid: item
        for eid, item in evidence.items()
        if min_score <= 0 or (item.get("relevance_percent") or 0) >= min_score
    }


def _generate_report(
    deps: Dependencies, session: SessionData, search_id: str, min_score: float = 0
) -> OperationResult:
    operation = deps.store.begin_operation(session, "generate", search_id=search_id)
    try:
        snapshot = operation.snapshot
        search = snapshot.search
        assert search is not None
        profile, evidence = search.profile, _evidence_above(search.evidence, min_score)
        if not evidence:
            return deps.store.commit_operation(
                operation,
                CommitChange(
                    messages=[_text("assistant", NO_FRAGMENT_ABOVE_MIN_SCORE)]
                ),
            )
        deps.store.checkpoint(operation)
        sections = deps.ai.generate(profile, evidence)
        deps.store.checkpoint(operation)
        report = (deps.pdf or create_pdf)(profile, sections, evidence, min_score)
        deps.store.checkpoint(operation)
        report_id = secrets.token_urlsafe(18)
        filename = _report_filename(snapshot, profile)
        messages = [
            _text("assistant", _recommendation_text(sections, evidence)),
            _download_message(
                snapshot, report_id, profile, prefix=deps.settings.public_root_path
            ),
            _text("assistant", EMAIL_OFFER),
        ]
        return deps.store.commit_operation(
            operation,
            CommitChange(
                messages=messages,
                report=(
                    report_id,
                    StoredReport(report, filename, profile.get("health_problem", "")),
                ),
                replace_search_id=search_id,
            ),
        )
    except OperationCancelled:
        return OperationResult(cancelled=True)
    except ApplicationError:
        raise
    except Exception as exc:
        logger.error("report_stage_failed stage=generate type=%s", type(exc).__name__)
        reply = (
            "Furnizorul AI nu este disponibil. Încercați din nou."
            if isinstance(exc, AIUnavailable)
            else "Raportul nu a putut fi generat. Încercați din nou."
        )
        return deps.store.commit_operation(
            operation, CommitChange(messages=[_text("assistant", reply)])
        )
    finally:
        deps.store.finish_operation(operation)


@router.post("/api/searches/{search_id}/generate")
def generate(search_id: str, request: Request, payload: GenerateRequest | None = None):
    deps = _deps(request)
    session = _current(request)
    if not getattr(request.state, "owner_authorized", False):
        return {**OperationResult().as_dict(), "ownerNotice": OWNER_ONLY_MESSAGE}
    result = _generate_report(
        deps, session, search_id, payload.minScore if payload else 0
    )
    return {**result.as_dict(), "ownerNotice": None}


@router.post("/api/session/end")
def end_session(request: Request):
    cookie, tab = _identity(request)
    _deps(request).store.delete(cookie, tab)
    return {
        "messages": [
            _text(
                "assistant",
                "Sesiunea a fost închisă. Reîncărcați pagina pentru o conversație nouă.",
            )
        ]
    }


@router.post("/api/session/unload", status_code=204)
def unload_session(request: Request):
    try:
        cookie, tab = _identity(request)
        _deps(request).store.delete(cookie, tab)
    except HTTPException:
        pass
    return Response(status_code=204)


def _cookie(
    response: Response,
    name: str,
    value: str,
    settings: Settings,
    *,
    max_age: int | None = None,
):
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=settings.public_root_path or "/",
    )


def _origin_allowed(request: Request, *, required: bool = False) -> bool:
    origin = request.headers.get("origin")
    if not origin and required:
        source = request.headers.get("referer")
        if not source:
            return False
    elif not origin:
        return True
    else:
        source = origin
    # TLS may terminate at ngrok before an HTTP hop through Caddy. The public
    # origin is an operator setting, never inferred from client proxy headers.
    configured = _deps(request).settings.public_origin
    try:
        parsed = urlparse(source)
        expected = urlparse(configured or str(request.url))
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.scheme == expected.scheme
            and parsed.hostname == expected.hostname
            and (
                parsed.port
                if parsed.port is not None
                else (443 if parsed.scheme == "https" else 80)
            )
            == (
                expected.port
                if expected.port is not None
                else (443 if expected.scheme == "https" else 80)
            )
            and not parsed.username
            and not parsed.password
            and (not origin or not (parsed.path or parsed.query or parsed.fragment))
        )
    except ValueError:
        return False


def _csrf_token(deps: Dependencies) -> str:
    payload = secrets.token_urlsafe(32)
    return (
        payload
        + "."
        + hmac.new(
            deps.csrf_secret, payload.encode("ascii"), hashlib.sha256
        ).hexdigest()
    )


def _require_csrf(request: Request):
    supplied = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    match = re.fullmatch(r"([A-Za-z0-9_-]{43})\.([0-9a-f]{64})", supplied)
    if (
        not _origin_allowed(request, required=True)
        or not match
        or not hmac.compare_digest(supplied.encode(), cookie.encode())
    ):
        raise ApplicationError(
            "CSRF_FAILED", "Cerere de autorizare invalidă. Reîncărcați formularul.", 403
        )
    expected = hmac.new(
        _deps(request).csrf_secret, match[1].encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(match[2], expected):
        raise ApplicationError(
            "CSRF_FAILED", "Cerere de autorizare invalidă. Reîncărcați formularul.", 403
        )


@router.get("/api/owner")
def owner_status(request: Request):
    if request.headers.get("sec-fetch-site") == "cross-site" or not _origin_allowed(
        request
    ):
        raise ApplicationError("ORIGIN_FORBIDDEN", "Origine nepermisă.", 403)
    deps = _deps(request)
    token = _csrf_token(deps)
    response = JSONResponse(
        {
            "authorized": getattr(request.state, "owner_authorized", False),
            "csrfToken": token,
        }
    )
    _cookie(response, CSRF_COOKIE, token, deps.settings)
    return response


def _owner_tokens(request: Request) -> list[str]:
    # A legacy Path=/ cookie can coexist with the current scoped cookie. The
    # framework's cookie dict keeps only the last value, losing the valid token.
    tokens = []
    for header in request.headers.getlist("cookie"):
        for part in header.split(";"):
            cookie = SimpleCookie()
            try:
                cookie.load(part.strip())
            except CookieError:
                continue
            if OWNER_COOKIE in cookie:
                token = cookie[OWNER_COOKIE].value
                if token and token not in tokens:
                    tokens.append(token)
    return tokens


def _delete_legacy_owner_cookie(response: Response, settings: Settings):
    if settings.public_root_path:
        response.delete_cookie(
            OWNER_COOKIE,
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
        )


def _authorize_owner(request: Request, key: str) -> str:
    deps = _deps(request)
    token = deps.owner_auth.login(key)
    for previous in _owner_tokens(request):
        deps.owner_auth.logout(previous)
    return token


@router.get("/owner")
def owner_link(request: Request, key: str = ""):
    if request.headers.get("sec-fetch-site") == "cross-site" or not _origin_allowed(
        request
    ):
        raise ApplicationError("ORIGIN_FORBIDDEN", "Origine nepermisă.", 403)
    deps = _deps(request)
    if not key or len(key) > 4096:
        raise HTTPException(404)
    try:
        token = _authorize_owner(request, key)
    except ApplicationError as exc:
        if exc.code == "OWNER_LOGIN_FAILED":
            raise HTTPException(404) from None
        raise
    response = RedirectResponse(deps.settings.public_root_path + "/", status_code=303)
    _delete_legacy_owner_cookie(response, deps.settings)
    _cookie(response, OWNER_COOKIE, token, deps.settings, max_age=OWNER_COOKIE_MAX_AGE)
    return response


class OwnerLoginRequest(BaseModel):
    key: str = Field(min_length=1, max_length=4096, repr=False)


@router.post("/api/owner/login")
def owner_login(payload: OwnerLoginRequest, request: Request):
    deps = _deps(request)
    _require_csrf(request)
    token = _authorize_owner(request, payload.key)
    response = JSONResponse({"authorized": True})
    _delete_legacy_owner_cookie(response, deps.settings)
    _cookie(response, OWNER_COOKIE, token, deps.settings, max_age=OWNER_COOKIE_MAX_AGE)
    return response


@router.post("/api/owner/logout")
def owner_logout(request: Request):
    _require_csrf(request)
    deps = _deps(request)
    for token in _owner_tokens(request):
        deps.owner_auth.logout(token)
    request.state.owner_authorized = False
    response = JSONResponse({"authorized": False})
    _delete_legacy_owner_cookie(response, deps.settings)
    response.delete_cookie(
        OWNER_COOKIE,
        path=deps.settings.public_root_path or "/",
        httponly=True,
        secure=deps.settings.cookie_secure,
        samesite="strict",
    )
    return response


def create_app(
    config: Settings | None = None, dependencies: Dependencies | None = None
) -> FastAPI:
    """Side-effect-free factory; runtime resources belong to lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        owned = dependencies is None
        cleanup_task = None
        runtime = dependencies
        session_store = ai = auth = None
        try:
            if owned:
                cfg = config or Settings.from_env(dotenv=True)
                configure_settings(cfg)
                logging.basicConfig(
                    level=getattr(logging, cfg.log_level, logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s",
                )
                access_logger = logging.getLogger("uvicorn.access")
                if not any(
                    isinstance(f, OwnerAccessLogFilter) for f in access_logger.filters
                ):
                    access_logger.addFilter(OwnerAccessLogFilter())
                session_store = SessionStore(
                    cfg.temp_dir, cfg.session_idle_seconds, cfg.session_max_seconds, cfg
                )
                ai = create_ai_client(cfg)
                auth = OwnerAuth(
                    cfg.owner_key, PostgresOwnerSessionRepository(cfg.database_url)
                )
                retriever = await asyncio.to_thread(Retriever, cfg.documents_dir)
                runtime = Dependencies(
                    cfg,
                    session_store,
                    retriever,
                    ai,
                    auth,
                    RateLimiter(),
                    RateLimiter(),
                    secrets.token_bytes(32),
                )
                application.state.dependencies = runtime
                application.root_path = cfg.public_root_path
                application.mount(
                    "/",
                    StaticFiles(
                        directory=str(cfg.frontend_dist_dir), html=True, check_dir=False
                    ),
                    name="frontend",
                )
                for warm in (warm_up_search, warm_up_condition_ai):
                    try:
                        await asyncio.to_thread(warm)
                    except Exception as exc:
                        logger.warning("warm_up_failed type=%s", type(exc).__name__)
            assert runtime is not None

            async def cleanup():
                while True:
                    await asyncio.sleep(30)
                    await asyncio.to_thread(runtime.store.sweep)
                    runtime.request_limiter.sweep()
                    runtime.login_limiter.sweep()

            cleanup_task = asyncio.create_task(cleanup())
            yield
        finally:
            if cleanup_task:
                cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup_task
            if runtime:
                runtime.store.shutdown()
                await asyncio.to_thread(runtime.store.wait_workers)
            elif session_store:
                session_store.shutdown()
            if owned:
                if ai:
                    ai.close()
                if auth:
                    auth.repository.close()
                from backend.ai import condition_ai, db

                condition_ai.close_clients()
                db.close_pool()

    application = FastAPI(
        title="Chatbot naturist",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        root_path=config.public_root_path if config else "",
    )
    if dependencies:
        application.state.dependencies = dependencies

    @application.exception_handler(ApplicationError)
    async def controlled_error(request: Request, exc: ApplicationError):
        return JSONResponse(
            {"detail": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default validation response echoes input, including login keys.
        return JSONResponse(
            {
                "detail": {
                    "code": "INVALID_REQUEST",
                    "message": "Datele cererii sunt invalide.",
                }
            },
            status_code=422,
        )

    @application.middleware("http")
    async def session_and_limits(request: Request, call_next):
        deps = _deps(request)
        path = request.url.path.removeprefix(deps.settings.public_root_path)
        sid = request.cookies.get(COOKIE, "")
        fresh = not COOKIE_RE.fullmatch(sid)
        if fresh:
            sid = secrets.token_urlsafe(32)
        request.state.session_cookie = sid
        try:
            if (request.method == "POST" and path == "/api/owner/login") or (
                request.method == "GET" and path == "/owner"
            ):
                deps.login_limiter.check(
                    (_client_ip(request), deps.settings.owner_login_per_minute)
                )
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                if not _origin_allowed(request):
                    raise ApplicationError(
                        "ORIGIN_FORBIDDEN", "Origine nepermisă.", 403
                    )
                if path.startswith("/api/") and path != "/api/owner/login":
                    deps.request_limiter.check(
                        (_client_ip(request), deps.settings.max_requests_per_minute)
                    )
            request.state.owner_authorized = False
            token = ""
            if path not in {
                "/owner",
                "/api/owner/login",
                "/api/owner/logout",
            }:
                for candidate in _owner_tokens(request):
                    if await asyncio.to_thread(deps.owner_auth.authorized, candidate):
                        token = candidate
                        request.state.owner_authorized = True
                        break
            response = await call_next(request)
            if request.state.owner_authorized:
                _delete_legacy_owner_cookie(response, deps.settings)
                _cookie(
                    response,
                    OWNER_COOKIE,
                    token,
                    deps.settings,
                    max_age=OWNER_COOKIE_MAX_AGE,
                )
        except ApplicationError as exc:
            response = JSONResponse(
                {"detail": {"code": exc.code, "message": exc.message}}, exc.status
            )
        if fresh and path == "/api/session":
            _cookie(response, COOKIE, sid, deps.settings)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    application.add_middleware(
        ApiBodyLimitMiddleware,
        limit=lambda: application.state.dependencies.settings.max_api_body_bytes,
    )
    application.include_router(router)
    return application


app = create_app()
