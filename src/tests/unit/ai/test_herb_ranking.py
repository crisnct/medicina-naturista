from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.ai import herb_display
from backend.ai.herb_display import romanian_herb_name
from backend.ai.herb_ranking import list_top_herbs
from backend.ai.index_state import IndexUnavailable


@pytest.mark.parametrize(
    "name,expected",
    [
        ("coada-soricelului", "coada-șoricelului"),
        ("musetel", "mușețel"),
        ("patlagele rosii", "pătlăgele roșii"),
        ("in", "in"),
        ("soc", "soc"),
        ("romaniță", "romaniță"),
        ("plantus unknownus", "plantus unknownus"),
    ],
)
def test_display_preserves_names_and_restores_known_accents(name, expected):
    with patch.object(
        herb_display,
        "_dictionary",
        return_value={
            "coada": {"coada", "coadă"},
            "soricelului": {"șoricelului"},
            "musetel": {"mușețel"},
            "patlagele": {"pătlăgele"},
            "rosii": {"roșii"},
            "in": {"in", "în"},
            "soc": {"soc", "șoc"},
        },
    ):
        assert romanian_herb_name(name) == expected


def test_bundled_dictionary_restores_inflected_words_and_keeps_ambiguity():
    assert romanian_herb_name("coada-soricelului") == "coada-șoricelului"
    assert romanian_herb_name("musetel") == "mușețel"
    assert romanian_herb_name("par") == "par"
    assert romanian_herb_name("in") == "in"


def test_dictionary_missing_keeps_names_without_ai(tmp_path):
    herb_display._dictionary.cache_clear()
    try:
        with patch.object(herb_display, "HUNSPELL_DIR", tmp_path):
            assert romanian_herb_name("musetel") == "musetel"
    finally:
        herb_display._dictionary.cache_clear()


@pytest.mark.parametrize("count", [0, -1, 10001, True, "20"])
def test_invalid_limits_never_open_database(count):
    with patch("backend.ai.herb_ranking.db.get_pool") as pool:
        with pytest.raises(ValueError):
            list_top_herbs(count)
        with pytest.raises(ValueError):
            list_top_herbs(20, "category not in catalog")
        pool.assert_not_called()


def test_index_lock_conflict_does_not_query_ranking():
    with patch("backend.ai.herb_ranking.db.get_pool") as pool:
        connection = pool.return_value.connection.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = (False,)
        with pytest.raises(IndexUnavailable):
            list_top_herbs(20)
        assert connection.execute.call_count == 3
