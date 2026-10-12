"""Strict intent contract and local Ollama wiring; no external traffic."""

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


def plant_catalog():
    return HerbCatalog(
        [
            Herb(
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
        sent = json.loads(classifier.client.complete_json.call_args.args[1])
        assert sent["context"]["recognized_herbs"]
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
        condition_ai_local_base="http://ollama:11434/v1",
        condition_ai_local_model="gemma3:1b",
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
        assert str(requests[0].url) == "http://ollama:11434/v1/responses"
        assert "Authorization" not in requests[0].headers
        payload = json.loads(requests[0].content)
        assert payload["model"] == "gemma3:1b"
        assert payload["temperature"] == 0.0
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
        ]
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
