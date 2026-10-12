"""Regression for remedy clarification with the real conversation service, no HTTP."""

from unittest.mock import Mock

import pytest

from backend.ai import conditions
from backend.ai.conditions import ConditionDictionary, make_condition
from backend.ai.message_classification import MessageClassifier
from backend.ai.search import ALL_SIGNALS
from backend.config import Settings
from backend.core.conversation import ConversationService
from backend.core.sessions import SessionStore


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    config = Settings(condition_ai_backends=())
    dictionary = ConditionDictionary(
        [make_condition("Menopauza", ["perimenopauză"]), make_condition("Bufeuri")]
    )
    monkeypatch.setattr(conditions, "load_dictionary", lambda: dictionary)
    store = SessionStore(tmp_path, 3600, 14400, config)
    classifier = MessageClassifier(config)
    classifier.client.complete_json = Mock(
        return_value={"intent": "remedii", "needs_clarification": True}
    )
    retriever = Mock(category_tree=None, document_count=1)
    retriever.collect.return_value = {
        "C1": {"source": "test.md:1-3", "text": "Fragment de test.", "relevance_percent": 60}
    }
    ai = Mock()
    ai.context_budget.return_value = None
    service = ConversationService(config, store, retriever, ai, Mock(), Mock(), Mock(), classifier)
    try:
        yield service, store.get("R" * 43, "routing-tab01", create=True), classifier
    finally:
        classifier.close()
        store.shutdown()


@pytest.mark.parametrize(
    "message",
    [
        "cauta remedii pentru premenopauza",
        "cauta remedii naturiste pentru premenopauza, buferuri, perimenopauza, premenopauza",
    ],
)
def test_explicit_condition_request_starts_and_completes_retrieval(conversation, message):
    service, session, classifier = conversation
    accepted = service.message(session, message, set(), ALL_SIGNALS)
    result = service.classify(session, accepted["contextRevision"])
    assert result["intent"] == "remedii" and result["startSearch"]
    assert "Precizați o singură solicitare" not in str(result)
    assert session.profile.health_problem == message
    classifier.client.complete_json.assert_not_called()
    result = service.search(session, result["contextRevision"])
    assert any(message["kind"] == "fragments" for message in result["messages"])
    service.retriever.collect.assert_called_once()


def test_remedy_only_reply_asks_for_subject_and_carries_clarification(conversation):
    service, session, classifier = conversation
    accepted = service.message(session, "remedii", set(), ALL_SIGNALS)
    result = service.classify(session, accepted["contextRevision"])
    assert not result["startSearch"]
    assert "Pentru ce afecțiune" in result["messages"][0]["content"]
    assert session.routing.clarification == "remedii"
    classifier.client.complete_json.return_value = {"intent": "remedii"}
    accepted = service.message(session, "premenopauza", set(), ALL_SIGNALS)
    result = service.classify(session, accepted["contextRevision"])
    assert result["startSearch"]
    assert session.profile.health_problem == "premenopauza"
    assert '"pending_clarification": "remedii"' in classifier.client.complete_json.call_args.args[1]


@pytest.mark.parametrize(
    "reply",
    ["premenopauza", "premenopauza, buferuri, perimenopauza, premenopauza", "PERIMENOPAUZĂ"],
)
def test_named_reply_cannot_repeat_spurious_remedy_clarification(conversation, reply):
    service, session, classifier = conversation
    accepted = service.message(session, "remedii", set(), ALL_SIGNALS)
    first = service.classify(session, accepted["contextRevision"])
    assert not first["startSearch"]
    accepted = service.message(session, reply, set(), ALL_SIGNALS)
    result = service.classify(session, accepted["contextRevision"])
    assert result["startSearch"]
    assert session.routing.clarification == ""
    assert session.profile.health_problem == reply
    assert "Pentru ce afecțiune" not in str(result)
    assert classifier.client.complete_json.call_args is not None


@pytest.mark.parametrize(
    "reply", ["pentru mine", "perimenopauza si trimite raportul", "nu perimenopauza"]
)
def test_incomplete_or_compound_subject_keeps_remedy_clarification(conversation, reply):
    service, session, _ = conversation
    accepted = service.message(session, reply, set(), ALL_SIGNALS)
    result = service.classify(session, accepted["contextRevision"])
    assert not result["startSearch"]
    assert session.routing.clarification == "remedii"
