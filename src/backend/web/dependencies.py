"""Injectable boundaries; constructing these objects performs no infrastructure I/O."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from backend.config import Settings
from backend.core.models import SessionSnapshot
from backend.core.owner_auth import OwnerAuth
from backend.core.rate_limits import RateLimiter
from backend.core.sessions import SessionStore


class AIProtocol(Protocol):
    def context_budget(self) -> int | None: ...
    def generate(self, profile: dict, evidence: dict) -> dict: ...
    def is_configured(self) -> bool: ...
    def close(self) -> None: ...


class RetrievalProtocol(Protocol):
    document_count: int
    category_tree: Any

    def collect(
        self, session: SessionSnapshot, max_chars: int | None = None
    ) -> dict: ...


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
    identify: Callable | None = None
    email: Callable | None = None
    pdf: Callable | None = None
