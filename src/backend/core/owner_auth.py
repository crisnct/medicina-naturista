"""Individual signed owner tokens. Only their SHA-256 digest is persisted."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Protocol

import psycopg

from backend.core.errors import ApplicationError

TOKEN_RE = re.compile(r"^v1\.([A-Za-z0-9_-]{43})\.([0-9a-f]{64})$")


class OwnerSessionRepository(Protocol):
    def issue(self, token_hash: str) -> None: ...
    def active(self, token_hash: str) -> bool: ...
    def revoke(self, token_hash: str) -> None: ...
    def close(self) -> None: ...


class PostgresOwnerSessionRepository:
    """No DDL in runtime. Short-lived connections have bounded connect/query timeouts."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _execute(self, query: str, token_hash: str):
        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=5,
                options="-c statement_timeout=5000",
            ) as conn:
                return conn.execute(query, (token_hash,)).fetchone()
        except psycopg.Error:
            # Do not echo database exceptions: connection strings may contain credentials.
            raise ApplicationError(
                "OWNER_AUTH_UNAVAILABLE",
                "Autorizarea este temporar indisponibilă. Verificați baza și migrările.",
                503,
            ) from None

    def issue(self, token_hash: str) -> None:
        self._execute(
            "INSERT INTO owner_sessions (token_hash) VALUES (%s) RETURNING token_hash",
            token_hash,
        )

    def active(self, token_hash: str) -> bool:
        return (
            self._execute(
                "SELECT token_hash FROM owner_sessions WHERE token_hash = %s AND revoked_at IS NULL",
                token_hash,
            )
            is not None
        )

    def revoke(self, token_hash: str) -> None:
        self._execute(
            "UPDATE owner_sessions SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP) WHERE token_hash = %s RETURNING token_hash",
            token_hash,
        )

    def close(self) -> None:
        pass  # Connections close with their transaction context; no shared pool.


class OwnerAuth:
    def __init__(self, key: str, repository: OwnerSessionRepository) -> None:
        self._key = key.encode("utf-8")
        self.repository = repository

    def _sign(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).hexdigest()

    def login(self, key: str) -> str:
        if not self._key or not hmac.compare_digest(key.encode("utf-8"), self._key):
            raise ApplicationError("OWNER_LOGIN_FAILED", "Cheie incorectă.", 401)
        payload = "v1." + secrets.token_urlsafe(32)
        token = payload + "." + self._sign(payload)
        self.repository.issue(self.digest(token))
        return token

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _signed(self, token: str) -> bool:
        match = TOKEN_RE.fullmatch(token)
        return bool(
            self._key
            and match
            and hmac.compare_digest(match[2], self._sign("v1." + match[1]))
        )

    def authorized(self, token: str) -> bool:
        return self._signed(token) and self.repository.active(self.digest(token))

    def logout(self, token: str) -> None:
        if self._signed(token):
            self.repository.revoke(self.digest(token))
