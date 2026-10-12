"""Failure injection and actual PostgreSQL advisory-lock semantics."""

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, redirect_stdout
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import psycopg
import pytest

from backend.ai import db, index_constants, index_state
from backend.ai.embedding_model import PROFILES, EmbeddingProfile
from backend.ai.retrieval import Retriever
from backend.ai.search import SearchSignals, rank
from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.models import HealthProfile
from scripts import build_hybrid_index as builder
from tests.support.conditions import conditions_from_rows, replace_catalog
from tests.support.postgres import PostgresFixture


@pytest.fixture(scope="module", autouse=True)
def postgres():
    fixture = PostgresFixture()
    fixture.start()
    yield fixture
    fixture.stop()


@pytest.fixture
def corpus(tmp_path, postgres):
    postgres.reset()
    source = tmp_path / "documents"
    source.mkdir()
    (source / "A").mkdir()
    (source / "A" / "a.md").write_text("# Zorbita\nText sintetic.", encoding="utf-8")
    config = replace(Settings(), model_cache_dir=tmp_path / "models")
    with (
        patch.object(builder, "settings", config),
        patch.object(
            builder,
            "GPUUsageMonitor",
            return_value=nullcontext(SimpleNamespace(percent=lambda: "N/A")),
        ),
    ):
        yield source, postgres


def sync(source, model=builder.DEFAULT_MODEL):
    def embeddings(_model, chunks, _batch, profile, **_kwargs):
        vectors = np.ones((len(chunks), profile.dimension), dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    with (
        patch.object(builder, "create_embedding_model", return_value=object()),
        patch.object(builder, "embed_chunks", side_effect=embeddings),
        redirect_stdout(io.StringIO()),
    ):
        builder.build(source, model)


def test_shared_text_version_rejects_old_index_and_rebuilds_unchanged_source(corpus):
    source, _postgres = corpus
    sync(source)
    before = snapshot()
    # Both imported modules must use the same source of truth.
    with patch.object(index_constants, "TEXT_REPR_VERSION", "11"):
        with pytest.raises(index_state.IndexUnavailable) as error:
            with index_state.index_reader():
                pass
        assert error.value.code == "INDEX_RESYNC_REQUIRED"

        sync(source)
        with index_state.index_reader() as (_connection, metadata):
            assert metadata.text_repr_version == "11"
        after = snapshot()
        assert after[1][0][0] != before[1][0][0]
        assert dict(after[2])["text_repr_version"] == "11"


def snapshot():
    with db.get_pool().connection() as connection:
        return (
            connection.execute("SELECT * FROM documents ORDER BY relative_path").fetchall(),
            connection.execute(
                "SELECT chunk_id, text, embedding::text, primary_medical_conditions FROM chunks ORDER BY chunk_id"
            ).fetchall(),
            connection.execute("SELECT * FROM sync_metadata ORDER BY key").fetchall(),
            db._embedding_dimension(connection),
        )


@pytest.mark.parametrize("stage", ["model", "embedding", "document", "dimension", "metadata"])
def test_every_failure_preserves_previous_generation(corpus, stage):
    source, _dictionary = corpus
    sync(source)
    before = snapshot()
    (source / "A" / "a.md").write_text("# Zorbita\nText schimbat.", encoding="utf-8")
    other = EmbeddingProfile("test/integrity", 32, "{text}", "{text}", 1400, 240)
    original_write = builder._write_document

    def failed_write(*args):
        original_write(*args)
        raise RuntimeError("injected document failure")

    original_execute = psycopg.Connection.execute

    def failed_execute(connection, query, *args, **kwargs):
        result = original_execute(connection, query, *args, **kwargs)
        if (stage == "dimension" and str(query).startswith("ALTER TABLE chunks ADD")) or (
            stage == "metadata" and str(query).startswith("INSERT INTO sync_metadata")
        ):
            raise RuntimeError("injected publication failure")
        return result

    with patch.dict(PROFILES, {other.name: other}):
        if stage in {"dimension", "metadata"}:
            with (
                patch.object(psycopg.Connection, "execute", failed_execute),
                pytest.raises(RuntimeError),
            ):
                sync(source, other.name if stage == "dimension" else builder.DEFAULT_MODEL)
        elif stage == "document":
            with (
                patch.object(builder, "_write_document", side_effect=failed_write),
                pytest.raises(RuntimeError),
            ):
                sync(source)
        else:
            with (
                patch.object(
                    builder,
                    "create_embedding_model",
                    side_effect=RuntimeError("model failure") if stage == "model" else None,
                ),
                patch.object(
                    builder, "embed_chunks", side_effect=RuntimeError("embedding failure")
                ),
                pytest.raises(RuntimeError),
            ):
                builder.build(source, builder.DEFAULT_MODEL)
    assert snapshot() == before
    with index_state.index_reader():
        pass


def test_dictionary_only_change_rebuilds_and_missing_fingerprint_rebuilds(corpus):
    source, _postgres = corpus
    sync(source)
    before = snapshot()
    with db.get_pool().connection() as connection:
        replace_catalog(connection, conditions_from_rows("Noua,Zorbita\n"))
    with pytest.raises(index_state.IndexUnavailable) as error:
        with index_state.index_reader():
            pass
    assert error.value.code == "INDEX_RESYNC_REQUIRED"
    sync(source)
    after = snapshot()
    assert after[1][0][3] == ["Noua"]
    assert after[1][0][0] != before[1][0][0]
    with db.get_pool().connection() as connection:
        connection.execute("DELETE FROM sync_metadata WHERE key='dictionary_fingerprint'")
    sync(source)
    assert snapshot()[1][0][0] != after[1][0][0]


def test_dictionary_change_during_calculation_aborts_publication(corpus):
    source, _postgres = corpus
    sync(source)
    before = snapshot()
    (source / "A" / "a.md").write_text("# Zorbita\nModificat.", encoding="utf-8")

    def changed(*args, **kwargs):
        return np.ones((len(args[1]), args[3].dimension), dtype=np.float32)

    with (
        patch.object(builder, "create_embedding_model", return_value=object()),
        patch.object(builder, "embed_chunks", side_effect=changed),
        patch.object(
            builder,
            "dictionary_snapshot",
            side_effect=[index_state.dictionary_snapshot(), ("changed", None)],
        ),
        pytest.raises(RuntimeError, match="DICTIONARY_CHANGED"),
    ):
        builder.build(source, builder.DEFAULT_MODEL)
    assert snapshot() == before


def test_reader_finishes_before_writer_and_new_readers_refuse_maintenance(corpus):
    sync(corpus[0])
    entered = threading.Event()
    release = threading.Event()

    def writer():
        with index_state.index_writer():
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as workers:
        with index_state.index_reader():
            future = workers.submit(writer)
            assert not entered.wait(0.1)
        assert entered.wait(5)
        try:
            with pytest.raises(index_state.IndexUnavailable):
                with index_state.index_reader():
                    pass
        finally:
            release.set()
        future.result(timeout=5)
    with index_state.index_reader():
        pass


def test_writers_serialize_and_connection_loss_releases_lock(corpus):
    sync(corpus[0])
    entered = threading.Event()

    def second():
        with index_state.index_writer():
            entered.set()

    with ThreadPoolExecutor(max_workers=1) as workers:
        with index_state.index_writer():
            future = workers.submit(second)
            assert not entered.wait(0.1)
        future.result(timeout=5)
        assert entered.is_set()
    with index_state.index_writer() as connection:
        pid = connection.execute("SELECT pg_backend_pid()").fetchone()[0]
        with psycopg.connect(db.settings.database_url, autocommit=True) as killer:
            killer.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with pytest.raises(psycopg.OperationalError):
            connection.execute("SELECT 1")
    with index_state.index_reader():
        pass


def test_empty_none_mixed_stale_and_cache_generation(corpus):
    source, _dictionary = corpus
    sync(source)
    retriever = Retriever(source)
    signals = SearchSignals(False, True, False)
    assert rank("Text", frozenset(), signals=signals) == []
    assert rank("Text", None, signals=signals)
    session = SimpleNamespace(
        profile=HealthProfile(health_problem="Text"),
        selected_categories={"A", "old"},
        search_signals=signals,
    )
    evidence = retriever.collect(session)
    assert evidence.removed_category_ids == ["old"]
    tree, generation = retriever.categories_snapshot()
    assert tree.nodes[tree.root_id].total_documents == 1
    session.selected_categories = {"old"}
    with pytest.raises(ApplicationError) as error:
        retriever.collect(session)
    assert error.value.code == "CATEGORY_SELECTION_STALE" and error.value.status == 409
    session.selected_categories = set()
    assert retriever.collect(session) == {}
    (source / "B").mkdir()
    (source / "B" / "b.md").write_text("Text nou.", encoding="utf-8")
    sync(source)
    tree, new_generation = retriever.categories_snapshot()
    assert generation != new_generation
    assert tree.nodes[tree.root_id].total_documents == 2
    assert retriever.document_count == 2


def test_http_maintenance_keeps_snapshot_generation_and_download_available(corpus):
    from tests.unit.web import test_web as support

    source, _dictionary = corpus
    sync(source)
    test = support.WebTests()
    test.setUp()
    sid, tab = "J" * 43, "maintenance-tab"
    try:
        test.client.get("/api/session", headers=support._headers(sid, tab))
        messages = support._send(test.client, sid, tab, "Text", [])
        search = support._by_kind(messages, "generate")["searchId"]
        with (
            patch.object(test.deps, "retriever", Retriever(source)),
            patch.object(test.deps.ai, "is_configured", return_value=True, create=True),
        ):
            with index_state.index_writer():
                for route in ("/api/categories", "/readyz"):
                    response = test.client.get(route, headers=support._headers(sid, tab))
                    assert response.status_code == 503
                    assert response.headers["Retry-After"] == "60"
                unavailable = test.client.post("/api/search", headers=support._headers(sid, tab))
                assert unavailable.status_code == 503
                assert unavailable.headers["Retry-After"] == "60"
                response = test.client.post(
                    f"/api/searches/{search}/generate", headers=support._headers(sid, tab, True)
                )
                assert response.status_code == 200
                download = support._by_kind(response.json()["messages"], "download")
                response = test.client.get(download["url"], headers=support._headers(sid, tab))
                assert response.status_code == 200 and response.content.startswith(b"%PDF")
            messages = support._send(
                test.client,
                sid,
                tab,
                "Text",
                ["A"],
                {"conditions": False, "lexical": True, "semantic": False},
            )
            fragments = support._by_kind(messages, "fragments")
            assert fragments["indexGeneration"]
            session = test.deps.store.get(sid, tab)
            stored = session.searches[fragments["searchId"]]
            assert type(stored.evidence) is dict
            assert stored.index_generation == fragments["indexGeneration"]
            from backend.core.models import CommitChange

            operation = test.deps.store.begin_operation(session, "message")
            try:
                test.deps.store.commit_operation(
                    operation,
                    CommitChange(
                        selected_categories={"old"},
                        search_signals=SearchSignals(True, False, False),
                    ),
                )
            finally:
                test.deps.store.finish_operation(operation)
            stale = test.client.post("/api/search", headers=support._headers(sid, tab))
            assert (
                stale.status_code == 409
                and stale.json()["detail"]["code"] == "CATEGORY_SELECTION_STALE"
            )
    finally:
        test.doCleanups()
