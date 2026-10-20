"""HTTP publication/retry contract using synthetic, isolated sessions."""

import io
from unittest.mock import patch

import pytest
from pypdf import PdfReader

from backend.ai.client import AIUnavailable
from backend.ai.index_state import IndexUnavailable
from backend.ai.report_validation import PARTIAL_NOTICE, SECTIONS
from backend.core.errors import ApplicationError
from tests.unit.web import test_web as support


@pytest.fixture
def web():
    test = support.WebTests()
    test.setUp()
    sid, tab = "I" * 43, "integrity-tab01"
    test.client.get("/api/session", headers=support._headers(sid, tab))
    messages = support._send(test.client, sid, tab, "Test", [])
    search = support._by_kind(messages, "generate")["searchId"]
    try:
        yield test, sid, tab, search
    finally:
        test.doCleanups()


@pytest.mark.parametrize("failure", [AIUnavailable("invalid JSON"), dict.fromkeys(SECTIONS, [])])
def test_failure_keeps_search_and_never_creates_pdf_or_retries(web, failure):
    test, sid, tab, search = web
    with (
        patch.object(
            test.deps.ai,
            "generate",
            side_effect=failure if isinstance(failure, Exception) else None,
            return_value=failure,
        ) as ai,
        patch.object(test.deps, "pdf") as pdf,
    ):
        response = support.post_report(
            test.client,
            f"/api/searches/{search}/generate",
            headers=support._headers(sid, tab, True),
        )
        assert response.status_code == 202
        assert not any(m["kind"] == "download" for m in response.json()["messages"])
        assert not response.json()["partial"]
        ai.assert_called_once()
        pdf.assert_not_called()
    session = test.deps.store.get(sid, tab)
    assert search in session.searches and not session.reports
    assert test.deps.store.metrics()["reserved_bytes"] == 0
    response = support.post_report(
        test.client, f"/api/searches/{search}/generate", headers=support._headers(sid, tab, True)
    )
    assert any(m["kind"] == "download" for m in response.json()["messages"])


def test_partial_publication_download_and_email_use_identical_pdf(web):
    test, sid, tab, search = web
    value = dict.fromkeys(SECTIONS, [])
    value["uz_intern"] = [
        {"text": "Valid", "evidence_ids": ["C1"]},
        {"text": "SECRET_INVALID", "evidence_ids": ["C1", "bad"]},
    ]
    with patch.object(test.deps.ai, "generate", return_value=value):
        response = support.post_report(
            test.client,
            f"/api/searches/{search}/generate",
            headers=support._headers(sid, tab, True),
        ).json()
    assert response["partial"]
    assert response["validationWarnings"][0]["code"] == "UNKNOWN_EVIDENCE"
    assert "SECRET_INVALID" not in str(response)
    assert PARTIAL_NOTICE in support._by_kind(response["messages"], "text")["content"]
    download = support._by_kind(response["messages"], "download")
    data = test.client.get(download["url"], headers=support._headers(sid, tab)).content
    assert PARTIAL_NOTICE in "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    with patch.object(test.deps, "email", return_value="ok") as email:
        first = test.client.post(
            "/api/messages",
            json={"message": "synthetic@example.com", "categories": []},
            headers=support._headers(sid, tab),
        ).json()
        test.client.post(
            "/api/classify",
            headers={
                **support._headers(sid, tab),
                "X-Context-Revision": str(first["contextRevision"]),
            },
        )
        assert email.call_args.args[1] == data


@pytest.mark.parametrize(
    "error", [IndexUnavailable(), ApplicationError("CATEGORY_SELECTION_STALE", "Reselect", 409)]
)
def test_controlled_index_and_stale_errors_are_http_errors(web, error):
    test, sid, tab, _search = web
    with patch.object(test.deps.retriever, "collect", side_effect=error):
        response = test.client.post("/api/search", headers=support._headers(sid, tab))
    assert response.status_code == error.status
    assert response.json()["detail"]["code"] == error.code
    if isinstance(error, IndexUnavailable):
        assert response.headers["Retry-After"] == "60"
