"""Apply versioned SQL explicitly, under an advisory lock and transactional ledger."""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from backend.config import Settings

MIGRATIONS = Path(__file__).resolve().parents[1] / "backend" / "migrations"


def migrate(database_url: str) -> list[str]:
    applied = []
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (7310192026,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if conn.execute(
                "SELECT version FROM schema_migrations WHERE version = %s", (path.name,)
            ).fetchone():
                continue
            conn.execute(path.read_text(encoding="utf-8-sig"))
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
            )
            applied.append(path.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    config = Settings.from_env(dotenv=True)
    try:
        versions = migrate(config.database_url)
    except psycopg.Error:
        raise SystemExit(
            "Migrarea a eșuat. Verificați PostgreSQL și permisiunile; nicio migrare parțială nu a fost publicată."
        ) from None
    print("Migrări aplicate: " + (", ".join(versions) or "schema este la zi"))


if __name__ == "__main__":
    main()
