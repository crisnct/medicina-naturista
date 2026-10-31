"""HTTP model binding, strict score validation and receipt idempotency."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.web.main import _generate_report
from tests.unit.web import test_web as support


@pytest.fixture
def web():
    test = support.WebTests()
    test.setUp()
    writer = test.deps.record_report_metrics = Mock(return_value=1)
    test.deps.ai.provider = SimpleNamespace(model="gemma4:12b", reasoning_effort="medium")
    sid, tab = "M" * 43, "metrics-tab01"
    headers = support._headers(sid, tab, True)
    test.client.get("/api/session", headers=headers)
    messages = support._send(test.client, sid, tab, "Remedii naturiste pentru gripă", [])
    search = support._by_kind(messages, "generate")["searchId"]
    try:
        yield test, headers, search, writer
    finally:
        test.doCleanups()


def test_success_and_repeated_request_poll_download_do_not_duplicate(web):
    test, headers, search, writer = web
    url = f"/api/searches/{search}/generate"
    options = {
        "minScore": 0,
        "model": "ollama-gemma4:12b",
        "effort": "medium",
        "requestId": "metrics-request01",
    }
    first = support.post_report(test.client, url, json=options, headers=headers)
    assert first.json()["state"] == "succeeded"
    metrics = writer.call_args.args[0]
    assert metrics.ai_model == options["model"] and metrics.ai_effort == "medium"
    assert metrics.medical_condition == "Gripa"
    assert metrics.characters == sum(
        len(item["text"])
        for item in test.deps.store.get("M" * 43, "metrics-tab01")
        .searches[search]
        .evidence.values()
    )
    repeated = support.post_report(test.client, url, json=options, headers=headers)
    assert first.json()["jobId"] == repeated.json()["jobId"]
    for _ in range(2):
        test.client.get(f"/api/report-generations/{first.json()['jobId']}", headers=headers)
    download = support._by_kind(first.json()["messages"], "download")
    assert test.client.get(download["url"], headers=headers).status_code == 200
    writer.assert_called_once()
    options["requestId"] = "metrics-request02"
    assert (
        support.post_report(test.client, url, json=options, headers=headers).json()["state"]
        == "succeeded"
    )
    assert writer.call_count == 2


@pytest.mark.parametrize("score", [50.5, True, "50", -1, 101])
def test_fractional_or_invalid_score_is_http_422(web, score):
    test, headers, search, writer = web
    response = test.client.post(
        f"/api/searches/{search}/generate", json={"minScore": score}, headers=headers
    )
    assert response.status_code == 422
    writer.assert_not_called()


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_sync_helper_binds_catalog_choice_and_selected_client(web, effort):
    test, _, search, writer = web
    ai = support.FakeAI()
    ai.provider = SimpleNamespace(model="deepseek-flash")
    test.deps.report_clients = {"deepseek-flash": ai}
    expected_effort = effort
    result = _generate_report(
        test.deps,
        test.deps.store.get("M" * 43, "metrics-tab01"),
        search,
        0,
        "deepseek-flash",
        effort,
    )
    assert not result.cancelled
    metrics = writer.call_args.args[0]
    assert metrics.ai_model == "deepseek-flash" and metrics.ai_effort == expected_effort


def test_metrics_error_keeps_background_job_successful_and_downloadable(web):
    test, headers, search, writer = web
    writer.side_effect = RuntimeError("synthetic database failure")
    response = support.post_report(test.client, f"/api/searches/{search}/generate", headers=headers)
    assert response.json()["state"] == "succeeded"
    download = support._by_kind(response.json()["messages"], "download")
    assert test.client.get(download["url"], headers=headers).status_code == 200
    writer.assert_called_once()


def test_queued_report_keeps_model_effort_and_search_from_admission(web):
    test, headers, search, writer = web
    test.deps.pdf = Mock(return_value=b"synthetic queue PDF")
    entered, release = threading.Event(), threading.Event()
    original_generate = test.deps.ai.generate

    def blocked_generate(*args):
        entered.set()
        assert release.wait(5)
        return original_generate(*args)

    test.deps.ai.generate = Mock(side_effect=blocked_generate)
    queued_ai = support.FakeAI()
    queued_ai.provider = SimpleNamespace(model="qwen3.5:4b")
    test.deps.report_clients = {
        "ollama-gemma4:12b": test.deps.ai,
        "ollama-qwen3.5:4b": queued_ai,
    }
    try:
        first = test.client.post(
            f"/api/searches/{search}/generate",
            json={"model": "ollama-gemma4:12b"},
            headers=headers,
        )
        assert first.status_code == 202 and entered.wait(2)
        second_headers = support._headers("M" * 43, "metrics-tab02", True)
        test.client.get("/api/session", headers=second_headers)
        messages = support._send(test.client, "M" * 43, "metrics-tab02", "Raceala", [])
        second_search = support._by_kind(messages, "generate")["searchId"]
        second = test.client.post(
            f"/api/searches/{second_search}/generate",
            json={"model": "ollama-qwen3.5:4b", "effort": "medium"},
            headers=second_headers,
        )
        assert second.status_code == 202 and second.json()["queuePosition"] == 1
        assert second.json()["effort"] == "medium"
        test.deps.store.get("M" * 43, "metrics-tab02").profile.health_problem = "Changed"
    finally:
        release.set()
        assert test.deps.store.wait_workers(3)
    assert writer.call_count == 2
    metrics = writer.call_args.args[0]
    assert metrics.medical_condition == "Raceala"
    assert metrics.ai_model == "ollama-qwen3.5:4b" and metrics.ai_effort == "medium"
