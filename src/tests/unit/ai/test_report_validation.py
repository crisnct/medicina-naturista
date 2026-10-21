import io
import json
from unittest.mock import patch

import pytest
from pypdf import PdfReader

from backend.ai.report_validation import (
    SECTIONS,
    ReportValidationError,
    partial_notice,
    validate_report,
)
from backend.reporting.pdf import create_pdf
from backend.web.handlers import _recommendation_text


def report(**sections):
    return {**dict.fromkeys(SECTIONS, []), **sections}


EVIDENCE = {
    "C1": {"source": "documents/synthetic.md:1-2", "text": "synthetic", "relevance_percent": 50}
}
VALID = {"text": "Recomandare sintetică", "evidence_ids": ["C1"]}


@pytest.mark.parametrize(
    "invalid,code",
    [
        ({"text": "secret medical", "evidence_ids": ["C1", "invented"]}, "UNKNOWN_EVIDENCE"),
        ({"text": "secret medical", "evidence_ids": [1]}, "INVALID_ITEM"),
        ({"text": "secret medical", "evidence_ids": "C1"}, "INVALID_ITEM"),
        ({"text": "secret medical"}, "MISSING_EVIDENCE"),
        ("secret medical", "INVALID_ITEM"),
        ({"text": " • - "}, "INVALID_ITEM"),
    ],
)
def test_invalid_recommendation_is_removed_whole(invalid, code):
    result = validate_report(report(uz_intern=[VALID, invalid]), EVIDENCE)
    assert result.section_payload()["uz_intern"] == [VALID]
    assert result.partial
    assert result.validationWarnings[0].code == code
    assert "secret medical" not in result.model_dump_json()


def test_missing_invalid_and_extra_sections():
    result = validate_report(
        {"uz_intern": [VALID], "nutritie": 3, "unknown medical name": []}, EVIDENCE
    )
    assert set(result.sections) == set(SECTIONS)
    assert {w.code for w in result.validationWarnings} == {
        "MISSING_SECTION",
        "INVALID_SECTION",
        "EXTRA_KEYS",
    }
    assert "unknown medical name" not in result.model_dump_json()


@pytest.mark.parametrize("nutrition", [[{"text": "Supă", "evidence_ids": []}], {"retete": "Supă"}])
def test_compatible_nutrition_does_not_mark_partial(nutrition):
    result = validate_report(report(nutritie=nutrition), EVIDENCE)
    assert not result.partial
    assert len(result.sections["nutritie"]) == 1


def test_structured_nutrition_rejects_mixed_ids():
    result = validate_report(
        report(
            uz_intern=[VALID],
            nutritie={"retete": [{"text": "secret", "evidence_ids": ["C1", "bad"]}]},
        ),
        EVIDENCE,
    )
    assert result.partial and not result.sections["nutritie"]


@pytest.mark.parametrize("value", [None, [], {}, report(), report(uz_intern=[{"text": "uncited"}])])
def test_complete_failure(value):
    with pytest.raises(ReportValidationError):
        validate_report(value, EVIDENCE)


def test_same_notice_and_filtered_content_in_chat_and_pdf():
    result = validate_report(
        report(uz_intern=[VALID, {"text": "ELIMINAT_SECRET", "evidence_ids": ["bad"]}]), EVIDENCE
    )
    chat = _recommendation_text(result, EVIDENCE)
    from backend.ai.conditions import ConditionDictionary

    with patch("backend.ai.conditions.load_dictionary", return_value=ConditionDictionary([])):
        pdf = create_pdf({"health_problem": "Test"}, result, EVIDENCE, 0)
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert partial_notice() in chat
    assert partial_notice() in text
    assert "ELIMINAT_SECRET" not in chat + text


def test_client_never_logs_report_or_evidence_even_with_old_debug_flags(caplog):
    from dataclasses import replace

    from backend.ai.client import XAIClient
    from backend.config import Settings

    client = XAIClient(replace(Settings(), log_ai_response_text=True, log_fragment_text=True))
    caplog.set_level("INFO", logger="naturist.ai")
    content = json.dumps(report(uz_intern=[{**VALID, "text": "SECRET_MEDICAL"}]))
    response = {
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}],
    }
    try:
        with patch.object(client, "_post") as post:
            post.return_value.json.return_value = response
            client.generate(
                {"health_problem": "SECRET_MEDICAL"},
                {"C1": {**EVIDENCE["C1"], "text": "SECRET_MEDICAL"}},
            )
        assert "SECRET_MEDICAL" not in caplog.text
    finally:
        client.close()
