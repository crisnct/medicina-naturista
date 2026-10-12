"""FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits."""

from __future__ import annotations

import asyncio
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from backend.ai.client import create_ai_client
from backend.ai.condition_ai import identify_conditions
from backend.ai.condition_ai import warm_up as warm_up_condition_ai
from backend.ai.herb_conditions import lookup_herb_conditions
from backend.ai.herbs import load_herbs
from backend.ai.index_state import IndexUnavailable, index_reader
from backend.ai.message_classification import MessageClassifier
from backend.ai.report_validation import ValidationWarning
from backend.ai.retrieval import Retriever
from backend.ai.search import SearchSignals
from backend.ai.search import warm_up as warm_up_search
from backend.config import Settings, configure_settings
from backend.core.conversation import (
    WELCOME,
    ConversationService,
)
from backend.core.errors import ApplicationError
from backend.core.models import (
    CommitChange,
    OperationResult,
    SessionData,
)
from backend.core.owner_auth import OwnerAuth, PostgresOwnerSessionRepository
from backend.core.rate_limits import RateLimiter
from backend.core.sessions import SessionStore
from backend.integrations.gmail import send_report
from backend.reporting.chat import (
    text as _text,
)
from backend.reporting.pdf import create_pdf
from backend.web.access_logs import OwnerAccessLogFilter
from backend.web.body_limit import ApiBodyLimitMiddleware
from backend.web.dependencies import Dependencies
from backend.web.owner_page import owner_page

logger = logging.getLogger("naturist.web")
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_COOKIE = "naturist_owner"
CSRF_COOKIE = "naturist_owner_csrf"
OWNER_COOKIE_MAX_AGE = 31536000
OWNER_ONLY_MESSAGE = "Generarea rețetei este disponibilă doar pentru autorul acestui chatbot."
router = APIRouter()


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
    messageId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


# The "Scor minim" chosen next to "Generează rețeta": only fragments whose
# relevance_percent is at least this value are sent to the AI (0 = all).
class GenerateRequest(BaseModel):
    minScore: float = Field(default=0, ge=0, le=100)


class GenerateResponse(BaseModel):
    messages: list[dict]
    ownerNotice: str | None
    partial: bool = False
    validationWarnings: list[ValidationWarning] = Field(default_factory=list)
    evictedSearchIds: list[str] = Field(default_factory=list)
    evictedReportIds: list[str] = Field(default_factory=list)
    evictedGroupIds: list[str] = Field(default_factory=list)
    cancelled: bool = False


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
        raise ApplicationError("SESSION_EXPIRED", "Sesiunea a expirat. Reîncărcați pagina.")
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
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request):
    healthz(request)
    if isinstance(_deps(request).retriever, Retriever):
        with index_reader():
            pass
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
    retriever = _deps(request).retriever
    if isinstance(retriever, Retriever):
        with index_reader() as (_connection, metadata):
            return _categories_payload(retriever.category_tree, metadata.index_generation)
    return _categories_payload(retriever.category_tree, None)


def _categories_payload(tree, generation):
    return {
        "tree": _category_node_payload(tree, tree.root_id) if tree else None,
        "defaultSelection": sorted(tree.known_ids()) if tree else [],
        "indexGeneration": generation,
    }


def _conversation(deps: Dependencies) -> ConversationService:
    return ConversationService(
        deps.settings,
        deps.store,
        deps.retriever,
        deps.ai,
        deps.identify or identify_conditions,
        deps.email or send_report,
        deps.pdf or create_pdf,
        deps.classify,
        deps.herb_lookup or lookup_herb_conditions,
    )


@router.post("/api/messages")
def post_message(payload: MessageRequest, request: Request):
    return _conversation(_deps(request)).message(
        _current(request),
        payload.message,
        set(payload.categories),
        payload.signals.to_signals(),
        payload.messageId,
    )


@router.post("/api/condition")
def post_condition(request: Request):
    return _conversation(_deps(request)).condition(_current(request), _revision(request))


@router.post("/api/classify")
def post_classify(request: Request):
    revision = _revision(request)
    if revision is None:
        raise ApplicationError(
            "REVISION_REQUIRED", "La clasificare este necesară revizia mesajului.", 422
        )
    return _conversation(_deps(request)).classify(_current(request), revision)


@router.post("/api/search")
def post_search(request: Request):
    deps = _deps(request)
    if isinstance(deps.retriever, Retriever):
        with index_reader():
            return _conversation(deps).search(_current(request), _revision(request))
    return _conversation(deps).search(_current(request), _revision(request))


def _generate_report(
    deps: Dependencies, session: SessionData, search_id: str, min_score: float = 0
) -> OperationResult:
    return _conversation(deps).generate(session, search_id, min_score)


@router.post(
    "/api/searches/{search_id}/generate",
    response_model=GenerateResponse,
    response_model_exclude_none=False,
)
def generate(search_id: str, request: Request, payload: GenerateRequest | None = None):
    deps = _deps(request)
    session = _current(request)
    if not getattr(request.state, "owner_authorized", False):
        return {**OperationResult().as_dict(), "ownerNotice": OWNER_ONLY_MESSAGE}
    result = _generate_report(deps, session, search_id, payload.minScore if payload else 0)
    return {**result.as_dict(), "ownerNotice": None}


@router.post("/api/session/end")
def end_session(request: Request):
    cookie, tab = _identity(request)
    return _conversation(_deps(request)).close(cookie, tab)


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
        + hmac.new(deps.csrf_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
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
    if request.headers.get("sec-fetch-site") == "cross-site" or not _origin_allowed(request):
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
    if request.headers.get("sec-fetch-site") == "cross-site" or not _origin_allowed(request):
        raise ApplicationError("ORIGIN_FORBIDDEN", "Origine nepermisă.", 403)
    deps = _deps(request)
    if not key:
        nonce = secrets.token_urlsafe(24)
        return HTMLResponse(
            owner_page(deps.settings.public_root_path, nonce),
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            },
        )
    if len(key) > 4096:
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


def create_app(config: Settings | None = None, dependencies: Dependencies | None = None) -> FastAPI:
    """Side-effect-free factory; runtime resources belong to lifespan."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        owned = dependencies is None
        cleanup_task = None
        runtime = dependencies
        session_store = ai = auth = classifier = None
        try:
            if owned:
                cfg = config or Settings.from_env(dotenv=True)
                configure_settings(cfg)
                logging.basicConfig(
                    level=getattr(logging, cfg.log_level, logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s",
                )
                access_logger = logging.getLogger("uvicorn.access")
                if not any(isinstance(f, OwnerAccessLogFilter) for f in access_logger.filters):
                    access_logger.addFilter(OwnerAccessLogFilter())
                session_store = SessionStore(
                    cfg.temp_dir, cfg.session_idle_seconds, cfg.session_max_seconds, cfg
                )
                ai = create_ai_client(cfg)
                classifier = MessageClassifier(cfg, herb_catalog=load_herbs)
                auth = OwnerAuth(cfg.owner_key, PostgresOwnerSessionRepository(cfg.database_url))
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
                    classify=classifier,
                )
                application.state.dependencies = runtime
                application.root_path = cfg.public_root_path
                application.mount(
                    "/",
                    StaticFiles(directory=str(cfg.frontend_dist_dir), html=True, check_dir=False),
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
                if classifier:
                    classifier.close()
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
            headers={"Retry-After": "60"} if isinstance(exc, IndexUnavailable) else None,
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
                    raise ApplicationError("ORIGIN_FORBIDDEN", "Origine nepermisă.", 403)
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
