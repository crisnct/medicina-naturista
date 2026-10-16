"""Real metrics transactions against disposable PostgreSQL only."""

from dataclasses import replace
from types import SimpleNamespace

import psycopg
import pytest

from backend.ai import db
from backend.core.report_metrics import ReportMetrics
from backend.persistence.report_metrics import PostgresReportMetricsRepository
from scripts.migrate_database import MIGRATIONS, migrate
from tests.support.postgres import PostgresFixture
from tests.unit.web import test_web as support


@pytest.fixture(scope="module")
def database():
    fixture = PostgresFixture()
    fixture.start()
    try:
        with db.get_pool().connection() as conn:
            conn.execute("TRUNCATE report_generation_metrics RESTART IDENTITY")
            conn.execute((MIGRATIONS / "012_seed_report_generation_metrics.sql").read_text())
        yield fixture._container.get_connection_url()
    finally:
        fixture.stop()


def test_migrations_seed_exact_measurements_once(database):
    expected = [
        ("ollama-gemma4:12b", "medium", 300000),
        ("ollama-qwen3.5:4b", "medium", 300000),
        ("ollama-qwen3.5:9b", "medium", 600000),
        ("ollama-ministral-3:8b", "medium", 1020000),
        ("deepseek-flash", "low", 180000),
        ("grok-4.3", "medium", 40000),
    ]
    assert migrate(database) == []
    with psycopg.connect(database) as conn:
        rows = conn.execute(
            "SELECT medical_condition, min_score, characters, ai_model, ai_effort, duration "
            "FROM report_generation_metrics WHERE medical_condition = 'Gripa' ORDER BY id"
        ).fetchall()
        assert rows == [("Gripa", 50, 53924, *entry) for entry in expected]


def test_repository_preserves_unicode_allows_repeated_generations_and_restores_timeout(database):
    repository = PostgresReportMetricsRepository(db.get_pool)
    metrics = ReportMetrics("Gripă, răceală", 50, 53924, "ollama-gemma4:12b", None, 40000)
    with db.get_pool().connection() as conn:
        previous_timeout = conn.execute("SHOW statement_timeout").fetchone()[0]
    first, second = repository(metrics), repository(metrics)
    assert second > first
    with db.get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT medical_condition, min_score, characters, ai_model, ai_effort, duration "
            "FROM report_generation_metrics WHERE id IN (%s, %s) ORDER BY id",
            (first, second),
        ).fetchall()
        assert rows == [("Gripă, răceală", 50, 53924, "ollama-gemma4:12b", None, 40000)] * 2
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == previous_timeout


def test_table_lock_has_bounded_wait_and_pool_remains_usable(database):
    repository = PostgresReportMetricsRepository(db.get_pool)
    metrics = ReportMetrics("Lock test", 0, 0, "grok-4.3", "medium", 0)
    with psycopg.connect(database) as blocker:
        blocker.execute("LOCK TABLE report_generation_metrics IN ACCESS EXCLUSIVE MODE")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            repository(metrics)
    assert repository(replace(metrics, medical_condition="After lock")) > 0
    with db.get_pool().connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM report_generation_metrics WHERE medical_condition = 'Lock test'"
            ).fetchone()[0]
            == 0
        )


def test_background_publication_inserts_real_measurement_once(database):
    test = support.WebTests()
    test.setUp()
    try:
        test.deps.record_report_metrics = PostgresReportMetricsRepository(db.get_pool)
        test.deps.ai.provider = SimpleNamespace(model="gemma4:12b", reasoning_effort="medium")
        sid, tab = "D" * 43, "database-tab01"
        headers = support._headers(sid, tab, True)
        test.client.get("/api/session", headers=headers)
        messages = support._send(test.client, sid, tab, "Gripa", [])
        search = support._by_kind(messages, "generate")["searchId"]
        with db.get_pool().connection() as conn:
            previous_id = conn.execute("SELECT max(id) FROM report_generation_metrics").fetchone()[
                0
            ]
        options = {"model": "ollama-gemma4:12b", "minScore": 0, "requestId": "real-db-request01"}
        url = f"/api/searches/{search}/generate"
        first = support.post_report(test.client, url, json=options, headers=headers)
        assert first.json()["state"] == "succeeded"
        repeated = support.post_report(test.client, url, json=options, headers=headers)
        assert repeated.json()["jobId"] == first.json()["jobId"]
        with db.get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT medical_condition, min_score, characters, ai_model, ai_effort, duration "
                "FROM report_generation_metrics WHERE id > %s",
                (previous_id,),
            ).fetchall()
        assert len(rows) == 1
        expected_characters = sum(
            len(item["text"])
            for item in test.deps.store.get(sid, tab).searches[search].evidence.values()
        )
        assert rows[0][:5] == ("Gripa", 0, expected_characters, "ollama-gemma4:12b", "medium")
        assert rows[0][5] >= 0
        download = support._by_kind(first.json()["messages"], "download")
        assert test.client.get(download["url"], headers=headers).status_code == 200
    finally:
        test.doCleanups()
