"""Shared ephemeral Postgres fixture for tests that exercise the hybrid
index (scripts/build_hybrid_index.py, ai/search.py, ai/categories.py,
ai/retrieval.py). One container is meant to be started per test module
(setUpModule/tearDownModule) and reset between individual tests (reset()) —
starting a container per test is too slow to be practical."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from testcontainers.postgres import PostgresContainer

from backend.ai import db as db_module


class PostgresFixture:
    def __init__(self) -> None:
        self._container: PostgresContainer | None = None
        self._patch: mock._patch | None = None

    # Start a pgvector-enabled container and point backend.ai.db at it.
    def start(self) -> None:
        self._container = PostgresContainer("pgvector/pgvector:pg16", driver=None)
        self._container.start()
        # db_module._pool is a process-wide global. If anything already
        # called get_pool() with the real settings before this fixture ran
        # (e.g. importing backend.web.main, whose module-level
        # code builds a Retriever() against the real database), that pool is
        # already cached — patching `settings` alone would NOT stop it from
        # being reused, silently pointing every "isolated" test write at the
        # real production database. Force a fresh pool after patching.
        db_module.close_pool()
        self._patch = mock.patch.object(
            db_module, "settings", SimpleNamespace(database_url=self._container.get_connection_url())
        )
        self._patch.start()
        db_module.close_pool()
        db_module.ensure_schema()

    # Stop the container and undo the settings patch.
    def stop(self) -> None:
        db_module.close_pool()
        if self._patch is not None:
            self._patch.stop()
        if self._container is not None:
            self._container.stop()

    # Empty every table between tests without tearing down the container.
    def reset(self) -> None:
        with db_module.get_pool().connection() as connection:
            connection.execute("TRUNCATE TABLE chunks, documents, sync_metadata RESTART IDENTITY CASCADE")
            connection.commit()
