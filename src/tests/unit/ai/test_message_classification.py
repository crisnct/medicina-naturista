"""Strict intent contract and local Ollama wiring; no external traffic."""

from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from backend.ai.client import AIUnavailable
from backend.ai.herb_repository import HerbCatalogUnavailable
from backend.ai.herbs import Herb, HerbCatalog
from backend.ai.message_classification import MessageClassification, MessageClassifier
from backend.config import Settings


@pytest.mark.parametrize(
    "message",
    [
        "cauta remedii pentru premenopauza",
        "cauta remedii naturiste pentru premenopauza",
        "cauta remedii naturiste pentru premenopauza, buferuri, perimenopauza, premenopauza",
        "Caută tratamente naturiste pentru premenopauză",
        "Caută remedii pentru premenopauză!",
        "Te rog cauta remedii pentru perimenopauza",
        "Vreau remedii naturale pentru gripă și insomnie",
        "cauta remedii pentru o problema necunoscuta",
    ],
)
def test_explicit_remedies_do_not_accept_spurious_model_clarification(message):
    classifier = MessageClassifier(Settings(), herb_catalog=Mock(side_effect=AssertionError()))
    try:
        classifier.client.complete_json = Mock(
            return_value={"intent": "remedii", "needs_clarification": True}
        )
        result = classifier(
            message, {"report_available": False, "pending_clarification": None, "herb_choices": []}
        )
        assert result.intent == "remedii" and not result.needs_clarification
        classifier.client.complete_json.assert_not_called()
    finally:
        classifier.close()


@pytest.mark.parametrize(
    "message",
    [
        "Nu cauta remedii pentru premenopauza",
        "cauta remedii pentru premenopauza si trimite raportul la test@example.com",
        'Ce înseamnă "caută remedii pentru premenopauză"?',
        "cauta remedii pentru premenopauza si top 20 plante",
    ],
)
def test_compound_or_negative_remedy_requests_still_use_model(message):
    classifier = MessageClassifier(Settings())
    try:
        classifier.client.complete_json = Mock(
            return_value={"intent": "diverse", "needs_clarification": True}
        )
        assert classifier(message, {}).needs_clarification
        classifier.client.complete_json.assert_called_once()
    finally:
        classifier.close()


@pytest.mark.parametrize(
    "message,count",
    [
        ("Da-mi top 20 plante care sunt cele mai recomandate/utile", 20),
        ("Dă-mi primele 7 vitamine", 7),
        ("Care sunt cele mai utile 12 plante?", 12),
    ],
)
def test_explicit_top_does_not_require_ollama_or_catalog(message, count):
    classifier = MessageClassifier(Settings(), herb_catalog=Mock(side_effect=AssertionError()))
    try:
        classifier.client.complete_json = Mock(side_effect=AssertionError())
        decision = classifier(message, {})
        assert decision.intent == "top_plante" and decision.top_count == count
        from backend.core.herb_categories import HERB_CATEGORIES

        for category in HERB_CATEGORIES:
            scoped = classifier(f"Top {count} {category}", {})
            assert scoped.top_category == category and scoped.top_count == count
        assert classifier("Top 100   ", {}).top_category is None
        products = classifier("Top 100 produse naturiste", {})
        assert products.top_clarification == "category" and products.top_count == 100
        context = {
            "pending_clarification": "top_plante",
            "top_count": 100,
            "top_clarification": "category",
        }
        for index, category in enumerate(HERB_CATEGORIES, 1):
            selected = classifier(str(index), context)
            assert selected.top_category == category and selected.top_count == 100
            assert not selected.needs_clarification
        for invalid in ("0", "15", "100", "-1", "1.5", "vitamine"):
            invalid_choice = classifier(invalid, context)
            assert invalid_choice.top_clarification == "category"
            assert invalid_choice.top_count == 100 and invalid_choice.top_category is None
        assert classifier("Top aminoacizi", {}).top_count == 100
        assert classifier("Top 100 probiotice", {}).top_category == "suplimente"
        assert classifier("Top 100 prebiotice", {}).top_category == "suplimente"
        assert classifier("Top 100 fibre", {}).top_category == "suplimente"
        assert (
            classifier("Top 100 fibre, probiotice și prebiotice", {}).top_category == "suplimente"
        )
        assert classifier("Top 100 suplimente și probiotice", {}).top_category == "suplimente"
        assert classifier("Top 100 produse apicole", {}).top_category == "suplimente"
        assert classifier("Top 100 suplimente și produse apicole", {}).top_category == "suplimente"
        assert classifier("Top 5 medicamente", {}).top_clarification == "category"
        assert len(HERB_CATEGORIES) == 11
        assert classifier("12", context).top_clarification == "category"
        assert classifier("11", context).top_category == "minerale"
        assert classifier("Top 20 categorie necunoscuta", {}).top_clarification == "category"
        for invalid in ("-2", "0", "10001", "1.5"):
            assert classifier(f"Top {invalid} uleiuri esentiale", {}).top_clarification == "count"
        assert classifier("Top 20 vitamine si minerale", {}).top_count == 20
    finally:
        classifier.close()


def test_top_count_clarification_and_changed_subject():
    classifier = MessageClassifier(Settings())
    try:
        classifier.client.complete_json = Mock(return_value={"intent": "remedii"})
        assert classifier("20", {"pending_clarification": "top_plante"}).top_count == 20
        assert classifier("top 0 plante", {}).needs_clarification
        assert classifier("Top 20 plante pentru gastrită", {}).top_condition == "gastrita"
        assert classifier("Top 20 plante gastrită", {}).intent == "remedii"
        assert classifier("Gripă", {"pending_clarification": "top_plante"}).intent == "remedii"
        classifier.client.complete_json.assert_called()
        classifier.client.complete_json = Mock(
            return_value={"intent": "top_plante", "top_count": 999, "top_category": None}
        )
        scoped = classifier("Prezintă clasamentul celor 20 vitamine", {})
        assert scoped.top_count == 20 and scoped.top_category == "vitamine"
        assert classifier("Prezintă clasamentul cu 0 vitamine", {}).top_clarification == "count"
        classifier.client.complete_json = Mock(
            return_value={
                "intent": "top_plante",
                "top_count": 20,
                "top_category": "fibre, probiotice, prebiotice",
            }
        )
        assert classifier("Prezintă clasamentul cu 20 probiotice", {}).top_category == "suplimente"

    finally:
        classifier.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "top_plante"},
        {"intent": "top_plante", "top_count": True},
        {"intent": "top_plante", "top_count": "20"},
        {"intent": "top_plante", "top_count": 0},
        {"intent": "top_plante", "top_count": 10001},
        {"intent": "remedii", "top_count": 20},
    ],
)
def test_top_contract_rejects_invalid_limits(payload):
    with pytest.raises(ValidationError):
        MessageClassification.model_validate(payload)


def plant_catalog():
    return HerbCatalog(
        [
            Herb(
                category="plante medicinale",
                id=1,
                ro="coada-șoricelului",
                latin="achillea millefolium",
                en="yarrow",
                ro_regional=(),
                latin_synonyms=(),
                en_alt=(),
                family="asteraceae",
            ),
            Herb(
                category="plante medicinale",
                id=2,
                ro="mușețel",
                latin="matricaria chamomilla",
                en="chamomile",
                ro_regional=("romaniță",),
                latin_synonyms=(),
                en_alt=(),
                family="asteraceae",
            ),
            Herb(
                category="plante medicinale",
                id=3,
                ro="mentă",
                latin="mentha piperita",
                en="peppermint",
                ro_regional=(),
                latin_synonyms=(),
                en_alt=(),
                family="lamiaceae",
            ),
            Herb(
                category="plante medicinale",
                id=4,
                ro="mușețel roman",
                latin="chamaemelum nobile",
                en="roman chamomile",
                ro_regional=("mușețel", "romaniță"),
                latin_synonyms=(),
                en_alt=(),
                family="asteraceae",
            ),
        ]
    )


@pytest.mark.parametrize(
    "message,pending,expected",
    [
        ("spune-mi tot ce stii despre coada-soricelului", None, "coada-șoricelului"),
        ("coada-soricelului", "planta", "coada-șoricelului"),
        ("musetel", "planta", "musetel"),
        ("pentru ce e musetelul?", None, "musetel"),
        ("Achillea millefolium", "planta", "coada-șoricelului"),
    ],
)
def test_named_catalog_plant_resolves_spurious_clarification(message, pending, expected):
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(
            return_value={
                "intent": "planta",
                "herb_name": None,
                "needs_clarification": True,
            }
        )
        decision = classifier(message, {"pending_clarification": pending})
        assert decision.intent == "planta"
        assert decision.herb_name == expected
        assert not decision.needs_clarification
        if message == "pentru ce e musetelul?":
            sent = json.loads(classifier.client.complete_json.call_args.args[1])
            assert sent["context"]["recognized_herbs"]
        else:
            classifier.client.complete_json.assert_not_called()
    finally:
        classifier.close()


@pytest.mark.parametrize(
    "message", ["musetel si menta", "musetel sau menta", "compară mușețel cu mentă"]
)
def test_two_catalog_plants_require_clarification_even_if_model_selects_one(message):
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(
            return_value={
                "intent": "planta",
                "herb_name": "musetel",
                "needs_clarification": False,
            }
        )
        decision = classifier(message, {})
        assert decision.needs_clarification
        assert decision.herb_name is None
    finally:
        classifier.close()


def test_catalog_plant_does_not_replace_a_remedy_request():
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(return_value={"intent": "remedii"})
        assert classifier("Ce remedii cu musetel ajuta pentru gastrita?", {}).intent == "remedii"
    finally:
        classifier.close()


def test_catalog_unavailability_does_not_disable_other_classification():
    classifier = MessageClassifier(
        Settings(), herb_catalog=Mock(side_effect=HerbCatalogUnavailable())
    )
    try:
        classifier.client.complete_json = Mock(return_value={"intent": "diverse"})
        assert classifier("Cum funcționează căutarea?", {}).intent == "diverse"
    finally:
        classifier.close()


def test_no_catalog_substring_or_unknown_plant_is_assumed_to_be_named():
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(
            return_value={
                "intent": "planta",
                "needs_clarification": True,
            }
        )
        assert classifier("spune-mi despre supermusetel", {}).needs_clarification
        assert classifier("spune-mi despre o planta", {}).needs_clarification
    finally:
        classifier.close()


def test_ambiguous_name_is_selected_only_from_the_presented_choices():
    catalog = plant_catalog()
    assert len(catalog.lookup("musetel")) == 2
    choices = [herb.choice for herb in catalog.lookup("musetel")]
    assert catalog.selected_choice("musetel", choices).latin == "matricaria chamomilla"
    assert catalog.selected_choice("musetel roman", choices).latin == "chamaemelum nobile"
    assert catalog.selected_choice("menta", choices) is None


@pytest.mark.parametrize(
    "reply", ["musetel roman", "chamaemelum nobile", "mușețel roman (chamaemelum nobile)"]
)
def test_explicit_choice_completes_ambiguity_with_one_species(reply):
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(
            return_value={"intent": "planta", "needs_clarification": True}
        )
        choices = [herb.choice for herb in plant_catalog().lookup("musetel")]
        decision = classifier(reply, {"pending_clarification": "planta", "herb_choices": choices})
        assert decision.herb_name == "chamaemelum nobile" and not decision.needs_clarification
    finally:
        classifier.close()


@pytest.mark.parametrize("message", ["romanita", "detalii despre romanita"])
def test_one_shared_alias_reaches_catalog_choices_instead_of_generic_clarification(message):
    classifier = MessageClassifier(Settings(), herb_catalog=plant_catalog)
    try:
        classifier.client.complete_json = Mock(
            return_value={"intent": "planta", "needs_clarification": True}
        )
        decision = classifier(message, {"pending_clarification": "planta"})
        assert decision.intent == "planta" and decision.herb_name == "romanita"
        assert not decision.needs_clarification
    finally:
        classifier.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "anything"},
        {"intent": "planta"},
        {"intent": "diverse", "herb_name": "mușețel"},
        {"intent": "remedii", "email_address": "a@example.com"},
        {"intent": "diverse", "needs_clarification": "false"},
        {"intent": "diverse", "sql": "DELETE"},
    ],
)
def test_invalid_output_is_rejected(payload):
    with pytest.raises(ValidationError):
        MessageClassification.model_validate(payload)


def test_existing_ollama_configuration_and_bounded_request_are_reused():
    classifier = MessageClassifier(Settings())
    try:
        assert classifier.client.provider.name == "ollama"
        assert classifier.client.provider.base_url == "http://localhost:11434/v1"
        assert classifier.client.provider.model == "gemma3:1b"
        assert classifier.client.provider.temperature == 0.0
        assert classifier.client.provider.read_timeout_seconds == 10
        classifier.client.complete_json = Mock(
            return_value={"intent": "planta", "herb_name": "mușețel"}
        )
        result = classifier("detalii despre mușețel", {"report_available": False})
        assert result.herb_name == "mușețel"
        assert classifier.client.complete_json.call_args.args[2] == 300
    finally:
        classifier.close()


def test_ollama_request_needs_no_hf_token_and_uses_the_existing_endpoint():
    settings = Settings(
        hf_api_token="",
        condition_ai_local_base="http://host.docker.internal:11434/v1",
        medical_condition_ai_local_model="gemma3:1b",
        message_classification_timeout_seconds=17,
        message_classification_max_output_tokens=250,
    )
    classifier = MessageClassifier(settings)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"intent":"diverse"}'}],
                    }
                ],
            },
        )

    try:
        classifier.client.http.close()
        classifier.client.http = httpx.Client(transport=httpx.MockTransport(respond))
        assert classifier("O întrebare generală", {}).intent == "diverse"
        assert len(requests) == 1
        assert str(requests[0].url) == "http://host.docker.internal:11434/v1/responses"
        assert "Authorization" not in requests[0].headers
        payload = json.loads(requests[0].content)
        assert payload["model"] == "gemma3:1b"
        assert payload["temperature"] == 0.0
        assert payload["reasoning"] == {"effort": "none"}
        assert payload["max_output_tokens"] == 250
        assert payload.get("stream", False) is False
        schema = payload["text"]["format"]
        assert schema["type"] == "json_schema"
        assert schema["strict"] is True
        branches = schema["schema"]["oneOf"]
        assert [branch["properties"]["intent"]["enum"][0] for branch in branches] == [
            "remedii",
            "planta",
            "diverse",
            "email_raport",
            "top_plante",
        ]
        from backend.core.herb_categories import HERB_CATEGORIES

        assert branches[-1]["properties"]["top_category"]["enum"] == [*HERB_CATEGORIES, None]
        assert branches[-1]["properties"]["top_clarification"]["enum"] == [
            "count",
            "category",
            "condition",
            None,
        ]
        assert "top_category" in branches[-1]["required"]
        assert "top_clarification" in branches[-1]["required"]
        assert branches[0]["properties"]["top_category"]["enum"] == [None]
        assert branches[0]["properties"]["herb_name"]["type"] == "null"
        assert branches[2]["properties"]["email_address"]["type"] == "null"
        assert classifier.client.provider.read_timeout_seconds == 17
    finally:
        classifier.close()


def test_failed_ollama_response_is_unavailable_without_a_hf_fallback():
    classifier = MessageClassifier(Settings(hf_api_token="synthetic"))
    try:
        response = Mock()
        response.json.return_value = {
            "status": "failed",
            "error": {"code": "server_error", "message": "Model unavailable"},
        }
        classifier.client._post = Mock(return_value=response)
        with pytest.raises(AIUnavailable) as caught:
            classifier("Gripă", {})
        assert caught.value.reason == "provider_failed"
        classifier.client._post.assert_called_once()
    finally:
        classifier.close()
