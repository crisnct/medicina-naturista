"""FastAPI JSON boundary. Slow stages use independent snapshots and atomic commits."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager, suppress
from functools import partial
from http.cookies import CookieError, SimpleCookie
from typing import Literal
from urllib.parse import quote, urlparse

from fastapi import APIRouter, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, model_validator

from backend.ai.client import create_report_clients
from backend.ai.condition_ai import identify_conditions
from backend.ai.db import get_pool
from backend.ai.herb_conditions import lookup_herb_conditions
from backend.ai.herb_evidence import lookup_herb_evidence
from backend.ai.herb_images import lookup_herb_image
from backend.ai.herb_ranking import list_top_herbs, list_top_herbs_for_condition
from backend.ai.herb_ranking import warm_up as warm_up_herbs
from backend.ai.herb_safety import lookup_herb_safety, lookup_herb_safety_evidence
from backend.ai.herbs import load_herbs
from backend.ai.index_state import IndexUnavailable, index_reader
from backend.ai.message_classification import MessageClassifier
from backend.ai.report_validation import ValidationWarning
from backend.ai.retrieval import Retriever
from backend.ai.search import SearchSignals
from backend.ai.search import warm_up as warm_up_search
from backend.config import Settings, configure_settings
from backend.core.contracts import (
    AIProtocol,
    HerbSafetyEvidencePage,
    HerbSafetyPage,
    ReportEffort,
    ReportModel,
)
from backend.core.conversation import (
    ConversationService,
    welcome,
)
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.herb_categories import category_labels
from backend.core.language import LANGUAGES, current_language, language_scope, validate_language
from backend.core.models import (
    CommitChange,
    OperationResult,
    SessionData,
)
from backend.core.operation_context import OperationBudget, operation_budget
from backend.core.owner_auth import OwnerAuth, PostgresOwnerSessionRepository
from backend.core.rate_limits import RateLimiter
from backend.core.report_generation import ReportGenerationService
from backend.core.report_metrics import MAX_BIGINT
from backend.core.report_models import (
    DEFAULT_REPORT_EFFORT,
    DEFAULT_REPORT_MODELS,
    EFFORT_MODELS,
)
from backend.core.sessions import SessionStore
from backend.core.texts import catalog, public_catalog, tr
from backend.integrations.gmail import send_report
from backend.persistence.report_metrics import PostgresReportMetricsRepository
from backend.reporting.chat import (
    text as _text,
)
from backend.reporting.service import create_ranked_pdf
from backend.web.access_logs import OwnerAccessLogFilter
from backend.web.body_limit import ApiBodyLimitMiddleware
from backend.web.dependencies import Dependencies
from backend.web.owner_page import owner_page
from backend.web.texts import TextStaticFiles

logger = logging.getLogger("naturist.web")
COOKIE = "naturist_sid"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
TAB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_COOKIE = "naturist_owner"
CSRF_COOKIE = "naturist_owner_csrf"
OWNER_COOKIE_MAX_AGE = 31536000


def owner_only_message() -> str:
    return tr("common.owner_only_generation")


router = APIRouter()


@router.get("/api/texts")
def application_texts() -> JSONResponse:
    return JSONResponse(public_catalog(), headers={"Cache-Control": "no-store"})


# Serialize one category node (and, recursively, its children) into the plain
# JSON shape the frontend's category tree component consumes.
def localized_source_label(label: str) -> str:
    known = {
        "ro": {"Safe": "Sigure", "Partial Safe": "Parțial sigure", "Unknown": "Necunoscute"},
        "en": {
            "Sigure": "Safe",
            "Parțial sigure": "Partially safe",
            "Necunoscute": "Unknown",
            "Partial Safe": "Partially safe",
        },
    }
    return known[current_language()].get(label, category_labels().get(label, label))


def _category_node_payload(tree, node_id: str) -> dict:
    node = tree.nodes[node_id]
    return {
        "id": node.id,
        "label": localized_source_label(node.label),
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
            raise ValueError(tr("errors.search_signal_required"))
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


# The "Scor minim" chosen next to "Generează raportul": only fragments whose
# relevance_percent is at least this value are sent to the AI (0 = all).
class GenerateRequest(BaseModel):
    minScore: int = Field(default=0, strict=True, ge=0, le=100)
    model: ReportModel | None = None
    # Ignored, and recorded as None, for models that cannot take an effort.
    effort: ReportEffort = DEFAULT_REPORT_EFFORT
    requestId: str = Field(
        default_factory=lambda: secrets.token_urlsafe(24), pattern=r"^[A-Za-z0-9_-]{8,64}$"
    )


class AIActivityResponse(BaseModel):
    phase: Literal["waiting", "processing", "thinking", "answering"]
    lastActivityAgeMs: int | None = Field(default=None, ge=0)
    firstEventElapsedMs: int | None = Field(default=None, ge=0)
    firstThinkingElapsedMs: int | None = Field(default=None, ge=0)
    firstAnswerElapsedMs: int | None = Field(default=None, ge=0)
    thinkingCharactersReceived: int = Field(default=0, ge=0)


class ReportDurationEstimateResponse(BaseModel):
    model: ReportModel
    effort: ReportEffort | None = None
    characters: int = Field(ge=0, le=MAX_BIGINT)
    estimatedSeconds: int | None = Field(default=None, ge=0)
    sampleCount: int = Field(ge=0)


class ReportBatchPreviewResponse(BaseModel):
    index: int = Field(ge=1)
    state: Literal["pending", "running", "validated", "failed", "cancelled", "timed_out"]
    reportPreview: str | None = None
    streamPreview: str | None = None
    thinkingPreview: str | None = None
    aiActivity: AIActivityResponse | None = None


class GenerateResponse(BaseModel):
    language: Literal["ro", "en"] = "ro"
    jobId: str
    searchId: str
    state: Literal["accepted", "running", "succeeded", "failed", "cancelled", "timed_out"]
    stage: str
    provider: str
    model: str
    modelChoice: str
    effort: ReportEffort | None = None
    createdAt: float
    deadlineAt: float
    startedAt: float | None = None
    finishedAt: float | None = None
    reportId: str | None = None
    partial: bool = False
    validationWarnings: list[ValidationWarning] = Field(default_factory=list)
    workerActive: bool = False
    pollAfterMs: int = 3000
    queuePosition: int | None = None
    streamPreview: str | None = None
    reportPreview: str | None = None
    previewVersion: int = Field(default=0, ge=0)
    batchesCompleted: int = Field(default=0, ge=0)
    batchesTotal: int = Field(default=0, ge=0)
    batchPreviews: list[ReportBatchPreviewResponse] = Field(default_factory=list)
    thinkingPreview: str | None = None
    streamTokensPerSecond: float | None = Field(default=None, ge=0)
    thinkingTokensPerSecond: float | None = Field(default=None, ge=0)
    aiActivity: AIActivityResponse | None = None
    errorCode: str | None = None
    message: str | None = None


def _deps(request: Request) -> Dependencies:
    return request.app.state.dependencies


def _identity(request: Request) -> tuple[str, str]:
    cookie = request.cookies.get(COOKIE, "")
    if not COOKIE_RE.fullmatch(cookie):
        cookie = getattr(request.state, "session_cookie", "")
    if not COOKIE_RE.fullmatch(cookie):
        raise HTTPException(401, tr("errors.session_expired"))
    tab = request.headers.get("x-tab-id", "")
    if not TAB_ID_RE.fullmatch(tab):
        raise HTTPException(400, tr("errors.tab_id_invalid"))
    return cookie, tab


def _current(request: Request, create: bool = False) -> SessionData:
    cookie, tab = _identity(request)
    deps = _deps(request)
    session = deps.store.get(cookie, tab, create=create, client_ip=_client_ip(request))
    if session is None:
        raise ApplicationError("SESSION_EXPIRED", tr("errors.session_expired"))
    return session


@router.post("/api/language")
def change_language(request: Request):
    session = _current(request)
    _deps(request).store.set_language(session, current_language())
    return {"language": current_language()}


def _client_ip(request: Request) -> str:
    # ASGI's peer is normalized by the server's explicit trusted proxy allowlist.
    # Never interpret a client-supplied X-Forwarded-For header here.
    return request.client.host if request.client else "unknown"


def _application_error_response(error: ApplicationError) -> JSONResponse:
    retry_after = 60 if isinstance(error, IndexUnavailable) else error.retry_after
    return JSONResponse(
        {"detail": {"code": error.code, "message": error.message}},
        status_code=error.status,
        headers={"Retry-After": str(retry_after)} if retry_after is not None else None,
    )


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
        raise HTTPException(400, tr("errors.invalid_revision")) from None


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
        provider = getattr(ai, "provider", None)
        label = getattr(provider, "label", "AI")
        key_env = getattr(provider, "api_key_env", "AI_API_KEY")
        raise HTTPException(
            503,
            tr("errors.secret_file_missing", label=label, key_env=key_env),
        )
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request):
    _require_initialized(request)
    healthz(request)
    if isinstance(_deps(request).retriever, Retriever):
        with index_reader():
            pass
    return {"status": "ok", "index": "ready"}


@router.get("/api/startup")
def startup_status(request: Request):
    status = dict(request.app.state.startup_status)
    if status.get("message"):
        for key, value in catalog("ro").items():
            if value == status["message"]:
                status["message"] = tr(key)
                break
    return status


def _require_initialized(request: Request) -> None:
    if request.app.state.startup_status["status"] == "initializing":
        raise ApplicationError(
            "APP_INITIALIZING",
            tr("errors.startup_initializing"),
            503,
            retry_after=2,
        )


@router.get("/api/reports/{tab_id}/{report_id}")
def download(tab_id: str, report_id: str, request: Request):
    store = _deps(request).store
    session = store.get(request.cookies.get(COOKIE, ""), tab_id)
    report = store.report(session, report_id) if session else None
    if report is None:
        raise HTTPException(404, tr("errors.report_not_authorized"))
    return Response(
        report.data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(report.filename, safe='')}",
            "Content-Language": report.language,
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/session")
def get_session(request: Request):
    deps = _deps(request)
    session = _current(request, create=True)
    page_id = request.headers.get("x-page-id")
    if page_id is not None and not TAB_ID_RE.fullmatch(page_id):
        raise HTTPException(400, tr("errors.page_id_invalid"))
    if not deps.store.conversation_view(session, page_id=page_id)["history"]:
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
                            f"{welcome()} {question}" if question else welcome(),
                        )
                    ],
                    profile=profile,
                ),
            )
        finally:
            deps.store.finish_operation(operation)
    view = deps.store.conversation_view(session)
    if not getattr(request.state, "owner_authorized", False):
        view["generations"] = [
            job
            for job in view["generations"]
            if job["modelChoice"] in _available_report_models(False)
        ]
    return view


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


@router.get("/api/herb-images/{herb_id}")
def get_herb_image(request: Request, herb_id: int = Path(ge=1, le=2147483647)):
    _require_initialized(request)
    deps = _deps(request)
    deps.request_limiter.check((_client_ip(request), deps.settings.max_requests_per_minute))
    lookup = deps.herb_image or partial(lookup_herb_image, settings=deps.settings)
    image = lookup(herb_id)
    if image is None:
        return Response(status_code=404)
    return FileResponse(image, media_type="image/png")


@router.get("/api/herb-evidence/{group_id}")
def get_herb_evidence(
    request: Request,
    group_id: str = Path(pattern=r"^[A-Za-z0-9_-]{8,64}$"),
    conditionId: int | None = Query(default=None, ge=1, le=2147483647),
    offset: int = Query(default=0, ge=0, le=2147483647),
    evidenceKind: Literal["positive", "contraindication"] = Query(default="positive"),
):
    _require_initialized(request)
    deps = _deps(request)
    deps.request_limiter.check((_client_ip(request), deps.settings.max_requests_per_minute))
    session = _current(request)
    reference = deps.store.herb_evidence_reference(session, group_id)
    if evidenceKind == "contraindication" and not reference.get("cautionRunId"):
        raise ApplicationError(
            "CAUTION_RANKING_NOT_READY", tr("errors.caution_ranking_not_ready"), 503
        )
    condition_ids = (
        reference.get("contraindicationConditionIds", [])
        if evidenceKind == "contraindication"
        else reference["conditionIds"]
    )
    if conditionId is not None and conditionId not in condition_ids:
        raise ApplicationError("INVALID_REQUEST", tr("errors.request_invalid"), 422)
    operation = deps.store.begin_operation(session, "herb_evidence")
    try:
        with operation_budget(
            OperationBudget(
                operation.deadline,
                deps.store.clock,
                lambda: deps.store.checkpoint(operation),
                language=reference.get("language", "ro"),
            )
        ):
            lookup = deps.herb_evidence or partial(lookup_herb_evidence, settings=deps.settings)
            if "cautionRunId" in reference:
                result = lookup(
                    reference["herbId"],
                    reference["positiveRunId"],
                    condition_id=conditionId,
                    offset=offset,
                    evidence_kind=evidenceKind,
                    caution_run_id=reference["cautionRunId"],
                )
            else:
                result = lookup(
                    reference["herbId"],
                    reference["positiveRunId"],
                    condition_id=conditionId,
                    offset=offset,
                )
            if deps.store.herb_evidence_reference(session, group_id) != reference:
                raise ApplicationError(
                    "HERB_EVIDENCE_UNAVAILABLE", tr("errors.herb_evidence_unavailable"), 404
                )
        return result
    except OperationCancelled:
        raise ApplicationError(
            "HERB_EVIDENCE_UNAVAILABLE", tr("errors.herb_evidence_unavailable"), 409
        ) from None
    finally:
        deps.store.finish_operation(operation)


def _herb_safety_response(
    request: Request, group_id: str, offset: int, warning_id: str | None = None
) -> HerbSafetyPage | HerbSafetyEvidencePage:
    _require_initialized(request)
    deps = _deps(request)
    deps.request_limiter.check((_client_ip(request), deps.settings.max_requests_per_minute))
    session = _current(request)
    reference = deps.store.herb_safety_reference(session, group_id)
    operation = deps.store.begin_operation(session, "herb_evidence")
    try:
        with operation_budget(
            OperationBudget(
                operation.deadline,
                deps.store.clock,
                lambda: deps.store.checkpoint(operation),
                language=reference.get("language", "ro"),
            )
        ):
            result: HerbSafetyPage | HerbSafetyEvidencePage
            if warning_id is None:
                lookup = deps.herb_safety or partial(lookup_herb_safety, settings=deps.settings)
                result = lookup(reference["herbId"], reference["safetyRunId"], offset=offset)
            else:
                evidence = deps.herb_safety_evidence or partial(
                    lookup_herb_safety_evidence, settings=deps.settings
                )
                result = evidence(
                    reference["herbId"],
                    reference["safetyRunId"],
                    warning_id=warning_id,
                    offset=offset,
                )
            if deps.store.herb_safety_reference(session, group_id) != reference:
                raise ApplicationError(
                    "HERB_SAFETY_UNAVAILABLE", tr("errors.herb_safety_unavailable"), 404
                )
        return result
    except OperationCancelled:
        raise ApplicationError(
            "HERB_SAFETY_UNAVAILABLE", tr("errors.herb_safety_unavailable"), 409
        ) from None
    finally:
        deps.store.finish_operation(operation)


@router.get("/api/herb-safety/{group_id}", response_model=None)
def get_herb_safety(
    request: Request,
    group_id: str = Path(pattern=r"^[A-Za-z0-9_-]{8,64}$"),
    offset: int = Query(default=0, ge=0, le=2147483647),
) -> HerbSafetyPage | HerbSafetyEvidencePage:
    return _herb_safety_response(request, group_id, offset)


@router.get("/api/herb-safety/{group_id}/evidence", response_model=None)
def get_herb_safety_evidence(
    request: Request,
    group_id: str = Path(pattern=r"^[A-Za-z0-9_-]{8,64}$"),
    warningId: str = Query(pattern=r"^[0-9a-f]{64}$"),
    offset: int = Query(default=0, ge=0, le=2147483647),
) -> HerbSafetyPage | HerbSafetyEvidencePage:
    return _herb_safety_response(request, group_id, offset, warningId)


def _conversation(
    deps: Dependencies,
    ai: AIProtocol | None = None,
    *,
    model_choice: ReportModel | None = None,
    effort: ReportEffort | None = None,
) -> ConversationService:
    selected_ai = ai if ai is not None else deps.ai
    # Bind the effective model now: queued reports must not use a later env default.
    provider = getattr(selected_ai, "provider", None)
    model = getattr(provider, "model", None)
    render_pdf = deps.pdf or partial(create_ranked_pdf, ai_model=model)
    return ConversationService(
        deps.settings,
        deps.store,
        deps.retriever,
        selected_ai,
        deps.identify or identify_conditions,
        deps.email or send_report,
        render_pdf,
        deps.classify,
        deps.herb_lookup or partial(lookup_herb_conditions, settings=deps.settings),
        deps.top_herbs or partial(list_top_herbs, settings=deps.settings),
        report_model=model,
        report_model_choice=model_choice or "",
        report_ai_effort=effort,
        record_report_metrics=deps.record_report_metrics,
        top_herbs_for_condition=deps.top_herbs_for_condition
        or partial(list_top_herbs_for_condition, settings=deps.settings),
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
        raise ApplicationError("REVISION_REQUIRED", tr("errors.message_revision_required"), 422)
    return _conversation(_deps(request)).classify(_current(request), revision)


@router.post("/api/search")
def post_search(request: Request):
    deps = _deps(request)
    if isinstance(deps.retriever, Retriever):
        with index_reader():
            return _conversation(deps).search(_current(request), _revision(request))
    return _conversation(deps).search(_current(request), _revision(request))


def _generate_report(
    deps: Dependencies,
    session: SessionData,
    search_id: str,
    min_score: int = 0,
    model: ReportModel | None = None,
    effort: ReportEffort = DEFAULT_REPORT_EFFORT,
) -> OperationResult:
    # Trusted Python-only entry point; HTTP admission supplies its verified session role.
    model = _select_report_model(deps.settings, model, owner_authorized=True)
    ai = deps.report_clients[model] if deps.report_clients is not None else deps.ai
    return _conversation(
        deps, ai, model_choice=model, effort=_effective_effort(model, effort)
    ).generate(session, search_id, min_score)


# Models without an effort control record and send nothing, whatever the client asked.
def _effective_effort(model: ReportModel, effort: ReportEffort) -> ReportEffort | None:
    return effort if model in EFFORT_MODELS else None


def _available_report_models(
    owner_authorized: bool, configured: tuple[ReportModel, ...] = DEFAULT_REPORT_MODELS
) -> list[ReportModel]:
    return list(configured) if owner_authorized else []


def _select_report_model(
    settings: Settings, model: ReportModel | None, *, owner_authorized: bool
) -> ReportModel:
    if model is None:
        model = settings.report_generation_model
    if model not in settings.report_generation_models:
        raise ApplicationError(
            "MODEL_NOT_CONFIGURED",
            tr("errors.model_not_configured"),
            422,
        )
    if not owner_authorized:
        raise ApplicationError("MODEL_FORBIDDEN", owner_only_message(), 403)
    return model


@router.get("/api/report-models")
def report_models(request: Request):
    configured = _deps(request).settings.report_generation_models
    allowed = _available_report_models(
        getattr(request.state, "owner_authorized", False),
        configured,
    )
    return {
        "models": list(configured),
        "defaultModel": configured[0],
        "allowedModels": allowed,
        "effortModels": [model for model in configured if model in EFFORT_MODELS],
    }


@router.get("/api/report-duration-estimate", response_model=ReportDurationEstimateResponse)
def report_duration_estimate(
    request: Request,
    model: ReportModel,
    characters: int = Query(..., ge=0, le=MAX_BIGINT),
    effort: ReportEffort | None = None,
):
    deps = _deps(request)
    if model not in deps.settings.report_generation_models:
        raise ApplicationError(
            "MODEL_NOT_CONFIGURED",
            tr("errors.model_not_configured"),
            422,
        )
    deps.request_limiter.check(
        (f"report-estimate:{_client_ip(request)}", deps.settings.max_requests_per_minute)
    )
    if deps.estimate_report_duration is None:
        raise ApplicationError(
            "REPORT_ESTIMATE_UNAVAILABLE",
            tr("errors.estimate_unavailable"),
            503,
        )
    try:
        estimate = deps.estimate_report_duration(
            model, characters, _effective_effort(model, effort) if effort else None
        )
    except Exception as exc:
        logger.warning("report_duration_estimate_unavailable type=%s", type(exc).__name__)
        raise ApplicationError(
            "REPORT_ESTIMATE_UNAVAILABLE",
            tr("errors.estimate_unavailable"),
            503,
        ) from None
    return ReportDurationEstimateResponse(
        model=model,
        effort=_effective_effort(model, effort) if effort else None,
        characters=characters,
        estimatedSeconds=estimate.estimated_seconds,
        sampleCount=estimate.sample_count,
    )


@router.post(
    "/api/searches/{search_id}/generate",
    status_code=202,
    response_model=GenerateResponse,
)
def generate(search_id: str, request: Request, payload: GenerateRequest | None = None):
    deps = _deps(request)
    session = _current(request)
    options = payload or GenerateRequest()
    model = _select_report_model(
        deps.settings,
        options.model,
        owner_authorized=getattr(request.state, "owner_authorized", False),
    )
    ai = deps.report_clients[model] if deps.report_clients is not None else deps.ai
    effort = _effective_effort(model, options.effort)
    service: ReportGenerationService = request.app.state.report_generation
    result = service.start(
        _conversation(deps, ai, model_choice=model, effort=effort),
        session,
        search_id,
        options.minScore,
        options.requestId,
        model,
        effort,
    )
    return JSONResponse(
        result,
        status_code=202,
        headers={
            "Location": f"{deps.settings.public_root_path}/api/report-generations/{result['jobId']}",
            "Cache-Control": "no-store",
        },
    )


def _generation_status(request: Request, job_id: str, *, cancel: bool = False):
    deps = _deps(request)
    session = _current(request)
    deps.request_limiter.check(
        (f"poll:{session.lifetime_id}", 120), (f"poll-ip:{_client_ip(request)}", 240)
    )
    if not getattr(request.state, "owner_authorized", False):
        raise ApplicationError("MODEL_FORBIDDEN", owner_only_message(), 403)
    return request.app.state.report_generation.generation(session, job_id, cancel=cancel)


@router.get("/api/report-generations/{job_id}", response_model=GenerateResponse)
def generation_status(job_id: str, request: Request):
    return _generation_status(request, job_id)


@router.post("/api/report-generations/{job_id}/cancel", response_model=GenerateResponse)
def cancel_generation(job_id: str, request: Request):
    return _generation_status(request, job_id, cancel=True)


@router.post("/api/session/end")
def end_session(request: Request):
    cookie, tab = _identity(request)
    return _conversation(_deps(request)).close(cookie, tab)


@router.post("/api/session/unload", status_code=204)
def unload_session(request: Request):
    try:
        cookie, tab = _identity(request)
        _deps(request).store.close_page(cookie, tab, request.headers.get("x-page-id"))
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
        raise ApplicationError("CSRF_FAILED", tr("errors.authorization_invalid"), 403)
    expected = hmac.new(
        _deps(request).csrf_secret, match[1].encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(match[2], expected):
        raise ApplicationError("CSRF_FAILED", tr("errors.authorization_invalid"), 403)


@router.get("/api/owner")
def owner_status(request: Request):
    if request.headers.get("sec-fetch-site") == "cross-site" or not _origin_allowed(request):
        raise ApplicationError("ORIGIN_FORBIDDEN", tr("errors.origin_forbidden"), 403)
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
        raise ApplicationError("ORIGIN_FORBIDDEN", tr("errors.origin_forbidden"), 403)
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
        warm_task = None
        runtime = dependencies
        session_store = auth = classifier = None
        report_clients: dict[ReportModel, AIProtocol] = {}
        try:
            for language in LANGUAGES:
                catalog(language)
            if owned:
                application.state.startup_status = {
                    "status": "initializing",
                    "message": tr("errors.startup_initializing"),
                }
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
                report_clients = create_report_clients(cfg)
                ai = report_clients[cfg.report_generation_model]
                classifier = MessageClassifier(cfg, herb_catalog=load_herbs)
                auth = OwnerAuth(cfg.owner_key, PostgresOwnerSessionRepository(cfg.database_url))
                retriever = await asyncio.to_thread(Retriever, cfg.documents_dir)
                metrics_repository = PostgresReportMetricsRepository(get_pool)
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
                    report_clients=report_clients,
                    record_report_metrics=metrics_repository,
                    estimate_report_duration=metrics_repository.estimate_duration,
                )
                application.state.dependencies = runtime
                application.root_path = cfg.public_root_path
                application.mount(
                    "/",
                    TextStaticFiles(
                        directory=str(cfg.frontend_dist_dir), html=True, check_dir=False
                    ),
                    name="frontend",
                )

                async def warm_search():
                    started = time.perf_counter()
                    logger.info("warm_up_started stage=search")
                    try:
                        await asyncio.to_thread(warm_up_search)
                    except Exception as exc:
                        logger.warning("warm_up_failed stage=search type=%s", type(exc).__name__)
                        application.state.startup_status = {
                            "status": "degraded",
                            "message": tr("errors.warmup_degraded"),
                        }
                    else:
                        application.state.startup_status = {"status": "ready", "message": None}
                    finally:
                        logger.info(
                            "warm_up_finished stage=search duration_ms=%s",
                            round((time.perf_counter() - started) * 1000),
                        )
                    # After readiness is published: name dictionaries and ranking verification
                    # only speed up the first herb ranking, so they must not delay startup.
                    herb_started = time.perf_counter()
                    try:
                        await asyncio.to_thread(warm_up_herbs, cfg)
                    except Exception as exc:
                        logger.warning("warm_up_failed stage=herbs type=%s", type(exc).__name__)
                    else:
                        logger.info(
                            "warm_up_finished stage=herbs duration_ms=%s",
                            round((time.perf_counter() - herb_started) * 1000),
                        )

                warm_task = asyncio.create_task(warm_search(), name="search-warm-up")
            assert runtime is not None
            if not hasattr(application.state, "report_generation"):
                application.state.report_generation = ReportGenerationService(runtime.store)

            async def cleanup():
                while True:
                    await asyncio.sleep(30)
                    await asyncio.to_thread(runtime.store.sweep)
                    runtime.request_limiter.sweep()
                    runtime.login_limiter.sweep()

            cleanup_task = asyncio.create_task(cleanup())
            yield
        finally:
            drained = True
            if warm_task:
                _done, pending = await asyncio.wait(
                    {warm_task},
                    timeout=(runtime.settings.report_shutdown_timeout_seconds if runtime else 20),
                )
                drained = not pending
                if pending:
                    logger.warning("warm_up_shutdown_pending")
            if cleanup_task:
                cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup_task
            if runtime:
                runtime.store.shutdown()
                workers_drained = await asyncio.to_thread(
                    runtime.store.wait_workers, runtime.settings.report_shutdown_timeout_seconds
                )
                drained = drained and workers_drained
                if hasattr(application.state, "report_generation"):
                    await asyncio.to_thread(application.state.report_generation.close, wait=drained)
                if not drained:
                    logger.warning(
                        "report_shutdown_pending_workers timeout_seconds=%s",
                        runtime.settings.report_shutdown_timeout_seconds,
                    )
            elif session_store:
                session_store.shutdown()
            if owned and drained:
                for client in report_clients.values():
                    client.close()
                if classifier:
                    classifier.close()
                if auth:
                    auth.repository.close()
                from backend.ai import condition_ai, db

                condition_ai.close_clients()
                db.close_pool()

    application = FastAPI(
        title="medicina-naturista",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        root_path=config.public_root_path if config else "",
    )
    application.state.startup_status = {
        "status": "ready" if dependencies else "initializing",
        "message": None,
    }
    if dependencies:
        application.state.dependencies = dependencies
        application.state.report_generation = ReportGenerationService(dependencies.store)

    @application.exception_handler(ApplicationError)
    async def controlled_error(request: Request, exc: ApplicationError):
        return _application_error_response(exc)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # FastAPI's default validation response echoes input, including login keys.
        return JSONResponse(
            {
                "detail": {
                    "code": "INVALID_REQUEST",
                    "message": tr("errors.request_invalid"),
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
            if request.method == "POST" and (
                path in {"/api/messages", "/api/classify", "/api/condition", "/api/search"}
                or (path.startswith("/api/searches/") and path.endswith("/generate"))
            ):
                _require_initialized(request)
            if (request.method == "POST" and path == "/api/owner/login") or (
                request.method == "GET" and path == "/owner"
            ):
                deps.login_limiter.check(
                    (_client_ip(request), deps.settings.owner_login_per_minute)
                )
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                if not _origin_allowed(request):
                    raise ApplicationError("ORIGIN_FORBIDDEN", tr("errors.origin_forbidden"), 403)
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
            response = _application_error_response(exc)
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

    @application.middleware("http")
    async def request_language(request: Request, call_next):
        raw = request.headers.get("x-app-language") or request.query_params.get("language", "ro")
        try:
            language = validate_language(raw)
        except ValueError:
            return JSONResponse(
                {
                    "detail": {
                        "code": "INVALID_LANGUAGE",
                        "message": tr("errors.request_invalid", language="ro"),
                    }
                },
                status_code=422,
            )
        with language_scope(language):
            response = await call_next(request)
            response.headers.setdefault("Content-Language", language)
            return response

    application.include_router(router)
    return application


app = create_app()
