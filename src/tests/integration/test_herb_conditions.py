"""Actual PostgreSQL DISTINCT, aliases and literal ILIKE matching in an isolated DB."""

import pytest

from backend.ai import db
from backend.ai.herb_conditions import literal_pattern, lookup_herb_conditions
from backend.ai.herb_index_catalog import read_index_catalogs
from backend.ai.herb_ranking import list_top_herbs
from backend.ai.herb_repository import HERBS_INDEX_VERSION
from backend.ai.index_state import IndexUnavailable
from tests.support.postgres import PostgresFixture


@pytest.fixture(scope="module")
def postgres():
    fixture = PostgresFixture()
    fixture.start()
    try:
        yield fixture
    finally:
        fixture.stop()


@pytest.fixture
def catalog(postgres):
    postgres.reset()
    with db.get_pool().connection() as connection:
        connection.execute("TRUNCATE herbs RESTART IDENTITY CASCADE")
        connection.execute("""
            INSERT INTO herbs(family,latin,ro,en) VALUES
            ('asteraceae','matricaria chamomilla','musetel','chamomile'),
            ('asteraceae','chamaemelum nobile','musetel','roman chamomile'),
            ('lamiaceae','mentha aquatica','menta de apa','water mint'),
            ('testaceae','testus percentus','planta %_speciala','')
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
        for key, value in metadata.items():
            connection.execute("INSERT INTO sync_metadata(key,value) VALUES(%s,%s)", (key, value))


@pytest.mark.parametrize("name", ["romanita", "romaniței", "Matricaria chamomilla"])
def test_specific_species_with_name_and_alias_resolution(catalog, name):
    result = lookup_herb_conditions(name)
    assert result["status"] == "found" and result["entriesCount"] == 2
    assert [row["name"] for row in result["conditions"]] == ["Vertigo", "Zorbita"]
    assert result["species"] == ["matricaria chamomilla"]


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
    with pytest.raises(IndexUnavailable):
        lookup_herb_conditions("matricaria chamomilla")


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
    with db.get_pool().connection() as connection:
        connection.execute(
            "DELETE FROM herbs_benefits WHERE herb_id=2 AND medical_condition_id=(SELECT id FROM medical_conditions ORDER BY name LIMIT 1)"
        )
        connection.execute(
            "UPDATE sync_metadata SET value=(SELECT count(*)::text FROM herbs_benefits) WHERE key='herbs_benefits_row_count'"
        )
    result = lookup_herb_conditions("chamaemelum nobile")
    assert result["entriesCount"] == 1 and result["species"] == ["chamaemelum nobile"]


def test_missing_table_is_index_unavailable(catalog):
    with db.get_pool().connection() as connection:
        connection.execute("ALTER TABLE herbs_benefits RENAME TO herbs_benefits_hidden")
    try:
        with pytest.raises(IndexUnavailable):
            lookup_herb_conditions("matricaria chamomilla")
    finally:
        with db.get_pool().connection() as connection:
            connection.execute("ALTER TABLE herbs_benefits_hidden RENAME TO herbs_benefits")


def test_top_limits_species_before_alias_join_and_orders_ties(catalog):
    with db.get_pool().connection() as connection:
        connection.execute(
            "UPDATE herbs SET ranking = CASE WHEN id=3 THEN 9 WHEN id IN (1,2) THEN 7 ELSE 0 END"
        )
        connection.execute(
            "INSERT INTO herb_aliases(herb_id,name,kind) VALUES (3,'water mint','en_alt'), (3,'menta de balta','ro_regional'), (3,'iz ma','latin_synonyms')"
        )
    assert list_top_herbs(2) == [
        {"ro": "menta de apa", "ro_regional": ["menta de balta"], "ranking": 9},
        {"ro": "mușețel", "ro_regional": ["romanita"], "ranking": 7},
    ]
    assert len(list_top_herbs(100)) == 4
    assert list_top_herbs(3)[2] == {"ro": "mușețel", "ro_regional": [], "ranking": 7}
