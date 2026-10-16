"""Regression examples for Romanian plant names across lookup and routing."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from backend.ai.herbs import Herb, HerbCatalog
from backend.ai.message_classification import MessageClassifier
from backend.ai.query_terms import plain
from backend.ai.romanian_inflections import word_variants
from backend.config import Settings

EXAMPLES = [
    ("Pătlăgele roșii", "Pătlăgelele roșii"),
    ("Pătlăgele roșii", "pătlăgelelor roșii"),
    ("Usturoi", "Usturoiul"),
    ("Usturoi", "usturoiului"),
    ("Grepfrut", "Grepfrutul"),
    ("Lamai", "Lamaile"),
    ("Sunătoare", "Sunătoarea"),
    ("Galbenele", "Galbenelele"),
    ("Par", "Perele"),
    ("Scoruș", "Scorușele"),
    ("Mar", "Merele"),
    ("Soc", "Socul"),
    ("Ovăz", "Ovăzul"),
    ("Mei", "Meiul"),
    ("Mentă", "mentei"),
    ("Salvie", "salviei"),
    ("Tei", "teiului"),
    ("Mușețel", "mușețelului"),
    ("Coada-șoricelului", "coada șoricelului"),
]


@pytest.fixture(scope="module")
def catalog():
    return HerbCatalog(
        [
            Herb(
                id=index,
                ro=name,
                ro_regional=(),
                latin=f"testus species{index}",
                latin_synonyms=(),
                en="",
                en_alt=(),
                family="testaceae",
            )
            for index, name in enumerate(dict.fromkeys(name for name, _ in EXAMPLES), 1)
        ]
    )


@pytest.mark.parametrize("name,inflected", EXAMPLES)
@pytest.mark.parametrize("without_diacritics", [False, True])
def test_lookup_and_free_text_agree(catalog, name, inflected, without_diacritics):
    query = plain(inflected) if without_diacritics else inflected
    expected = catalog.lookup(name)
    assert catalog.lookup(query.upper()) == expected
    assert catalog.mentions(f"La ce sunt bune {query}?") == expected


@pytest.mark.parametrize("name,inflected", EXAMPLES)
def test_complete_plant_questions_bypass_model_and_resolve_in_catalog(catalog, name, inflected):
    classifier = MessageClassifier(Settings(), herb_catalog=lambda: catalog)
    classifier.client.complete_json = Mock(side_effect=AssertionError("Model should not be needed"))
    try:
        for message in (inflected, f"La ce sunt bune {inflected}?", f"detalii despre {inflected}"):
            decision = classifier(message, {})
            assert decision.intent == "planta" and not decision.needs_clarification
            assert catalog.lookup(decision.herb_name) == catalog.lookup(name)
        classifier.client.complete_json.assert_not_called()
    finally:
        classifier.close()


@pytest.mark.parametrize(
    "query", ["superusturoiul", "usturoiabc", "mereu", "mare", "meu", "mea", "mele"]
)
def test_similar_substrings_and_unrelated_dictionary_words_do_not_match(catalog, query):
    assert catalog.lookup(query) == []
    assert catalog.mentions(f"spune-mi despre {query}") == []


def test_longest_phrase_wins_and_foreign_names_stay_exact(catalog):
    tomato = catalog.lookup("pătlăgele roșii")[0]
    other = replace(tomato, id=100, ro="pătlăgele", latin="solanum lycopersicum", en="tomato")
    extended = HerbCatalog([*catalog.herbs, other])
    assert extended.mentions("pătlăgelele roșii") == [tomato]
    assert extended.lookup("solanum lycopersicumul") == []
    assert extended.lookup("tomatoul") == []
    assert extended.lookup("Solanum lycopersicum") == [other]


def test_literal_name_precedes_another_names_inflection(catalog):
    apple = catalog.lookup("mar")[0]
    literal = replace(apple, id=100, ro="merele", latin="testus literal")
    extended = HerbCatalog([apple, literal])
    assert extended.lookup("merele") == [literal]
    assert extended.mentions("despre merele") == [literal]


def test_shared_inflected_alias_preserves_all_species_and_choice_constraints(catalog):
    garlic = catalog.lookup("usturoi")[0]
    second = replace(
        garlic, id=100, ro="altă specie", latin="testus alius", ro_regional=("usturoi",)
    )
    extended = HerbCatalog([garlic, second])
    assert extended.lookup("usturoiului") == [garlic, second]
    assert extended.mentions("despre usturoiul") == [garlic, second]
    assert extended.selected_choice("usturoiului", [garlic.choice]) == garlic
    assert extended.selected_choice("usturoiului", [garlic.choice, second.choice]) is None


def test_two_inflected_plants_still_need_clarification(catalog):
    classifier = MessageClassifier(Settings(), herb_catalog=lambda: catalog)
    classifier.client.complete_json = Mock(
        return_value={"intent": "planta", "herb_name": "usturoi"}
    )
    try:
        decision = classifier("La ce sunt bune usturoiul și socul?", {})
        assert decision.needs_clarification and decision.herb_name is None
    finally:
        classifier.close()


def test_explicit_remedies_keep_their_route(catalog):
    classifier = MessageClassifier(Settings(), herb_catalog=lambda: catalog)
    classifier.client.complete_json = Mock(side_effect=AssertionError())
    try:
        assert classifier("Caută remedii pentru gripă cu usturoiul", {}).intent == "remedii"
    finally:
        classifier.close()


def test_no_dictionary_keeps_literal_matching(monkeypatch, tmp_path):
    import backend.ai.romanian_inflections as morphology

    word_variants.cache_clear()
    monkeypatch.setattr(morphology, "files", lambda _: tmp_path)
    try:
        assert word_variants(frozenset(("usturoi",))) == {"usturoi": frozenset(("usturoi",))}
    finally:
        word_variants.cache_clear()
