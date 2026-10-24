"""Injectable boundaries; constructing these objects performs no infrastructure I/O."""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.core.contracts import (
    AIProtocol,
    ClassifyMessage,
    EmailProtocol,
    EstimateReportDuration,
    IdentifyCondition,
    ListTopHerbs,
    LookupHerb,
    LookupHerbEvidence,
    RecordReportMetrics,
    RenderPDF,
    ReportModel,
    RetrievalProtocol,
)
from backend.core.owner_auth import OwnerAuth
from backend.core.rate_limits import RateLimiter
from backend.core.sessions import SessionStore


@dataclass
class Dependencies:
    settings: Settings
    store: SessionStore
    retriever: RetrievalProtocol
    ai: AIProtocol
    owner_auth: OwnerAuth
    request_limiter: RateLimiter
    login_limiter: RateLimiter
    csrf_secret: bytes
    identify: IdentifyCondition | None = None
    email: EmailProtocol | None = None
    pdf: RenderPDF | None = None
    classify: ClassifyMessage | None = None
    herb_lookup: LookupHerb | None = None
    top_herbs: ListTopHerbs | None = None
    report_clients: dict[ReportModel, AIProtocol] | None = None
    record_report_metrics: RecordReportMetrics | None = None
    estimate_report_duration: EstimateReportDuration | None = None
    herb_evidence: LookupHerbEvidence | None = None
