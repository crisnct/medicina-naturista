"""Create only a missing PostgreSQL database, before transactional migrations."""

from __future__ import annotations

import hashlib

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def ensure_database(database_url: str, bootstrap_url: str = "") -> bool:
    target = conninfo_to_dict(database_url)
    name = target.get("dbname")
    if not name:
        raise ValueError("DATABASE_NAME_REQUIRED")
    try:
        with psycopg.connect(database_url, connect_timeout=5):
            return False
    except (psycopg.OperationalError, psycopg.errors.InvalidCatalogName) as error:
        # libpq connection failures often omit SQLSTATE, including a missing DB.
        # Confirm absence through pg_database instead of parsing a translated
        # error message or treating any connection failure as permission to create.
        if error.sqlstate not in (None, "3D000"):
            raise
        connection_failure = error

    maintenance = make_conninfo(database_url, dbname="postgres")
    if bootstrap_url:
        supplied = conninfo_to_dict(bootstrap_url)
        # Bootstrap may use a separate role/database, but never another server.
        for key, default in (("host", ""), ("hostaddr", ""), ("port", "5432")):
            if supplied.get(key, default) != target.get(key, default):
                raise ValueError("DATABASE_BOOTSTRAP_SERVER_MISMATCH")
        maintenance = bootstrap_url
    lock = int.from_bytes(
        hashlib.sha256(f"create-database:{name}".encode()).digest()[:8], "big", signed=True
    )
    created = False
    try:
        maintenance_connection = psycopg.connect(maintenance, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError:
        raise connection_failure from None
    with maintenance_connection as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (lock,))
        try:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
            ).fetchone()
            if exists:
                # Another bootstrap may have created it while we were waiting.
                try:
                    with psycopg.connect(database_url, connect_timeout=5):
                        return False
                except psycopg.OperationalError:
                    raise connection_failure from None
            else:
                # The target role owns the database even when bootstrap uses another role.
                owner = target.get("user", connection.info.user)
                try:
                    connection.execute(
                        sql.SQL("CREATE DATABASE {} OWNER {}").format(
                            sql.Identifier(name), sql.Identifier(owner)
                        )
                    )
                    created = True
                except psycopg.errors.DuplicateDatabase:
                    pass
        finally:
            if not connection.closed and not connection.broken:
                connection.execute("SELECT pg_advisory_unlock(%s)", (lock,))
    with psycopg.connect(database_url, connect_timeout=5):
        pass
    return created
