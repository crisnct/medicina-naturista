"""Actual PostgreSQL DISTINCT, aliases and literal ILIKE matching in an isolated DB."""

from __future__ import annotations

import pytest

from backend.ai import db
from backend.ai.embedding_model import get_profile
from backend.ai.herb_association_classification import relation_id, semantic_config
from backend.ai.herb_association_rules import Decision, content_hash
from backend.ai.herb_conditions import literal_pattern, lookup_herb_conditions
from backend.ai.herb_evidence import lookup_herb_evidence
from backend.ai.herb_index_catalog import read_index_catalogs
from backend.ai.herb_positive_repository import PositiveRepository
from backend.ai.herb_ranking import list_top_herbs
from backend.ai.herb_repository import HERBS_INDEX_VERSION
from backend.ai.index_constants import TEXT_REPR_VERSION
from backend.ai.index_state import IndexUnavailable, dictionary_snapshot, passage_profile
from backend.config import Settings
from backend.core.errors import ApplicationError
from tests.support.postgres import PostgresFixture


@pytest.fixture(scope="module")
def postgres():
    fixture = PostgresFixture()
    fixture.start()
    fixture.snapshot_herbs()
    try:
        yield fixture
    finally:
        try:
            fixture.restore_herbs()
        finally:
            fixture.stop()


@pytest.fixture
def catalog(postgres):
    postgres.reset()
    with db.get_pool().connection() as connection:
        connection.execute("TRUNCATE herbs RESTART IDENTITY CASCADE")
        connection.execute("""
            INSERT INTO herbs(category,family,latin,ro,en) VALUES
            ('plante medicinale','asteraceae','matricaria chamomilla','musetel','chamomile'),
            ('plante medicinale','asteraceae','chamaemelum nobile','musetel','roman chamomile'),
            ('plante medicinale','lamiaceae','mentha aquatica','menta de apa','water mint'),
            ('plante medicinale','testaceae','testus percentus','planta %_speciala','')
        """)
        connection.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (1,'romanita','ro_regional')"
        )
        connection.execute("""
            INSERT INTO herbs_benefits(herb_id,medical_condition_id)
            SELECT h.id,mc.id FROM herbs h CROSS JOIN medical_conditions mc WHERE h.id IN (1,2)
        """)
        *_, conditions_fingerprint, herbs_fingerprint = read_index_catalogs(connection)
        metadata = {
            "herbs_benefits_index_version": str(HERBS_INDEX_VERSION),
            "herbs_benefits_chunks_generation": "synthetic",
            "index_generation": "synthetic",
            "herbs_benefits_conditions_fingerprint": conditions_fingerprint,
            "herbs_benefits_herbs_fingerprint": herbs_fingerprint,
            "herbs_benefits_row_count": str(
                connection.execute("SELECT count(*) FROM herbs_benefits").fetchone()[0]
            ),
        }
        profile = get_profile("Qwen/Qwen3-Embedding-0.6B")
        from backend.ai.condition_repository import FINGERPRINT_VERSION

        metadata.update(
            model_name=profile.name,
            model_dimension=str(profile.dimension),
            dictionary_fingerprint=dictionary_snapshot(connection)[0],
            dictionary_fingerprint_version=str(FINGERPRINT_VERSION),
            passage_profile=passage_profile(profile),
            text_repr_version=TEXT_REPR_VERSION,
        )
        for key, value in metadata.items():
            connection.execute("INSERT INTO sync_metadata(key,value) VALUES(%s,%s)", (key, value))
        for condition in ("Vertigo", "Zorbita"):
            path = condition + ".md"
            text = f"# {condition}\n## Recomandari\n- matricaria chamomilla\n- chamaemelum nobile\n"
            digest = content_hash(text)
            connection.execute(
                "INSERT INTO documents(relative_path,absolute_path,size_bytes,modified_utc,sha256,encoding,line_count,char_count) VALUES(%s,%s,1,now(),%s,'utf-8',4,%s)",
                (path, path, digest, len(text)),
            )
            connection.execute(
                "INSERT INTO chunks(source_relative_path,source_absolute_path,source_sha256,line_start,line_end,heading,text,text_sha256,char_count,embedding,primary_medical_conditions,text_search) VALUES(%s,%s,%s,1,4,%s,%s,%s,%s,%s::vector,%s,''::tsvector)",
                (
                    path,
                    path,
                    digest,
                    condition,
                    text,
                    digest,
                    len(text),
                    "[" + ",".join(["0"] * profile.dimension) + "]",
                    [condition],
                ),
            )
    from uuid import uuid4

    repository = PositiveRepository()
    config = Settings()
    data = repository.read_snapshot()
    run_id = str(uuid4())
    repository.create_run(run_id, data, semantic_config(config), "c" * 64, False)
    repository.finish(
        run_id,
        data,
        {
            relation_id(work): Decision("positive", "rule", "synthetic_fixture")
            for work in data.works
        },
        {},
        {},
    )
    repository.publish(run_id, config, digest="c" * 64)


@pytest.mark.parametrize("name", ["romanita", "romaniței", "Matricaria chamomilla"])
def test_specific_species_with_name_and_alias_resolution(catalog, name):
    result = lookup_herb_conditions(name)
    assert result["status"] == "found" and result["entriesCount"] == 2
    assert [row["name"] for row in result["conditions"]] == ["Vertigo", "Zorbita"]
    assert result["species"] == ["matricaria chamomilla"]
    assert result["herbId"] == 1 and result["fragmentsCount"] == result["documentsCount"] == 2
    page = lookup_herb_evidence(result["herbId"], result["positiveRunId"])
    assert page["fragmentsCount"] == 2 and page["nextOffset"] is None
    assert len({item["chunkId"] for item in page["fragments"]}) == 2
    for fragment in page["fragments"]:
        assert fragment["text"].startswith("# ") and fragment["lineStart"] == 1
        assert fragment["lineEnd"] == 4
        assert any(span["kind"] == "herb" for span in fragment["textHighlights"])
        assert all(span["kind"] == "condition" for span in fragment["headingHighlights"])
    condition_id = result["conditions"][0]["id"]
    filtered = lookup_herb_evidence(1, result["positiveRunId"], condition_id=condition_id)
    assert filtered["fragmentsCount"] == 1
    assert filtered["fragments"][0]["conditions"] == [result["conditions"][0]]
    assert lookup_herb_evidence(1, result["positiveRunId"], offset=20)["fragments"] == []
    with pytest.raises(ApplicationError) as stale:
        lookup_herb_evidence(1, "00000000-0000-0000-0000-000000000000")
    assert stale.value.code == "HERB_EVIDENCE_STALE"
    # The existing synthetic flow also exercises a product's shared, paginated evidence.
    with db.get_pool().connection() as connection:
        product_id = connection.execute(
            "INSERT INTO herbs(category,family,latin,ro,en) "
            "VALUES('uleiuri',NULL,NULL,'ulei de primula','evening primrose oil') RETURNING id"
        ).fetchone()[0]
        for index in range(21):
            path = f"shared-{index:02}.md"
            text = (
                "# Vertigo\n## Recomandari\n🌿 romanita pentru ameteala.\n- ulei de primula\n"
                "# Zorbita\n## Recomandari\nmatricaria chamomilla pentru zorbitoza.\n- ulei de primula\n"
            )
            connection.execute(
                "INSERT INTO documents SELECT %s,%s,size_bytes,modified_utc,sha256,"
                "encoding,line_count,char_count FROM documents LIMIT 1",
                (path, path),
            )
            connection.execute(
                "INSERT INTO chunks(source_relative_path,source_absolute_path,source_sha256,"
                "line_start,line_end,heading,text,text_sha256,char_count,embedding,"
                "primary_medical_conditions,text_search) "
                "SELECT %s,%s,source_sha256,1,6,'Vertigo',%s,%s,%s,embedding,"
                "ARRAY['Vertigo','Zorbita'],text_search FROM chunks LIMIT 1",
                (path, path, text, content_hash(text), len(text)),
            )
    from uuid import uuid4

    repository = PositiveRepository()
    config = Settings()
    snapshot = repository.read_snapshot()
    next_run = str(uuid4())
    repository.create_run(next_run, snapshot, semantic_config(config), "c" * 64, False)
    repository.finish(
        next_run,
        snapshot,
        {
            relation_id(work): Decision("positive", "rule", "synthetic_fixture")
            for work in snapshot.works
        },
        {},
        {},
    )
    repository.publish(next_run, config, digest="c" * 64)
    first = lookup_herb_evidence(1, next_run)
    second = lookup_herb_evidence(1, next_run, offset=first["nextOffset"])
    assert first["fragmentsCount"] == first["documentsCount"] == 23
    assert len(first["fragments"]) == 20 and len(second["fragments"]) == 3
    assert second["nextOffset"] is None
    assert len({item["chunkId"] for item in first["fragments"] + second["fragments"]}) == 23
    shared = next(item for item in first["fragments"] if item["document"].startswith("shared-"))
    assert len(shared["conditions"]) == 2
    marked = [
        (span["kind"], shared["text"][span["start"] : span["end"]])
        for span in shared["textHighlights"]
    ]
    assert ("herb", "romanita") in marked and ("condition", "ameteala") in marked
    assert ("herb", "matricaria chamomilla") in marked and ("condition", "zorbitoza") in marked
    filtered = lookup_herb_evidence(1, next_run, condition_id=condition_id)
    assert filtered["fragmentsCount"] == 22
    assert any(len(item["conditions"]) == 2 for item in filtered["fragments"])
    product = lookup_herb_conditions("evening primrose oil")
    assert product["herbId"] == product_id and product["species"] == []
    assert product["fragmentsCount"] == 21
    product_page = lookup_herb_evidence(product_id, product["positiveRunId"])
    assert len(product_page["fragments"]) == 20
    assert any(span["kind"] == "herb" for span in product_page["fragments"][0]["textHighlights"])
    with pytest.raises(ApplicationError) as replaced:
        lookup_herb_evidence(1, result["positiveRunId"])
    assert replaced.value.code == "HERB_EVIDENCE_STALE"


@pytest.mark.parametrize("name", ["mușețel", "MUSETEL", "mușețelului"])
def test_common_name_shared_by_species_requires_selection(catalog, name):
    result = lookup_herb_conditions(name)
    assert result == {
        "status": "ambiguous",
        "choices": ["musetel (chamaemelum nobile)", "musetel (matricaria chamomilla)"],
    }


def test_zero_unknown_and_unpublished_index_are_distinct(catalog):
    assert lookup_herb_conditions("mentha aquatica")["entriesCount"] == 0
    assert lookup_herb_conditions("absent") == {"status": "not_found"}
    with db.get_pool().connection() as connection:
        connection.execute("DELETE FROM sync_metadata")
    with pytest.raises(IndexUnavailable):
        lookup_herb_conditions("matricaria chamomilla")


def test_like_metacharacters_are_literal_and_query_is_parameterized(catalog):
    assert literal_pattern("a\\%_b") == "a\\\\\\%\\_b"
    result = lookup_herb_conditions("plantă %_specială")
    assert result["status"] == "found" and result["entriesCount"] == 0
    assert lookup_herb_conditions("mușețel' OR TRUE --") == {"status": "not_found"}


@pytest.mark.parametrize(
    "key,value",
    [
        ("herbs_benefits_index_version", "999"),
        ("herbs_benefits_row_count", "999"),
        ("herbs_benefits_chunks_generation", "old"),
        ("herbs_benefits_herbs_fingerprint", "old"),
        ("herbs_benefits_conditions_fingerprint", "old"),
    ],
)
def test_stale_association_metadata_never_becomes_zero_results(catalog, key, value):
    with db.get_pool().connection() as connection:
        connection.execute("UPDATE sync_metadata SET value=%s WHERE key=%s", (value, key))
    with pytest.raises(ApplicationError) as stale:
        lookup_herb_conditions("matricaria chamomilla")
    assert stale.value.code == "POSITIVE_RANKING_STALE"


def test_alias_ambiguity_requires_choice(catalog):
    with db.get_pool().connection() as connection:
        connection.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES(3,'romanita','ro_regional')"
        )
    assert lookup_herb_conditions("romaniță") == {
        "status": "ambiguous",
        "choices": ["menta de apa (mentha aquatica)", "musetel (matricaria chamomilla)"],
    }


def test_exact_romanian_name_does_not_hide_other_plants_sharing_the_alias(catalog):
    with db.get_pool().connection() as connection:
        connection.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES(3,'musetel','ro_regional')"
        )
        *_, _conditions_fingerprint, herbs_fingerprint = read_index_catalogs(connection)
        connection.execute(
            "UPDATE sync_metadata SET value=%s WHERE key='herbs_benefits_herbs_fingerprint'",
            (herbs_fingerprint,),
        )
    result = lookup_herb_conditions("musetel")
    assert result["status"] == "ambiguous" and len(result["choices"]) == 3


def test_selected_species_does_not_include_another_species_associations(catalog):
    from uuid import uuid4

    with db.get_pool().connection() as connection:
        connection.execute(
            "DELETE FROM herbs_benefits WHERE herb_id=2 AND medical_condition_id=(SELECT id FROM medical_conditions ORDER BY name LIMIT 1)"
        )
        connection.execute(
            "UPDATE sync_metadata SET value=(SELECT count(*)::text FROM herbs_benefits) WHERE key='herbs_benefits_row_count'"
        )
        condition_id = connection.execute(
            "SELECT id FROM medical_conditions ORDER BY name LIMIT 1"
        ).fetchone()[0]
    repository = PositiveRepository()
    config = Settings()
    data = repository.read_snapshot()
    run_id = str(uuid4())
    repository.create_run(run_id, data, semantic_config(config), "c" * 64, False)
    decisions = {
        relation_id(work): Decision(
            "caution"
            if work[1].herb_id == 2 and work[1].condition_id == condition_id
            else "positive",
            "rule",
            "synthetic_fixture",
        )
        for work in data.works
    }
    repository.finish(run_id, data, decisions, {}, {})
    repository.publish(run_id, config, digest="c" * 64)
    result = lookup_herb_conditions("chamaemelum nobile")
    assert result["entriesCount"] == 1 and result["species"] == ["chamaemelum nobile"]
    assert lookup_herb_conditions("matricaria chamomilla")["entriesCount"] == 2
    assert (
        next(row for row in list_top_herbs(10) if row["latin"] == "chamaemelum nobile")["ranking"]
        == result["entriesCount"]
    )
    page = lookup_herb_evidence(result["herbId"], result["positiveRunId"])
    assert page["fragmentsCount"] == 1
    assert all(
        condition["id"] != condition_id
        for item in page["fragments"]
        for condition in item["conditions"]
    )


def test_missing_table_is_index_unavailable(catalog):
    with db.get_pool().connection() as connection:
        connection.execute("ALTER TABLE herb_positive_pairs RENAME TO herb_positive_pairs_hidden")
    try:
        with pytest.raises(IndexUnavailable):
            lookup_herb_conditions("matricaria chamomilla")
    finally:
        with db.get_pool().connection() as connection:
            connection.execute(
                "ALTER TABLE herb_positive_pairs_hidden RENAME TO herb_positive_pairs"
            )


def test_top_limits_species_before_alias_join_and_orders_ties(catalog):
    import io
    from contextlib import redirect_stdout
    from unittest.mock import Mock, patch

    from backend.ai.embedding_model import get_profile
    from backend.ai.herb_positive_repository import PositiveRepository
    from backend.ai.index_constants import TEXT_REPR_VERSION
    from backend.ai.index_state import dictionary_snapshot, passage_profile
    from backend.config import Settings
    from backend.core.errors import ApplicationError
    from scripts.positive_herb_ranking import run_positive_ranking

    config = Settings()
    repository = PositiveRepository()
    with db.get_pool().connection() as connection:
        connection.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
        connection.execute("DELETE FROM sync_metadata")
        profile = get_profile("Qwen/Qwen3-Embedding-0.6B")
        metadata = {
            "model_name": profile.name,
            "model_dimension": str(profile.dimension),
            "dictionary_fingerprint": dictionary_snapshot(connection)[0],
            "dictionary_fingerprint_version": "1",
            "passage_profile": passage_profile(profile),
            "text_repr_version": TEXT_REPR_VERSION,
            "index_generation": "positive-synthetic",
        }
        from backend.ai.condition_repository import FINGERPRINT_VERSION

        metadata["dictionary_fingerprint_version"] = str(FINGERPRINT_VERSION)
        for key, value in metadata.items():
            connection.execute("INSERT INTO sync_metadata VALUES(%s,%s)", (key, value))
        connection.execute(
            "INSERT INTO herbs(category,family,latin,ro,en) VALUES ('fructe','testaceae','fructus primus','fruct sintetic unu','fruit one'),('fructe','testaceae','fructus secundus','fruct sintetic doi','fruit two'),('cereale','testaceae','cerealis fictiva','cereala sintetica','synthetic cereal')"
        )
        connection.execute(
            "UPDATE herbs SET ranking = CASE WHEN id=3 THEN 9 WHEN id IN (1,2) THEN 7 ELSE 0 END"
        )
        connection.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (3,'aquatic mint','en_alt'), (3,'menta de balta','ro_regional'), (3,'mentha sylvestris','latin_synonyms')"
        )
        sources = (
            (
                "positive.md",
                "Zorbita",
                "# Zorbita\n## Alimente recomandate\n- matricaria chamomilla\n- chamaemelum nobile\n- mentha aquatica\n- fruct sintetic unu\n- fruct sintetic doi\n- cereala sintetica\n",
            ),
            (
                "negative.md",
                "Zorbita",
                "# Zorbita\n## Contraindicatii\n- mentha aquatica\n- cereala sintetica\n",
            ),
            (
                "repeat.md",
                "Zorbita",
                "# Zorbita\nmatricaria chamomilla este mentionata. matricaria chamomilla apare iar.\n",
            ),
            ("ambiguous.md", "Zorbita", "# Zorbita\nmentha aquatica este mentionata.\n"),
        )
        for index, (path, condition, text) in enumerate(sources, 1):
            connection.execute(
                "INSERT INTO documents(relative_path,absolute_path,size_bytes,modified_utc,sha256,encoding,line_count,char_count) VALUES(%s,%s,1,now(),%s,'utf-8',1,%s)",
                (path, path, str(index), len(text)),
            )
            connection.execute(
                "INSERT INTO chunks(source_relative_path,source_absolute_path,source_sha256,line_start,line_end,heading,text,text_sha256,char_count,embedding,primary_medical_conditions,text_search) VALUES(%s,%s,%s,1,1,%s,%s,%s,%s,%s::vector,%s,''::tsvector)",
                (
                    path,
                    path,
                    str(index),
                    condition,
                    text,
                    str(index),
                    len(text),
                    "[" + ",".join(["0"] * profile.dimension) + "]",
                    [condition],
                ),
            )

    with pytest.raises(ApplicationError) as not_ready:
        list_top_herbs(20)
    assert not_ready.value.code == "POSITIVE_RANKING_NOT_READY"
    before = repository.read_snapshot().manifest
    with db.get_pool().connection() as connection:
        historical = connection.execute(
            "SELECT id,ranking,xmin::text FROM herbs ORDER BY id"
        ).fetchall()
        pairs = connection.execute("SELECT * FROM herbs_benefits ORDER BY 1,2").fetchall()

    client = Mock()

    def classify_source(_system, user, _tokens):
        import json

        payload = json.loads(user)
        if any(c["herb_id"] == 1 for c in payload["candidates"]):
            assert len(next(c["mentions"] for c in payload["candidates"] if c["herb_id"] == 1)) == 2
        return {
            "relations": {
                c["id"]: {
                    "local_condition": c["condition"],
                    "recommendation": c["herb_id"] == 3,
                    "prohibition": c["herb_id"] == 3,
                }
                for c in payload["candidates"]
            }
        }

    client.complete_json.side_effect = classify_source
    with (
        patch("scripts.positive_herb_ranking.model_digest", return_value="a" * 64),
        patch("scripts.positive_herb_ranking.make_client", return_value=client),
        redirect_stdout(io.StringIO()),
    ):
        analyzed = run_positive_ranking(config, analyze=True)
        assert analyzed["batches"] == 1 and analyzed["requests"] == 0
        client.complete_json.assert_not_called()
        first = run_positive_ranking(config)
        assert first["status"] == "ready" and first["requests"] == 1
        with pytest.raises(ApplicationError):
            list_top_herbs(300)
        second = run_positive_ranking(config)
        assert second["requests"] == 0 and second["cache_hits"] == 3
        assert run_positive_ranking(config, resume=first["run_id"])["status"] == "ready"
        run_positive_ranking(config, publish=first["run_id"])
        with pytest.raises(ValueError, match="POSITIVE_PUBLICATION_CONFLICT"):
            run_positive_ranking(config, publish=second["run_id"])
        assert run_positive_ranking(config, publish=first["run_id"])["status"] == "published"
        assert run_positive_ranking(config, analyze=True)["batches"] == 0
    assert client.complete_json.call_count == 1
    from backend.ai.herb_caution_repository import CautionRepository

    warnings = lookup_herb_conditions("mentha aquatica")
    assert warnings["contraindicationsCount"] == 1
    assert warnings["contraindications"][0]["hasRecommendation"]
    negative_page = lookup_herb_evidence(
        warnings["herbId"],
        warnings["positiveRunId"],
        evidence_kind="contraindication",
        caution_run_id=warnings["cautionRunId"],
    )
    assert {fragment["document"] for fragment in negative_page["fragments"]} == {
        "negative.md",
    }
    with db.get_pool().connection() as connection:
        assert connection.execute(
            "SELECT DISTINCT e.warning_kind FROM herb_caution_evidence e JOIN chunks c USING(chunk_id) "
            "WHERE e.run_id=%s AND c.source_relative_path='ambiguous.md'",
            (warnings["cautionRunId"],),
        ).fetchall() == [("unknown",)]
    caution_repository = CautionRepository()
    replay = caution_repository.prepare(warnings["positiveRunId"], config)
    caution_repository.publish(replay["run_id"], config)
    assert replay["ai_requests_sent_total"] == 0
    assert client.complete_json.call_count == 1
    assert lookup_herb_conditions("mentha aquatica")["contraindicationsCount"] == 1
    with pytest.raises(ApplicationError) as stale_warning:
        lookup_herb_evidence(
            warnings["herbId"],
            warnings["positiveRunId"],
            evidence_kind="contraindication",
            caution_run_id=warnings["cautionRunId"],
        )
    assert stale_warning.value.code == "HERB_EVIDENCE_STALE"
    with db.get_pool().connection() as connection:
        connection.execute("DELETE FROM herb_caution_cache")
    historical_replay = caution_repository.prepare(warnings["positiveRunId"], config)
    caution_repository.publish(historical_replay["run_id"], config)
    recovered = lookup_herb_conditions("mentha aquatica")
    assert recovered["contraindicationsCount"] == 1
    assert recovered["contraindicationsStatus"] == "partial"
    assert historical_replay["ai_requests_sent_total"] == 0
    assert client.complete_json.call_count == 1
    from dataclasses import replace

    attempts = []

    def fail_second(system, user, tokens):
        attempts.append(user)
        if len(attempts) == 2:
            raise TimeoutError("synthetic timeout")
        return classify_source(system, user, tokens)

    failing_client = Mock()
    failing_client.complete_json.side_effect = fail_second
    bounded = replace(config, herb_association_ai_max_pairs=1, herb_association_ai_max_requests=2)
    with (
        patch("scripts.positive_herb_ranking.model_digest", return_value="b" * 64),
        patch("scripts.positive_herb_ranking.make_client", return_value=failing_client),
        redirect_stdout(io.StringIO()),
    ):
        with pytest.raises(TimeoutError):
            run_positive_ranking(bounded)
        with db.get_pool().connection() as connection:
            failed_run = str(
                connection.execute(
                    "SELECT run_id FROM herb_positive_runs WHERE model_digest=%s ORDER BY created_at DESC LIMIT 1",
                    ("b" * 64,),
                ).fetchone()[0]
            )
            assert (
                connection.execute(
                    "SELECT status FROM herb_positive_runs WHERE run_id=%s", (failed_run,)
                ).fetchone()[0]
                == "preparing"
            )
        assert len(list_top_herbs(300)) == 4
        failing_client.complete_json.side_effect = classify_source
        with pytest.raises(ValueError, match="POSITIVE_REQUEST_LIMIT"):
            run_positive_ranking(bounded, resume=failed_run)
        assert failing_client.complete_json.call_count == 2
        resumed = run_positive_ranking(
            replace(bounded, herb_association_ai_max_requests=3), resume=failed_run
        )
        assert resumed["requests"] == 1 and resumed["cache_hits"] == 2
        assert failing_client.complete_json.call_count == 3
    assert len(list_top_herbs(300)) == 4
    assert [row["latin"] for row in list_top_herbs(2)] == [
        "matricaria chamomilla",
        "chamaemelum nobile",
    ]
    assert all(row["ranking"] == 1 for row in list_top_herbs(300))
    assert len(list_top_herbs(100, "fructe")) == 2
    assert list_top_herbs(100, "cereale") == []
    assert list_top_herbs(100, "seminte") == []
    assert lookup_herb_conditions("matricaria chamomilla")["entriesCount"] == 1
    assert lookup_herb_conditions("mentha aquatica")["entriesCount"] == 0
    assert lookup_herb_conditions("cereala sintetica")["conditions"] == []
    positive = lookup_herb_conditions("matricaria chamomilla")
    page = lookup_herb_evidence(positive["herbId"], positive["positiveRunId"])
    assert page["fragmentsCount"] == 1
    assert [item["document"] for item in page["fragments"]] == ["positive.md"]
    mixed = lookup_herb_conditions("mentha aquatica")
    assert lookup_herb_evidence(mixed["herbId"], mixed["positiveRunId"])["fragments"] == []
    fruit = lookup_herb_conditions("fruct sintetic unu")
    assert lookup_herb_evidence(fruit["herbId"], fruit["positiveRunId"])["fragmentsCount"] == 1
    assert repository.read_snapshot().manifest == before
    with db.get_pool().connection() as connection:
        assert (
            connection.execute("SELECT id,ranking,xmin::text FROM herbs ORDER BY id").fetchall()
            == historical
        )
        assert connection.execute("SELECT * FROM herbs_benefits ORDER BY 1,2").fetchall() == pairs
        assert (
            connection.execute(
                "SELECT state FROM herb_positive_pairs WHERE run_id=%s AND herb_id=3",
                (first["run_id"],),
            ).fetchone()[0]
            == "mixed"
        )
        assert (
            connection.execute(
                "SELECT ranking FROM herb_positive_rankings WHERE run_id=%s AND herb_id=4",
                (first["run_id"],),
            ).fetchone()[0]
            == 0
        )
        connection.execute(
            "UPDATE herb_positive_rankings SET ranking=77 WHERE run_id=%s AND herb_id=1",
            (first["run_id"],),
        )
    with pytest.raises(ValueError, match="POSITIVE_AGGREGATION_MISMATCH"):
        repository.publish(first["run_id"], config, digest="a" * 64)
    with pytest.raises(ApplicationError) as invalid_top:
        list_top_herbs(20)
    assert invalid_top.value.code == "POSITIVE_RANKING_STALE"
    with pytest.raises(ApplicationError) as invalid_details:
        lookup_herb_conditions("matricaria chamomilla")
    assert invalid_details.value.code == "POSITIVE_RANKING_STALE"
    with db.get_pool().connection() as connection:
        connection.execute(
            "UPDATE herb_positive_rankings SET ranking=1 WHERE run_id=%s AND herb_id=1",
            (first["run_id"],),
        )
        connection.execute(
            "UPDATE chunks SET heading='changed' WHERE source_relative_path='positive.md'"
        )
    with pytest.raises(ApplicationError) as stale:
        repository.publish(second["run_id"], config, digest="a" * 64)
    assert stale.value.code == "POSITIVE_RANKING_STALE"
    with pytest.raises(ApplicationError) as stale_top:
        list_top_herbs(20)
    assert stale_top.value.code == "POSITIVE_RANKING_STALE"
    with db.get_pool().connection() as connection:
        assert (
            connection.execute(
                "SELECT value FROM sync_metadata WHERE key='herb_positive_active_run'"
            ).fetchone()[0]
            == first["run_id"]
        )
