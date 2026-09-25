"""Ephemeral, tab-scoped state. No database stores medical information."""
from __future__ import annotations

import secrets
import logging
import shutil
import threading
import time
from pathlib import Path

from medicina_naturista.core.models import SessionData

logger = logging.getLogger("naturist.sessions")


class SessionStore:
    # Initialize the in-memory session registry and remove stale temporary data.
    def __init__(self, temp_root: Path, idle_seconds: int, max_seconds: int) -> None:
        self.temp_root = temp_root.resolve()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.idle_seconds = idle_seconds
        self.max_seconds = max_seconds
        self._sessions: dict[tuple[str, str], SessionData] = {}
        self._lock = threading.RLock()
        removed_directories = 0
        for child in self.temp_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                removed_directories += 1
        logger.info(
            "session_store_initialized temp_root=%s idle_seconds=%s max_seconds=%s stale_directories_removed=%s",
            self.temp_root,
            idle_seconds,
            max_seconds,
            removed_directories,
        )

    # Check both inactivity and absolute lifetime limits for a session.
    def _expired(self, session: SessionData) -> bool:
        now = time.monotonic()
        return now - session.last_seen > self.idle_seconds or now - session.created_at > self.max_seconds

    # Retrieve a tab-scoped session and optionally create it when absent.
    def get(self, cookie_id: str, tab_id: str, create: bool = False) -> SessionData | None:
        if not cookie_id or not tab_id:
            return None
        key = (cookie_id, tab_id)
        with self._lock:
            session = self._sessions.get(key)
            if session and self._expired(session):
                logger.info("session_expired tab_id=%s", tab_id)
                self._delete_locked(key)
                session = None
            if session is None and create:
                directory = self.temp_root / secrets.token_hex(20)
                directory.mkdir(mode=0o700)
                session = SessionData(cookie_id=cookie_id, tab_id=tab_id, directory=directory)
                self._sessions[key] = session
                logger.info("session_created tab_id=%s active_sessions=%s", tab_id, len(self._sessions))
            if session:
                session.touch()
            return session

    # Delete the requested session while holding the store lock.
    def delete(self, cookie_id: str, tab_id: str) -> None:
        with self._lock:
            self._delete_locked((cookie_id, tab_id))

    # Remove one session and its temporary directory without acquiring the lock.
    def _delete_locked(self, key: tuple[str, str]) -> None:
        session = self._sessions.pop(key, None)
        if session:
            session.clear_report()
            session.history.clear()
            shutil.rmtree(session.directory, ignore_errors=True)
            logger.info("session_deleted tab_id=%s active_sessions=%s", key[1], len(self._sessions))

    # Delete every session that has exceeded an idle or absolute lifetime limit.
    def sweep(self) -> None:
        with self._lock:
            expired = 0
            for key, session in list(self._sessions.items()):
                if self._expired(session):
                    self._delete_locked(key)
                    expired += 1
            if expired:
                logger.info("session_sweep expired=%s active_sessions=%s", expired, len(self._sessions))

    # Return the number of currently active sessions.
    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
