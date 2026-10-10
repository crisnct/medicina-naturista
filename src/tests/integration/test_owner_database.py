"""Owner ledger and migrations tested only against disposable PostgreSQL."""

from __future__ import annotations

import hashlib
import unittest

import psycopg

from backend.core.owner_auth import OwnerAuth, PostgresOwnerSessionRepository
from scripts.migrate_database import migrate
from tests.support.postgres import PostgresFixture

fixture = PostgresFixture()


def setUpModule():
    fixture.start()


def tearDownModule():
    fixture.stop()


class OwnerDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.url = fixture._container.get_connection_url()
        migrate(self.url)
        with psycopg.connect(self.url) as conn:
            conn.execute("TRUNCATE owner_sessions")

    def test_revocation_and_restart_are_enforced_by_real_database(self):
        auth = OwnerAuth("synthetic key", PostgresOwnerSessionRepository(self.url))
        token = auth.login("synthetic key")
        restarted = OwnerAuth("synthetic key", PostgresOwnerSessionRepository(self.url))
        self.assertTrue(restarted.authorized(token))
        with psycopg.connect(self.url) as conn:
            row = conn.execute(
                "SELECT token_hash, created_at, revoked_at FROM owner_sessions"
            ).fetchone()
            self.assertEqual(row[0], hashlib.sha256(token.encode()).hexdigest())
            self.assertNotIn(token, repr(row))
            self.assertNotIn("synthetic key", repr(row))
            self.assertIsNotNone(row[1])
            self.assertIsNone(row[2])
            columns = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'owner_sessions' ORDER BY ordinal_position"
            ).fetchall()
            self.assertEqual(
                [c[0] for c in columns], ["token_hash", "created_at", "revoked_at"]
            )
        restarted.logout(token)
        restarted.logout(token)
        self.assertFalse(auth.authorized(token))
        with psycopg.connect(self.url) as conn:
            self.assertIsNotNone(
                conn.execute("SELECT revoked_at FROM owner_sessions").fetchone()[0]
            )

    def test_migrations_are_idempotent_and_runtime_never_creates_tables(self):
        self.assertEqual(migrate(self.url), [])
        with psycopg.connect(self.url) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 2
            )
            conn.execute("ALTER TABLE owner_sessions RENAME TO owner_sessions_hidden")
        try:
            from backend.core.errors import ApplicationError

            auth = OwnerAuth("synthetic key", PostgresOwnerSessionRepository(self.url))
            with self.assertRaises(ApplicationError) as caught:
                auth.login("synthetic key")
            self.assertEqual(caught.exception.status, 503)
        finally:
            with psycopg.connect(self.url) as conn:
                conn.execute(
                    "ALTER TABLE owner_sessions_hidden RENAME TO owner_sessions"
                )
