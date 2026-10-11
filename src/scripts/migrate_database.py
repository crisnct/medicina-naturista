"""Apply versioned SQL explicitly, under an advisory lock and transactional ledger."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import psycopg

from backend.ai.condition_repository import read_conditions
from backend.ai.herb_repository import read_herbs
from backend.ai.index_state import INDEX_LOCK
from backend.config import Settings
from backend.core.errors import ApplicationError

MIGRATIONS = Path(__file__).resolve().parents[1] / "backend" / "migrations"


def migrate(database_url: str, *, lock_timeout_ms: int | None = None) -> list[str]:
    applied = []
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        if lock_timeout_ms is not None:
            if lock_timeout_ms <= 0:
                raise ValueError("INVALID_MIGRATION_LOCK_TIMEOUT")
            conn.execute("SELECT set_config('lock_timeout', %s, true)", (str(lock_timeout_ms),))
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (7310192026,))
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (INDEX_LOCK,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if conn.execute(
                "SELECT version FROM schema_migrations WHERE version = %s", (path.name,)
            ).fetchone():
                continue
            conn.execute(path.read_text(encoding="utf-8-sig"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)
        read_conditions(conn)
        read_herbs(conn)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    config = Settings.from_env(dotenv=True)
    try:
        versions = migrate(config.database_url)
    except ApplicationError as error:
        raise SystemExit(f"Migrarea a eșuat la validarea cataloagelor: {error.code}") from None
    except psycopg.Error as error:
        logging.getLogger(__name__).error(
            "migration_failed stage=sql error_type=%s sqlstate=%s message=%s",
            type(error).__name__,
            error.sqlstate,
            error.diag.message_primary if error.sqlstate else "connection unavailable",
        )
        raise SystemExit(
            "Migrarea a eșuat. Verificați PostgreSQL și permisiunile; nicio migrare parțială nu a fost publicată."
        ) from None
    print("Migrări aplicate: " + (", ".join(versions) or "schema este la zi"))


if __name__ == "__main__":
    main()
