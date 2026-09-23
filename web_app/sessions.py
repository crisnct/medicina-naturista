"""Ephemeral, tab-scoped state. No database stores patient information."""
from __future__ import annotations

import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from web_app.profile import HealthProfile


@dataclass
class UploadedDocument:
    name: str
    chunks: list[dict[str, Any]]
    vectors: np.ndarray
    size_bytes: int
    summary: str = ""


@dataclass
class SessionData:
    cookie_id: str
    tab_id: str
    directory: Path
    created_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    profile: HealthProfile = field(default_factory=HealthProfile)
    history: list[dict[str, str]] = field(default_factory=list)
    documents: list[UploadedDocument] = field(default_factory=list)
    report_bytes: bytes | None = None
    report_id: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def clear_report(self) -> None:
        self.report_bytes = None
        self.report_id = None

    @property
    def uploaded_bytes(self) -> int:
        return sum(item.size_bytes for item in self.documents)

    @property
    def chunk_count(self) -> int:
        return sum(len(item.chunks) for item in self.documents)


class SessionStore:
    def __init__(self, temp_root: Path, idle_seconds: int, max_seconds: int) -> None:
        self.temp_root = temp_root.resolve()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self._sessions: dict[tuple[str, str], SessionData] = {}
        self._lock = threading.RLock()
        # All data in this directory belongs to an earlier, ended process.
        for child in self.temp_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    def _expired(self, session: SessionData) -> bool:
        now = time.monotonic()
        return now - session.last_seen > self.idle_seconds or now - session.created_at > self.max_seconds

    def get(self, cookie_id: str, tab_id: str, create: bool = False) -> SessionData | None:
        if not cookie_id or not tab_id:
            return None
        key = (cookie_id, tab_id)
        with self._lock:
            session = self._sessions.get(key)
            if session and self._expired(session):
                self._delete_locked(key)
                session = None
            if session is None and create:
                directory = self.temp_root / secrets.token_hex(20)
                directory.mkdir(mode=0o700)
                session = SessionData(cookie_id=cookie_id, tab_id=tab_id, directory=directory)
                self._sessions[key] = session
            if session:
                session.touch()
            return session

    def delete(self, cookie_id: str, tab_id: str) -> None:
        with self._lock:
            self._delete_locked((cookie_id, tab_id))

    def _delete_locked(self, key: tuple[str, str]) -> None:
        session = self._sessions.pop(key, None)
        if session:
            session.clear_report()
            session.documents.clear()
            session.history.clear()
            shutil.rmtree(session.directory, ignore_errors=True)

    def sweep(self) -> None:
        with self._lock:
            for key, session in list(self._sessions.items()):
                if self._expired(session):
                    self._delete_locked(key)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
