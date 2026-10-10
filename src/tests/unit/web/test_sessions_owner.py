"""HTTP races, owner revocation and streaming limits, using synthetic dependencies."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.ai.conditions import ConditionDictionary, parse_conditions
from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.models import OperationResult
from backend.core.owner_auth import OwnerAuth
from backend.core.rate_limits import RateLimiter
from backend.core.sessions import SessionStore
from backend.web.access_logs import OwnerAccessLogFilter
from backend.web.dependencies import Dependencies
from backend.web.main import COOKIE, OWNER_COOKIE, create_app
from tests.support.conditions import conditions_jsonl
from tests.support.owners import FakeOwnerRepository


class FakeAI:
    def __init__(self):
        self.calls = 0
        self.entered = None
        self.release = None
        self.closed = False

    def context_budget(self):
        return 1000

    def generate(self, profile, evidence):
        self.calls += 1
        if self.entered:
            self.entered.set()
            if not self.release.wait(5):
                raise AssertionError("test worker never released")
        return {
            "uz_intern": [{"text": "synthetic recommendation", "evidence_ids": ["C1"]}],
            "nutritie": [],
            "uz_extern": [],
            "atentionari": [],
            "alte_recomandari": [],
        }

    def close(self):
        self.closed = True


class FakeRetriever:
    document_count = 1
    category_tree = None

    def collect(self, snapshot, max_chars=None):
        return {
            "C1": {
                "source": "documents/synthetic.md:1",
                "text": snapshot.profile.health_problem,
                "score": 1.0,
                "relevance_percent": 100.0,
            }
        }


class HTTPPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = replace(
            Settings(),
            owner_key="owner synthetic secret",
            condition_ai_backends=(),
            max_requests_per_minute=200,
        )
        self.repo = FakeOwnerRepository()
        self.deps = self.dependencies(self.config, self.repo)
        self.client = TestClient(
            create_app(self.config, self.deps), base_url="https://testserver"
        )
        self.addCleanup(self.client.close)
        self.addCleanup(self.deps.store.shutdown)
        dictionary = ConditionDictionary(
            parse_conditions(conditions_jsonl("Gripă,gripa\nMigrenă,migrena\n"))
        )
        patcher = patch(
            "backend.ai.conditions.load_dictionary", return_value=dictionary
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tab = {"X-Tab-Id": "tab-synthetic"}
        self.origin = {"Origin": "https://testserver"}

    def dependencies(self, config, repo):
        root = Path(self.temp.name) / secrets.token_hex(6)
        return Dependencies(
            config,
            SessionStore(
                root, config.session_idle_seconds, config.session_max_seconds, config
            ),
            FakeRetriever(),
            FakeAI(),
            OwnerAuth(config.owner_key, repo),
            RateLimiter(),
            RateLimiter(),
            secrets.token_bytes(32),
            pdf=lambda *args: b"%PDF-synthetic",
        )

    def login(self, client=None):
        client = client or self.client
        status = client.get("/api/owner").json()
        response = client.post(
            "/api/owner/login",
            json={"key": self.config.owner_key},
            headers={**self.origin, "X-CSRF-Token": status["csrfToken"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return client.cookies.get(OWNER_COOKIE)

    def search(self, text="Gripă"):
        self.assertEqual(
            self.client.get("/api/session", headers=self.tab).status_code, 200
        )
        first = self.client.post(
            "/api/messages", json={"message": text}, headers=self.tab
        ).json()
        response = self.client.post(
            "/api/search",
            headers={**self.tab, "X-Context-Revision": str(first["contextRevision"])},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return next(
            m["searchId"]
            for m in response.json()["messages"]
            if m["kind"] == "generate"
        )

    def test_first_session_request_bootstraps_cookie_in_one_round_trip(self):
        response = self.client.get("/api/session", headers=self.tab)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.cookies.get(COOKIE))
        self.assertEqual(self.deps.store.count(), 1)

    def test_public_https_origin_works_over_internal_http_for_chat_and_owner(self):
        config = replace(self.config, public_origin="https://public.example")
        deps = self.dependencies(config, self.repo)
        self.addCleanup(deps.store.shutdown)
        with TestClient(
            create_app(config, deps), base_url="http://internal:7860"
        ) as client:
            self.assertEqual(
                client.get("/api/session", headers=self.tab).status_code, 200
            )
            response = client.post(
                "/api/messages",
                json={"message": "Gripă"},
                headers={**self.tab, "Origin": "https://public.example"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            csrf = client.get("/api/owner").json()["csrfToken"]
            login = client.post(
                "/api/owner/login",
                json={"key": config.owner_key},
                headers={"Origin": "https://public.example:443", "X-CSRF-Token": csrf},
            )
            self.assertEqual(login.status_code, 200, login.text)
            status = client.get("/api/owner").json()
            self.assertTrue(status["authorized"])
            logout = client.post(
                "/api/owner/logout",
                headers={
                    "Referer": "https://public.example/medicina/",
                    "X-CSRF-Token": status["csrfToken"],
                },
            )
            self.assertEqual(logout.status_code, 200, logout.text)

    def test_configured_public_origin_rejects_foreign_origins_and_forged_headers(self):
        self.deps.settings = replace(
            self.config, public_origin="https://public.example"
        )
        self.client.get("/api/session", headers=self.tab)
        for origin in (
            "https://evil.example",
            "http://public.example",
            "https://public.example:444",
            "https://public.example/path",
            "https://[invalid",
            "null",
            "https://user@public.example",
        ):
            with self.subTest(origin=origin):
                response = self.client.post(
                    "/api/messages",
                    json={"message": "synthetic"},
                    headers={
                        **self.tab,
                        "Origin": origin,
                        "X-Forwarded-Host": "public.example",
                        "X-Forwarded-Proto": "https",
                    },
                )
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.deps.ai.calls, 0)

    def test_signed_tokens_restart_logout_copied_cookie_and_key_rotation(self):
        token = self.login()
        self.assertTrue(self.deps.owner_auth.authorized(token))
        self.assertNotIn(token, repr(self.repo.rows))
        self.assertNotIn(self.config.owner_key, repr(self.repo.rows))
        restarted = self.dependencies(self.config, self.repo)
        self.addCleanup(restarted.store.shutdown)
        with TestClient(
            create_app(self.config, restarted), base_url="https://testserver"
        ) as client:
            client.cookies.set(OWNER_COOKIE, token)
            status = client.get("/api/owner")
            self.assertTrue(status.json()["authorized"])
            response = client.post(
                "/api/owner/logout",
                headers={**self.origin, "X-CSRF-Token": status.json()["csrfToken"]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(restarted.owner_auth.authorized(token))
            self.assertFalse(self.deps.owner_auth.authorized(token))
            client.cookies.set(OWNER_COOKIE, token)
            self.assertFalse(client.get("/api/owner").json()["authorized"])
        token2 = self.deps.owner_auth.login(self.config.owner_key)
        rotated = OwnerAuth("new synthetic key", self.repo)
        self.assertFalse(rotated.authorized(token2))
        legacy = hmac.new(
            self.config.owner_key.encode(), b"naturist-owner", hashlib.sha256
        ).hexdigest()
        self.assertFalse(self.deps.owner_auth.authorized(legacy))
        altered = token2[:-1] + ("0" if token2[-1] != "0" else "1")
        self.assertFalse(self.deps.owner_auth.authorized(altered))

    def test_query_key_rejects_missing_wrong_or_oversized_secret_without_echo(self):
        for key in ("", "wrong-secret", "sensitive" * 1000):
            response = self.client.get(
                "/owner", params={"key": key}, follow_redirects=False
            )
            self.assertEqual(response.status_code, 404)
            if key:
                self.assertNotIn(key, response.text)
        self.assertNotIn(OWNER_COOKIE + "=", response.headers.get("set-cookie", ""))
        self.assertFalse(self.repo.rows)

    def test_query_key_authorizes_redirects_without_key_and_rotation_revokes_copy(self):
        response = self.client.get(
            "/owner", params={"key": self.config.owner_key}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(response.headers["location"], "/")
        self.assertNotIn(
            self.config.owner_key, response.text + response.headers["location"]
        )
        token = self.client.cookies.get(OWNER_COOKIE)
        self.assertTrue(self.deps.owner_auth.authorized(token))
        self.assertNotIn(token, repr(self.repo.rows))
        self.assertIn("Max-Age=31536000", response.headers["set-cookie"])
        renewed = self.client.get(
            "/owner", params={"key": self.config.owner_key}, follow_redirects=False
        )
        self.assertEqual(renewed.status_code, 303)
        new_token = self.client.cookies.get(OWNER_COOKIE)
        self.assertNotEqual(new_token, token)
        self.assertFalse(self.deps.owner_auth.authorized(token))
        csrf = self.client.get("/api/owner").json()["csrfToken"]
        logout = self.client.post(
            "/api/owner/logout", headers={**self.origin, "X-CSRF-Token": csrf}
        )
        self.assertEqual(logout.status_code, 200)
        self.assertFalse(self.deps.owner_auth.authorized(new_token))

    def test_query_key_respects_prefix_and_https_cookie_flags(self):
        config = replace(
            self.config,
            public_root_path="/medicina",
            cookie_secure=True,
            public_origin="https://public.example",
        )
        deps = self.dependencies(config, self.repo)
        self.addCleanup(deps.store.shutdown)
        with TestClient(
            create_app(config, deps), base_url="https://public.example"
        ) as client:
            response = client.get(
                "/medicina/owner",
                params={"key": config.owner_key},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/medicina/")
            cookie = response.headers["set-cookie"]
            for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/medicina"):
                self.assertIn(flag, cookie)
            self.assertTrue(client.get("/medicina/api/owner").json()["authorized"])

    def test_legacy_root_cookie_is_removed_when_authorizing_scoped_owner(self):
        config = replace(self.config, public_root_path="/medicina", cookie_secure=True)
        deps = self.dependencies(config, self.repo)
        self.addCleanup(deps.store.shutdown)
        client = TestClient(create_app(config, deps), base_url="https://testserver")
        self.addCleanup(client.close)
        client.cookies.set(
            OWNER_COOKIE, "legacy-owner", domain="testserver.local", path="/"
        )
        response = client.get(
            "/medicina/owner", params={"key": config.owner_key}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            [
                cookie.path
                for cookie in client.cookies.jar
                if cookie.name == OWNER_COOKIE
            ],
            ["/medicina"],
        )
        self.assertTrue(client.get("/medicina/api/owner").json()["authorized"])

    def test_duplicate_owner_cookies_preserve_generation_authorization_and_revocation(
        self,
    ):
        token = self.login()
        search_id = self.search()
        for cookies in (
            f"{OWNER_COOKIE}={token}; {OWNER_COOKIE}=legacy-owner",
            f"{OWNER_COOKIE}=legacy-owner; {OWNER_COOKIE}={token}",
        ):
            with self.subTest(order=cookies.startswith(OWNER_COOKIE + "=legacy")):
                headers = {
                    **self.tab,
                    "Cookie": f"{COOKIE}={self.client.cookies.get(COOKIE)}; {cookies}",
                }
                with patch(
                    "backend.web.main._generate_report", return_value=OperationResult()
                ) as generate:
                    response = self.client.post(
                        f"/api/searches/{search_id}/generate", headers=headers
                    )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNone(response.json()["ownerNotice"])
                generate.assert_called_once()
        csrf = self.client.get("/api/owner").json()["csrfToken"]
        cookies = f"{OWNER_COOKIE}={token}; {OWNER_COOKIE}=legacy-owner; naturist_owner_csrf={csrf}"
        logout = self.client.post(
            "/api/owner/logout",
            headers={**self.origin, "X-CSRF-Token": csrf, "Cookie": cookies},
        )
        self.assertEqual(logout.status_code, 200, logout.text)
        self.assertFalse(self.deps.owner_auth.authorized(token))

    def test_query_key_has_shared_login_limit_and_rejects_cross_site_navigation(self):
        cross_site = self.client.get(
            "/owner",
            params={"key": self.config.owner_key},
            headers={"Sec-Fetch-Site": "cross-site"},
            follow_redirects=False,
        )
        self.assertEqual(cross_site.status_code, 403)
        self.assertFalse(self.repo.rows)
        for _ in range(4):
            response = self.client.get(
                "/owner", params={"key": "wrong"}, follow_redirects=False
            )
            self.assertEqual(response.status_code, 404)
        sixth = self.client.get(
            "/owner", params={"key": self.config.owner_key}, follow_redirects=False
        )
        self.assertEqual(sixth.status_code, 429)
        self.assertFalse(self.repo.rows)

    def test_csrf_missing_invalid_cross_origin_and_sixth_attempt(self):
        csrf = self.client.get("/api/owner").json()["csrfToken"]

        def login(headers, key="wrong"):
            return self.client.post(
                "/api/owner/login", json={"key": key}, headers=headers
            )

        self.assertEqual(login(self.origin).status_code, 403)
        self.assertEqual(
            login({**self.origin, "X-CSRF-Token": "invalid"}).status_code, 403
        )
        self.assertEqual(
            login({"Origin": "https://evil.test", "X-CSRF-Token": csrf}).status_code,
            403,
        )
        self.assertEqual(login({"X-CSRF-Token": csrf}).status_code, 403)
        self.assertEqual(login({**self.origin, "X-CSRF-Token": csrf}).status_code, 401)
        self.assertEqual(
            login(
                {**self.origin, "X-CSRF-Token": csrf}, self.config.owner_key
            ).status_code,
            429,
        )
        self.assertFalse(self.repo.rows)
        # Session creation has its own windows and is still allowed.
        self.assertEqual(
            self.client.get("/api/session", headers=self.tab).status_code, 200
        )

    def test_logout_fails_closed_when_csrf_or_repository_unavailable(self):
        token = self.login()
        self.assertEqual(
            self.client.post("/api/owner/logout", headers=self.origin).status_code, 403
        )
        self.assertTrue(self.deps.owner_auth.authorized(token))
        csrf = self.client.get("/api/owner").json()["csrfToken"]
        with patch.object(
            self.repo,
            "revoke",
            side_effect=ApplicationError("OWNER_AUTH_UNAVAILABLE", "temporar", 503),
        ):
            response = self.client.post(
                "/api/owner/logout", headers={**self.origin, "X-CSRF-Token": csrf}
            )
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("Max-Age=0", response.headers.get("set-cookie", ""))
        with patch.object(
            self.repo,
            "active",
            side_effect=ApplicationError("OWNER_AUTH_UNAVAILABLE", "temporar", 503),
        ):
            self.assertEqual(self.client.get("/api/owner").status_code, 503)

    def test_cookie_flags_prefix_and_activity_renewal(self):
        for prefix, secure in (("", False), ("/medicina", True)):
            config = replace(self.config, public_root_path=prefix, cookie_secure=secure)
            deps = self.dependencies(config, self.repo)
            self.addCleanup(deps.store.shutdown)
            with TestClient(
                create_app(config, deps), base_url="https://testserver"
            ) as client:
                csrf = client.get(prefix + "/api/owner").json()["csrfToken"]
                response = client.post(
                    prefix + "/api/owner/login",
                    json={"key": config.owner_key},
                    headers={**self.origin, "X-CSRF-Token": csrf},
                )
                self.assertEqual(response.status_code, 200, response.text)
                cookie = response.headers["set-cookie"]
                self.assertIn("Max-Age=31536000", cookie)
                self.assertIn("HttpOnly", cookie)
                self.assertIn("SameSite=strict", cookie)
                self.assertIn("Path=" + (prefix or "/"), cookie)
                self.assertEqual("Secure" in cookie, secure)
                renewed = client.get(prefix + "/api/owner")
                self.assertTrue(renewed.json()["authorized"])
                self.assertIn("Max-Age=31536000", renewed.headers["set-cookie"])

    def test_login_validation_does_not_echo_input_and_access_logs_redact_query(self):
        csrf = self.client.get("/api/owner").json()["csrfToken"]
        secret = "sensitive" * 1000
        response = self.client.post(
            "/api/owner/login",
            json={"key": secret},
            headers={**self.origin, "X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)
        record = logging.LogRecord(
            "uvicorn.access",
            20,
            "",
            0,
            '%s "%s %s HTTP/%s" %d',
            ("peer", "GET", "/medicina/owner?key=private-key", "1.1", 200),
            None,
        )
        OwnerAccessLogFilter().filter(record)
        self.assertNotIn("private-key", record.getMessage())

    def test_body_limit_checks_actual_stream_with_no_or_false_length(self):
        self.deps.settings = replace(self.config, max_api_body_bytes=100)
        for headers in ({}, {"Content-Length": "1"}):
            response = self.client.post(
                "/api/messages",
                content=iter([b"x" * 50, b"x" * 51]),
                headers={**self.tab, **headers},
            )
            self.assertEqual(response.status_code, 413, response.text)
        response = self.client.post(
            "/api/messages", content=b"x" * 101, headers=self.tab
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.deps.store.count(), 0)

    def test_untrusted_xff_cannot_bypass_session_ip_cap(self):
        self.client.get(
            "/api/session", headers={**self.tab, "X-Forwarded-For": "1.2.3.4"}
        )
        other = self.client.get(
            "/api/session",
            headers={"X-Tab-Id": "other-tab", "X-Forwarded-For": "5.6.7.8"},
        )
        self.assertEqual(other.status_code, 429)
        self.assertEqual(other.json()["detail"]["code"], "SESSION_ALREADY_ACTIVE")
        self.assertEqual(self.deps.store.count(), 1)

    def test_other_tab_and_other_browser_are_blocked_without_closing_first_session(
        self,
    ):
        first = self.client.get("/api/session", headers=self.tab)
        self.assertEqual(first.status_code, 200)
        for different_browser in (False, True):
            with self.subTest(different_browser=different_browser):
                other = TestClient(
                    create_app(self.config, self.deps), base_url="https://testserver"
                )
                self.addCleanup(other.close)
                if not different_browser:
                    other.cookies.update(self.client.cookies)
                headers = {"X-Tab-Id": "second-tab"}
                blocked = other.get("/api/session", headers=headers)
                self.assertEqual(blocked.status_code, 429)
                self.assertEqual(
                    blocked.json()["detail"]["code"], "SESSION_ALREADY_ACTIVE"
                )
                self.assertIn(
                    "alt tab sau browser", blocked.json()["detail"]["message"]
                )
                self.assertEqual(
                    other.post("/api/session/unload", headers=headers).status_code, 204
                )
                self.assertEqual(self.deps.store.count(), 1)
                self.assertEqual(
                    self.client.get("/api/session", headers=self.tab).status_code, 200
                )
        self.client.post("/api/session/unload", headers=self.tab)
        self.assertEqual(self.deps.store.count(), 0)
        other = TestClient(
            create_app(self.config, self.deps), base_url="https://testserver"
        )
        self.addCleanup(other.close)
        self.assertEqual(
            other.get("/api/session", headers={"X-Tab-Id": "second-tab"}).status_code,
            200,
        )

    def test_different_ips_can_use_the_chat_at_the_same_time(self):
        clients = []
        for address in ("192.0.2.10", "192.0.2.11"):
            client = TestClient(
                create_app(self.config, self.deps),
                base_url="https://testserver",
                client=(address, 10000),
            )
            self.addCleanup(client.close)
            clients.append(client)
            self.assertEqual(
                client.get("/api/session", headers=self.tab).status_code, 200
            )
        self.assertEqual(self.deps.store.count(), 2)

    def test_generate_blocked_then_close_and_recreate_drops_pdf_and_links(self):
        self.login()
        sid = self.search()
        ai = self.deps.ai
        ai.entered = threading.Event()
        ai.release = threading.Event()
        old = self.deps.store.get(self.client.cookies.get(COOKIE), self.tab["X-Tab-Id"])
        with ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                self.client.post, f"/api/searches/{sid}/generate", headers=self.tab
            )
            try:
                self.assertTrue(ai.entered.wait(3))
                self.assertEqual(
                    self.client.post("/api/session/end", headers=self.tab).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get("/api/session", headers=self.tab).status_code, 200
                )
                new = self.deps.store.get(
                    self.client.cookies.get(COOKIE), self.tab["X-Tab-Id"]
                )
                self.assertNotEqual(old.lifetime_id, new.lifetime_id)
            finally:
                ai.release.set()
            result = future.result(timeout=3)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["cancelled"])
        self.assertEqual(result.json()["messages"], [])
        self.assertFalse(old.reports or old.history or new.reports)

    def test_duplicate_generation_is_409_before_second_ai_call(self):
        self.login()
        sid = self.search()
        ai = self.deps.ai
        ai.entered = threading.Event()
        ai.release = threading.Event()
        with ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                self.client.post, f"/api/searches/{sid}/generate", headers=self.tab
            )
            try:
                self.assertTrue(ai.entered.wait(3))
                duplicate = self.client.post(
                    f"/api/searches/{sid}/generate", headers=self.tab
                )
                self.assertEqual(duplicate.status_code, 409, duplicate.text)
                self.assertEqual(ai.calls, 1)
            finally:
                ai.release.set()
            self.assertEqual(future.result(timeout=3).status_code, 200)

    def test_new_message_during_search_discards_stale_result(self):
        self.client.get("/api/session", headers=self.tab)
        first = self.client.post(
            "/api/messages", json={"message": "Gripă"}, headers=self.tab
        ).json()
        entered, release = threading.Event(), threading.Event()

        def blocked(snapshot, max_chars=None):
            entered.set()
            self.assertTrue(release.wait(5))
            return FakeRetriever().collect(snapshot, max_chars)

        with (
            patch.object(self.deps.retriever, "collect", side_effect=blocked),
            ThreadPoolExecutor(1) as executor,
        ):
            future = executor.submit(
                self.client.post,
                "/api/search",
                headers={
                    **self.tab,
                    "X-Context-Revision": str(first["contextRevision"]),
                },
            )
            try:
                self.assertTrue(entered.wait(3))
                newer = self.client.post(
                    "/api/messages", json={"message": "Migrenă"}, headers=self.tab
                )
                self.assertEqual(newer.status_code, 200, newer.text)
            finally:
                release.set()
            result = future.result(timeout=3).json()
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["messages"], [])
        stale = self.client.post(
            "/api/search",
            headers={**self.tab, "X-Context-Revision": str(first["contextRevision"])},
        ).json()
        self.assertTrue(stale["cancelled"])

    def test_email_close_discards_confirmation_after_external_send(self):
        self.login()
        sid = self.search()
        self.client.post(f"/api/searches/{sid}/generate", headers=self.tab)
        entered, release = threading.Event(), threading.Event()

        def email(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return "sent"

        self.deps.email = email
        with ThreadPoolExecutor(1) as executor:
            future = executor.submit(
                self.client.post,
                "/api/messages",
                json={"message": "synthetic@example.test"},
                headers=self.tab,
            )
            try:
                self.assertTrue(entered.wait(3))
                self.client.post("/api/session/end", headers=self.tab)
            finally:
                release.set()
            result = future.result(timeout=3).json()
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["messages"], [])
