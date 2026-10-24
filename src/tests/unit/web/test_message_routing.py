"""Intent routing, cancellation and email claims with isolated HTTP dependencies."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from backend.ai.client import AIUnavailable
from backend.ai.message_classification import MessageClassification, MessageClassifier
from backend.core.errors import ApplicationError
from backend.core.models import CommitChange, StoredReport
from tests.unit.ai.test_message_classification import plant_catalog
from tests.unit.web import test_web as support


@pytest.fixture
def web():
    test = support.WebTests()
    test.setUp()
    sid, tab = "R" * 43, "routing-tab01"
    test.client.get("/api/session", headers=support._headers(sid, tab))
    try:
        yield test, sid, tab
    finally:
        test.doCleanups()


def accept(web, text, signals=None):
    test, sid, tab = web
    payload = {"message": text, "categories": []}
    if signals is not None:
        payload["signals"] = signals
    response = test.client.post("/api/messages", json=payload, headers=support._headers(sid, tab))
    assert response.status_code == 200, response.text
    return response.json()


def classify(web, revision):
    test, sid, tab = web
    return test.client.post(
        "/api/classify", headers={**support._headers(sid, tab), "X-Context-Revision": str(revision)}
    )


def report(web, identity="previous", data=b"previous pdf"):
    test, sid, tab = web
    session = test.deps.store.get(sid, tab)
    operation = test.deps.store.begin_operation(session, "message")
    try:
        test.deps.store.commit_operation(
            operation,
            CommitChange(report=(identity, StoredReport(data, identity + ".pdf", "Gripă"))),
        )
    finally:
        test.deps.store.finish_operation(operation)


def test_echo_is_fast_and_does_not_replace_the_medical_profile(web):
    test, sid, tab = web
    classifier = test.deps.classify = Mock(return_value=MessageClassification(intent="diverse"))
    first = accept(web, "cum se prepară o infuzie?")
    assert first["classifyMessage"] and not first["startSearch"]
    assert len(first["messages"]) == 1 and first["messages"][0]["role"] == "user"
    assert test.deps.store.get(sid, tab).profile.health_problem == ""
    classifier.assert_not_called()
    result = classify(web, first["contextRevision"]).json()
    assert result["intent"] == "diverse" and result["startSearch"]
    assert test.deps.store.get(sid, tab).profile.health_problem == "cum se prepară o infuzie?"


def test_explicit_premenopause_request_starts_search_with_real_classifier(web):
    test, sid, tab = web
    classifier = MessageClassifier(test.deps.settings)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(
        return_value={"intent": "remedii", "needs_clarification": True}
    )
    test.deps.classify = classifier
    first = accept(web, "cauta remedii pentru premenopauza")
    response = classify(web, first["contextRevision"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["intent"] == "remedii" and result["startSearch"]
    assert "Precizați o singură solicitare" not in str(result)
    assert (
        test.deps.store.get(sid, tab).profile.health_problem == "cauta remedii pentru premenopauza"
    )
    assert test.client.post("/api/search", headers=support._headers(sid, tab)).status_code == 200
    classifier.client.complete_json.assert_not_called()


def test_remedy_clarification_asks_for_condition_and_then_starts_search(web):
    test, sid, tab = web
    classifier = MessageClassifier(test.deps.settings)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(return_value={"intent": "remedii"})
    test.deps.classify = classifier
    first = accept(web, "remedii")
    result = classify(web, first["contextRevision"]).json()
    assert not result["startSearch"]
    assert "Pentru ce afecțiune" in result["messages"][0]["content"]
    assert test.deps.store.get(sid, tab).routing.clarification == "remedii"
    second = accept(web, "premenopauza")
    result = classify(web, second["contextRevision"]).json()
    assert result["startSearch"]
    context = classifier.client.complete_json.call_args.args[1]
    assert '"pending_clarification": "remedii"' in context


def test_top_returns_names_and_aliases_without_search_or_report(web):
    test, sid, tab = web
    test.deps.classify = Mock(return_value=MessageClassification(intent="top_plante", top_count=20))
    test.deps.top_herbs = Mock(
        return_value=[
            {
                "ro": "mușețel",
                "latin": "matricaria chamomilla",
                "ro_regional": ["romaniță", "matricea"],
                "ranking": 1156,
            },
            {"ro": "păr", "latin": "pyrus communis", "ro_regional": [], "ranking": 1},
        ]
    )
    first = accept(
        web, "Dă-mi top 20 plante", {"conditions": True, "lexical": False, "semantic": False}
    )
    response = classify(web, first["contextRevision"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["intent"] == "top_plante"
    assert not result["startSearch"] and not result["identifyCondition"]
    assert result["messages"][0]["content"] == (
        "### Top 2 produse naturiste — toate categoriile după numărul de afecțiuni din bibliotecă\n"
        "Numărul reprezintă afecțiuni distincte cu recomandări pozitive identificate în surse.\n"
        "Sunt disponibile 2 produse cu scor pozitiv din cele 20 solicitate.\n"
        "1. **Mușețel** (Matricaria Chamomilla) — util(ă) în "
        "1156 afecțiuni (denumiri regionale: romaniță, matricea)\n"
        "2. **Păr** (Pyrus Communis) — util(ă) în 1 afecțiune"
    )
    test.deps.top_herbs.assert_called_once_with(20, None)
    assert test.deps.store.get(sid, tab).profile.health_problem == ""
    assert test.client.post("/api/search", headers=support._headers(sid, tab)).status_code == 409
    classify(web, first["contextRevision"])
    test.deps.top_herbs.assert_called_once()


def test_top_without_count_asks_then_accepts_count_only(web):
    test, sid, tab = web
    classifier = MessageClassifier(test.deps.settings)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(
        return_value={"intent": "top_plante", "needs_clarification": True}
    )
    test.deps.classify = classifier
    test.deps.top_herbs = Mock(return_value=[])
    first = accept(web, "Top 0 uleiuri esentiale")
    result = classify(web, first["contextRevision"]).json()
    assert "Câte intrări" in result["messages"][0]["content"]
    assert test.deps.store.get(sid, tab).routing.clarification == "top_plante"
    test.deps.top_herbs.assert_not_called()
    second = accept(web, "20")
    result = classify(web, second["contextRevision"]).json()
    test.deps.top_herbs.assert_called_once_with(20, "uleiuri esentiale")
    assert "Nu există produse cu recomandări pozitive" in result["messages"][0]["content"]

    assert "uleiuri esențiale" in result["messages"][0]["content"]
    test.deps.top_herbs.reset_mock()
    third = accept(web, "Top 20 vitamine și minerale")
    result = classify(web, third["contextRevision"]).json()
    assert "Alegeți o singură categorie" in result["messages"][0]["content"]
    assert test.deps.store.get(sid, tab).routing.top_count == 20
    fourth = accept(web, "10")
    result = classify(web, fourth["contextRevision"]).json()
    test.deps.top_herbs.assert_called_once_with(20, "vitamine")
    classify(web, fourth["contextRevision"])
    test.deps.top_herbs.assert_called_once()
    test.deps.top_herbs.reset_mock()
    products = accept(web, "Top 37 produse naturiste")
    menu = classify(web, products["contextRevision"]).json()["messages"][0]["content"]
    assert "1. plante medicinale\n2. fructe" in menu
    assert "11. minerale" in menu
    assert "12." not in menu
    assert "medicamente" not in menu
    assert "produse apicole" not in menu
    assert "fibre, probiotice" not in menu
    assert test.deps.store.get(sid, tab).routing.top_count == 37
    test.deps.top_herbs.assert_not_called()
    invalid = accept(web, "15")
    assert classify(web, invalid["contextRevision"]).json()["messages"][0]["content"] == menu
    test.deps.top_herbs.assert_not_called()
    selection = accept(web, "7")
    classify(web, selection["contextRevision"])
    test.deps.top_herbs.assert_called_once_with(37, "uleiuri")
    classify(web, selection["contextRevision"])
    test.deps.top_herbs.assert_called_once()
    fifth = accept(web, "La ce e bun mușețelul?")
    classifier.client.complete_json = Mock(
        return_value={"intent": "planta", "herb_name": "mușețel"}
    )
    test.deps.herb_lookup = Mock(return_value={"status": "not_found"})
    classify(web, fifth["contextRevision"])
    routing = test.deps.store.get(sid, tab).routing
    assert (
        routing.top_count is None
        and routing.top_category is None
        and routing.top_clarification is None
    )


def test_diverse_skips_ai_identification_and_direct_condition_endpoint(web):
    test, sid, tab = web
    test.condition_ai_gate.side_effect = AssertionError(
        "Must not schedule condition identification"
    )
    test.deps.classify = Mock(return_value=MessageClassification(intent="diverse"))
    test.deps.identify = Mock(side_effect=AssertionError("Must not identify a condition"))
    first = accept(web, "cum se prepară o infuzie?")
    result = classify(web, first["contextRevision"]).json()
    assert result["startSearch"] and not result["identifyCondition"]
    assert "Nu am găsit afecțiunea" not in str(result)
    assert "Nu am putut identifica" not in str(result)
    direct = test.client.post("/api/condition", headers=support._headers(sid, tab))
    assert direct.status_code == 200
    test.deps.identify.assert_not_called()
    search = test.client.post("/api/search", headers=support._headers(sid, tab))
    assert search.status_code == 200
    pending = next(iter(test.deps.store.get(sid, tab).searches.values()))
    assert (
        pending.intent == "diverse"
        and pending.profile["health_problem"] == "cum se prepară o infuzie?"
    )


def test_diverse_only_conditions_requests_other_signals_without_clinical_warning(web):
    test, _, _ = web
    test.deps.classify = lambda *args: MessageClassification(intent="diverse")
    first = accept(
        web, "cum prepar o infuzie?", {"conditions": True, "lexical": False, "semantic": False}
    )
    result = classify(web, first["contextRevision"]).json()
    assert not result["startSearch"]
    assert "Activați căutarea lexicală" in str(result)
    assert "afecțiun" not in str(result)


@pytest.mark.parametrize("count", [0, 2])
def test_plant_returns_structured_results_without_search_or_identification(web, count):
    test, sid, tab = web
    test.deps.classify = Mock(
        return_value=MessageClassification(intent="planta", herb_name="musetel")
    )
    lookup = test.deps.herb_lookup = Mock(
        return_value={
            "status": "found",
            "herbName": "mușețel",
            "species": ["matricaria chamomilla"],
            "entriesCount": count,
            "conditions": [{"id": i, "name": str(i)} for i in range(1, count + 1)],
            "herbId": 17,
            "positiveRunId": "synthetic-positive-run",
            "fragmentsCount": count,
            "documentsCount": count,
        }
    )
    test.deps.retriever.category_tree = object()  # Empty categories must not block a plant query.
    first = accept(web, "pentru ce e musetelul?")
    result = classify(web, first["contextRevision"]).json()
    assert not result["startSearch"] and not result["identifyCondition"]
    assert result["messages"][0]["kind"] == "herb_conditions"
    assert result["messages"][0]["entriesCount"] == count
    lookup.assert_called_once_with("musetel")
    message = result["messages"][0]
    evidence = test.deps.herb_evidence = Mock(
        return_value={
            "herbId": 17,
            "positiveRunId": "synthetic-positive-run",
            "fragmentsCount": count,
            "documentsCount": count,
            "fragments": [],
            "nextOffset": None,
        }
    )
    url = f"/api/herb-evidence/{message['groupId']}"
    headers = support._headers(sid, tab)
    response = test.client.get(url, headers=headers)
    assert response.status_code == 200 and response.json()["fragmentsCount"] == count
    evidence.assert_called_once_with(17, "synthetic-positive-run", condition_id=None, offset=0)
    if count:
        assert test.client.get(url + "?conditionId=1&offset=20", headers=headers).status_code == 200
        evidence.assert_called_with(17, "synthetic-positive-run", condition_id=1, offset=20)
    calls = evidence.call_count
    assert test.client.get(url + "?conditionId=999", headers=headers).status_code == 422
    assert test.client.get(url + "?offset=-1", headers=headers).status_code == 422
    assert test.client.get("/api/herb-evidence/missing-group", headers=headers).status_code == 404
    other = support._headers(sid, "another-tab01")
    test.client.get("/api/session", headers=other)
    assert test.client.get(url, headers=other).status_code == 404
    assert evidence.call_count == calls
    evidence.side_effect = ApplicationError("HERB_EVIDENCE_STALE", "Repetați întrebarea.", 409)
    assert test.client.get(url, headers=headers).json()["detail"]["code"] == "HERB_EVIDENCE_STALE"
    blocked = test.client.post("/api/search", headers=support._headers(sid, tab))
    assert blocked.status_code == 409


@pytest.mark.parametrize(
    "lookup_result",
    [
        {"status": "not_found"},
        {"status": "ambiguous", "choices": ["planta a", "planta b"]},
    ],
)
def test_plant_clarification_is_passed_to_the_next_classification(web, lookup_result):
    test, sid, tab = web
    test.deps.classify = Mock(
        return_value=MessageClassification(intent="planta", herb_name="alias")
    )
    test.deps.herb_lookup = Mock(return_value=lookup_result)
    first = accept(web, "detalii despre alias")
    result = classify(web, first["contextRevision"]).json()
    assert not result["startSearch"]
    assert test.deps.store.get(sid, tab).routing.clarification == "planta"
    second = accept(web, "planta a")
    classify(web, second["contextRevision"])
    context = test.deps.classify.call_args.args[1]
    assert context["pending_clarification"] == "planta"
    assert context["herb_choices"] == lookup_result.get("choices", [])


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("coada-soricelului", "coada-șoricelului"),
        ("Achillea millefolium", "coada-șoricelului"),
    ],
)
def test_named_reply_finishes_plant_clarification_and_returns_results(web, reply, expected):
    test, _, _ = web
    classifier = MessageClassifier(test.deps.settings, herb_catalog=plant_catalog)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(
        return_value={
            "intent": "planta",
            "herb_name": None,
            "needs_clarification": True,
        }
    )
    test.deps.classify = classifier
    test.deps.herb_lookup = Mock(
        return_value={
            "status": "found",
            "herbName": expected,
            "species": [],
            "entriesCount": 1,
            "conditions": [{"id": 1, "name": "condiție test"}],
        }
    )
    first = accept(web, "Vreau informații despre o plantă")
    initial = classify(web, first["contextRevision"]).json()
    assert "Precizați o singură intrare" in str(initial)
    test.deps.herb_lookup.assert_not_called()
    second = accept(web, reply)
    completed = classify(web, second["contextRevision"]).json()
    assert completed["intent"] == "planta"
    assert completed["messages"][0]["kind"] == "herb_conditions"
    assert completed["messages"][0]["entriesCount"] == 1
    assert "Precizați o singură intrare" not in str(completed)
    test.deps.herb_lookup.assert_called_once_with(expected)


def test_shared_name_lists_species_then_uses_only_the_user_choice(web):
    test, _, _ = web
    classifier = MessageClassifier(test.deps.settings, herb_catalog=plant_catalog)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(
        return_value={"intent": "planta", "needs_clarification": True}
    )
    test.deps.classify = classifier
    choices = [herb.choice for herb in plant_catalog().lookup("musetel")]
    test.deps.herb_lookup = Mock(
        side_effect=[
            {"status": "ambiguous", "choices": choices},
            {
                "status": "found",
                "herbName": "mușețel roman",
                "species": ["chamaemelum nobile"],
                "entriesCount": 0,
                "conditions": [],
            },
        ]
    )
    first = accept(web, "musetel")
    offered = classify(web, first["contextRevision"]).json()
    assert "Alegeți una" in str(offered)
    assert "matricaria chamomilla" in str(offered) and "chamaemelum nobile" in str(offered)
    assert "Precizați o singură intrare" not in str(offered)
    second = accept(web, "musetel roman")
    completed = classify(web, second["contextRevision"]).json()
    assert completed["messages"][0]["kind"] == "herb_conditions"
    assert completed["messages"][0]["species"] == ["chamaemelum nobile"]
    assert test.deps.herb_lookup.call_args.args == ("chamaemelum nobile",)


def test_classification_is_reused_without_duplicate_messages_or_calls(web):
    test, sid, tab = web
    test.deps.classify = Mock(return_value=MessageClassification(intent="diverse"))
    first = accept(web, "cum prepar o infuzie?")
    assert classify(web, first["contextRevision"]).status_code == 200
    history = test.deps.store.history(test.deps.store.get(sid, tab))
    repeated = classify(web, first["contextRevision"]).json()
    assert repeated["messages"] == [] and repeated["startSearch"]
    assert test.deps.store.history(test.deps.store.get(sid, tab)) == history
    test.deps.classify.assert_called_once()


def test_new_message_discards_late_classification_and_concurrent_call_is_rejected(web):
    test, sid, tab = web
    entered, release = threading.Event(), threading.Event()

    def slow(*args):
        entered.set()
        assert release.wait(5)
        return MessageClassification(intent="diverse")

    test.deps.classify = slow
    first = accept(web, "primul mesaj")
    with ThreadPoolExecutor(1) as executor:
        future = executor.submit(classify, web, first["contextRevision"])
        try:
            assert entered.wait(3)
            assert classify(web, first["contextRevision"]).status_code == 409
            second = accept(web, "mesaj nou")
        finally:
            release.set()
        result = future.result(3).json()
    assert result["cancelled"] and not result["messages"]
    assert classify(web, first["contextRevision"]).json()["cancelled"]
    assert test.deps.store.get(sid, tab).routing.message == "mesaj nou"
    assert second["contextRevision"] > first["contextRevision"]
    assert test.deps.store.metrics()["reserved_bytes"] == 0


def test_classification_requires_revision_and_search_cannot_bypass_it(web):
    test, sid, tab = web
    accept(web, "Gripă")
    assert test.client.post("/api/classify", headers=support._headers(sid, tab)).status_code == 422
    assert test.client.post("/api/search", headers=support._headers(sid, tab)).status_code == 409


def test_email_selects_previous_report_before_classification_and_never_resends(web):
    test, sid, tab = web
    report(web)
    test.deps.email = Mock(return_value="sent")

    def decision(*args):
        report(web, "newer", b"newer pdf")
        return MessageClassification(intent="email_raport", email_address="friend@example.com")

    test.deps.classify = decision
    original = "Trimite raportul la friend@example.com"
    first = accept(web, original)
    result = classify(web, first["contextRevision"]).json()
    assert "Am trimis" in str(result)
    assert test.deps.email.call_args.args[1] == b"previous pdf"
    assert test.deps.email.call_args.args[2:] == ("previous.pdf", "friend@example.com")
    classify(web, first["contextRevision"])
    test.deps.email.assert_called_once()
    history = test.deps.store.history(test.deps.store.get(sid, tab))
    assert sum(m.get("content") == original for m in history) == 1


@pytest.mark.parametrize(
    "message,candidate",
    [
        ("Trimite raportul la a@example.com și b@example.com", None),
        ("Trimite raportul la invalid@@example.com", None),
        ("Trimite raportul la a@example.com", "invented@example.com"),
        ("Trimite raportul", None),
    ],
)
def test_email_needs_one_explicit_valid_address(web, message, candidate):
    test, sid, tab = web
    report(web)
    test.deps.email = Mock()
    test.deps.classify = lambda *args: MessageClassification(
        intent="email_raport", email_address=candidate
    )
    first = accept(web, message)
    result = classify(web, first["contextRevision"]).json()
    assert "singură adresă validă" in str(result)
    assert not result["startSearch"]
    test.deps.email.assert_not_called()
    assert test.deps.store.get(sid, tab).routing.clarification == "email_raport"


def test_email_clarification_keeps_its_report_and_can_be_completed_with_address(web):
    test, _, _ = web
    report(web)
    test.deps.email = Mock(return_value="sent")
    test.deps.classify = Mock(return_value=MessageClassification(intent="email_raport"))
    first = accept(web, "trimite raportul")
    classify(web, first["contextRevision"])
    report(web, "newer", b"newer pdf")
    second = accept(web, "friend@example.com")
    result = classify(web, second["contextRevision"]).json()
    assert "Am trimis" in str(result)
    assert test.deps.email.call_args.args[1] == b"previous pdf"
    assert test.deps.classify.call_args.args[1]["pending_clarification"] == "email_raport"


def test_email_without_report_does_not_search(web):
    test, _, _ = web
    test.deps.classify = lambda *args: MessageClassification(intent="email_raport")
    test.deps.email = Mock()
    first = accept(web, "Trimite raportul la friend@example.com")
    result = classify(web, first["contextRevision"]).json()
    assert "Nu există un raport precedent" in str(result) and not result["startSearch"]
    test.deps.email.assert_not_called()


def test_email_failure_keeps_pdf_and_claim_prevents_automatic_retry(web):
    test, sid, tab = web
    report(web)
    test.deps.email = Mock(side_effect=TimeoutError("delivery uncertain"))
    test.deps.classify = lambda *args: MessageClassification(intent="email_raport")
    first = accept(web, "friend@example.com")
    result = classify(web, first["contextRevision"]).json()
    assert "Nu am putut trimite" in str(result)
    classify(web, first["contextRevision"])
    test.deps.email.assert_called_once()
    assert test.deps.store.get(sid, tab).reports["previous"].data == b"previous pdf"


@pytest.mark.parametrize(
    "text,is_email", [("Gripă", False), ("Trimite raportul la friend@example.com", True)]
)
def test_provider_failure_has_controlled_fallback_and_cannot_send_email(web, text, is_email):
    test, _, _ = web
    report(web)
    test.deps.classify = Mock(side_effect=AIUnavailable("unavailable"))
    test.deps.email = Mock()
    first = accept(web, text)
    result = classify(web, first["contextRevision"]).json()
    assert result["startSearch"] is not is_email
    test.deps.email.assert_not_called()


def test_bare_email_retains_deterministic_fallback(web):
    test, _, _ = web
    report(web)
    test.deps.classify = Mock(side_effect=AIUnavailable("unavailable"))
    test.deps.email = Mock(return_value="sent")
    first = accept(web, "friend@example.com")
    assert classify(web, first["contextRevision"]).status_code == 200
    test.deps.email.assert_called_once()


def test_duplicate_message_id_cannot_resend_email_even_after_other_messages(web):
    test, sid, tab = web
    report(web)
    test.deps.email = Mock(return_value="sent")
    test.deps.classify = lambda *args: MessageClassification(intent="email_raport")
    payload = {"message": "friend@example.com", "messageId": "synthetic-request01"}
    headers = support._headers(sid, tab)
    first = test.client.post("/api/messages", json=payload, headers=headers).json()
    classify(web, first["contextRevision"])
    repeated = test.client.post("/api/messages", json=payload, headers=headers).json()
    assert repeated["contextRevision"] == first["contextRevision"] and not repeated["messages"]
    classify(web, repeated["contextRevision"])
    accept(web, "un mesaj nou")
    stale = test.client.post("/api/messages", json=payload, headers=headers).json()
    assert stale["cancelled"] and not stale["classifyMessage"]
    conflict = test.client.post(
        "/api/messages", json={**payload, "message": "different"}, headers=headers
    )
    assert conflict.status_code == 409
    test.deps.email.assert_called_once()


def test_local_classifier_failure_is_explained_in_the_fallback(web):
    test, _, _ = web
    test.deps.classify = Mock(side_effect=AIUnavailable("Ollama unavailable"))
    first = accept(web, "Gripă")
    result = classify(web, first["contextRevision"]).json()
    assert result["startSearch"] and "Clasificarea AI nu este disponibilă" in str(result)
    assert "credite" not in str(result)


@pytest.mark.parametrize(
    "reply", ["premenopauza", "premenopauza, buferuri, perimenopauza, premenopauza"]
)
def test_named_remedy_reply_starts_search_despite_model_clarification(web, monkeypatch, reply):
    from backend.ai import conditions
    from backend.ai.conditions import ConditionDictionary, make_condition

    dictionary = ConditionDictionary(
        [make_condition("Menopauza", ["perimenopauza"]), make_condition("Bufeuri")]
    )
    monkeypatch.setattr(conditions, "load_dictionary", lambda: dictionary)
    test, sid, tab = web
    classifier = MessageClassifier(test.deps.settings)
    test.addCleanup(classifier.close)
    classifier.client.complete_json = Mock(
        return_value={"intent": "remedii", "needs_clarification": True}
    )
    test.deps.classify = classifier
    first = accept(web, "remedii")
    assert not classify(web, first["contextRevision"]).json()["startSearch"]
    second = accept(web, reply)
    response = classify(web, second["contextRevision"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["startSearch"]
    assert "Pentru ce afecțiune" not in str(result)
    assert test.deps.store.get(sid, tab).profile.health_problem == reply
    assert test.client.post("/api/search", headers=support._headers(sid, tab)).status_code == 200
