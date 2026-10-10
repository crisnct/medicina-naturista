"""Deterministic session lifetime/capacity tests. No database, corpus, .env or AI."""

from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from backend.config import Settings
from backend.core.errors import ApplicationError, OperationCancelled
from backend.core.models import CommitChange, HealthProfile, PendingSearch, StoredReport
from backend.core.sessions import SessionStore, retained_usage, serialized_bytes


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 100.0
        self.config = replace(Settings(), max_sessions_per_ip=10)
        self.store = SessionStore(
            Path(self.temp.name), 60, 120, self.config, clock=lambda: self.now
        )
        self.addCleanup(self.store.shutdown)
        self.session = self.store.get("cookie", "tab", True, client_ip="ip")

    def commit(self, kind="message", **kwargs):
        op = self.store.begin_operation(self.session, kind)
        try:
            return self.store.commit_operation(op, CommitChange(**kwargs))
        finally:
            self.store.finish_operation(op)

    def search(self, text="Gripă", search_id="s"):
        profile = HealthProfile(health_problem=text)
        self.commit(
            profile=profile,
            new_context=True,
            messages=[{"kind": "text", "role": "user", "content": text}],
        )
        self.commit(
            "search",
            search=(
                search_id,
                PendingSearch(
                    profile.as_dict(), {"C1": {"text": text, "source": "synthetic:1"}}
                ),
            ),
            messages=[
                {
                    "kind": "fragments",
                    "role": "assistant",
                    "searchId": search_id,
                    "fragments": [{"text": text}],
                },
                {"kind": "generate", "role": "assistant", "searchId": search_id},
            ],
        )

    def test_close_clears_all_state_and_prevents_old_lifetime_commit(self):
        self.search()
        op = self.store.begin_operation(self.session, "generate", search_id="s")
        old = self.session
        self.store.delete("cookie", "tab")
        new = self.store.get("cookie", "tab", True, client_ip="ip")
        self.assertNotEqual(old.lifetime_id, new.lifetime_id)
        self.assertTrue(old.closed)
        self.assertEqual(old.profile.as_dict(), HealthProfile().as_dict())
        self.assertFalse(
            old.history
            or old.searches
            or old.reports
            or old.groups
            or old.selected_categories
        )
        result = self.store.commit_operation(
            op,
            CommitChange(
                messages=[{"kind": "download", "reportId": "late"}],
                report=("late", StoredReport(b"pdf", "x.pdf", "x")),
            ),
        )
        self.assertTrue(result.cancelled)
        self.assertFalse(old.history or old.reports or new.history or new.reports)
        with self.assertRaises(ApplicationError):
            self.store.history(old)
        self.assertIs(self.store.get("cookie", "tab"), new)
        self.store.finish_operation(op)
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)
        self.assertEqual(
            self.store.metrics()["retained_bytes"], retained_usage(new).total
        )

    def test_expiry_cancels_and_releases_reservations_once(self):
        self.search()
        op = self.store.begin_operation(self.session, "generate", search_id="s")
        self.now += 60
        self.store.sweep()
        self.store.sweep()
        self.store.delete("cookie", "tab")
        self.assertTrue(self.session.closed)
        self.assertTrue(op.cancellation.is_set())
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)
        self.assertEqual(self.store.metrics()["retained_bytes"], 0)
        self.store.finish_operation(op)
        self.store.finish_operation(op)
        self.assertEqual(self.store.metrics()["active_workers"], 0)

    def test_new_identical_message_invalidates_revision_not_just_text(self):
        self.search()
        op = self.store.begin_operation(self.session, "condition")
        snap = op.snapshot
        snap.profile.health_context.append("snapshot only")
        self.assertNotIn("snapshot only", self.session.profile.health_context)
        self.commit(profile=HealthProfile(health_problem="Gripă"), new_context=True)
        self.assertTrue(op.cancellation.is_set())
        self.assertTrue(
            self.store.commit_operation(
                op, CommitChange(messages=[{"content": "obsolete"}])
            ).cancelled
        )
        self.store.finish_operation(op)
        with self.assertRaises(OperationCancelled):
            self.store.begin_operation(self.session, "search", expected_revision=0)

    def test_old_search_uses_exact_snapshot_and_duplicate_is_409(self):
        self.search("Gripă")
        first = self.store.begin_operation(self.session, "generate", search_id="s")
        with self.assertRaises(ApplicationError) as caught:
            self.store.begin_operation(self.session, "generate", search_id="s")
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "GENERATION_IN_PROGRESS"),
        )
        self.commit(profile=HealthProfile(health_problem="Migrenă"), new_context=True)
        self.assertEqual(first.snapshot.search.profile["health_problem"], "Gripă")
        self.assertEqual(first.snapshot.search.evidence["C1"]["text"], "Gripă")
        self.assertFalse(
            self.store.commit_operation(
                first,
                CommitChange(
                    report=("r", StoredReport(b"pdf", "x.pdf", "Gripă")),
                    replace_search_id="s",
                ),
            ).cancelled
        )
        self.store.finish_operation(first)
        self.assertEqual(self.session.profile.health_problem, "Migrenă")
        self.assertEqual(self.session.reports["r"].health_problem, "Gripă")

    def test_cancelled_worker_holds_global_generation_slot_until_finished(self):
        self.search()
        first = self.store.begin_operation(self.session, "generate", search_id="s")
        self.store.delete("cookie", "tab")
        self.session = self.store.get("cookie", "new-tab", True, client_ip="ip")
        self.search(search_id="new")
        with self.assertRaises(ApplicationError) as caught:
            self.store.begin_operation(self.session, "generate", search_id="new")
        self.assertEqual(caught.exception.status, 429)
        self.store.finish_operation(first)
        op = self.store.begin_operation(self.session, "generate", search_id="new")
        self.store.finish_operation(op)

    def test_operations_return_only_their_messages(self):
        a = self.store.begin_operation(self.session, "email")
        b = self.store.begin_operation(self.session, "email")
        # These generic operations do not carry an email resource.
        a.kind = b.kind = "notice"
        first = self.store.commit_operation(
            a, CommitChange(messages=[{"content": "A"}])
        )
        second = self.store.commit_operation(
            b, CommitChange(messages=[{"content": "B"}])
        )
        self.assertEqual([m["content"] for m in first.messages], ["A"])
        self.assertEqual([m["content"] for m in second.messages], ["B"])
        self.store.finish_operation(a)
        self.store.finish_operation(b)

    def test_last_global_and_client_slots_are_atomic(self):
        self.store.delete("cookie", "tab")
        self.store.limits = replace(
            self.config, max_active_sessions=1, max_sessions_per_ip=1
        )
        barrier = threading.Barrier(8)

        def create(i):
            barrier.wait()
            try:
                return self.store.get(f"cookie{i}", f"tab{i}", True, client_ip="same")
            except ApplicationError as error:
                return error

        with ThreadPoolExecutor(8) as executor:
            results = list(executor.map(create, range(8)))
        self.assertEqual(sum(not isinstance(r, ApplicationError) for r in results), 1)
        self.assertEqual(self.store.count(), 1)
        winner = next(r for r in results if not isinstance(r, ApplicationError))
        events = copy.deepcopy(self.store.creation_limiter.events)
        for _ in range(12):
            self.assertIs(
                self.store.get(winner.cookie_id, winner.tab_id, True, client_ip="same"),
                winner,
            )
        self.assertEqual(events, self.store.creation_limiter.events)

    def test_close_sweep_commit_concurrent_no_deadlock_or_double_release(self):
        self.search()
        op = self.store.begin_operation(self.session, "generate", search_id="s")
        barrier = threading.Barrier(3)

        def run(action):
            barrier.wait()
            action()

        with ThreadPoolExecutor(3) as executor:
            futures = [
                executor.submit(run, action)
                for action in (
                    lambda: self.store.delete("cookie", "tab"),
                    self.store.sweep,
                    lambda: self.store.commit_operation(
                        op,
                        CommitChange(
                            report=("r", StoredReport(b"pdf", "x.pdf", "x")),
                            replace_search_id="s",
                        ),
                    ),
                )
            ]
            for future in futures:
                future.result(timeout=3)
        self.store.finish_operation(op)
        self.assertEqual(
            self.store.metrics(),
            {
                "active_sessions": 0,
                "retained_bytes": 0,
                "reserved_bytes": 0,
                "active_workers": 0,
            },
        )
        self.assertFalse(self.session.history or self.session.reports)

    def test_utf8_pdf_alias_and_exact_history_byte_boundary(self):
        self.assertEqual(serialized_bytes("ă"), '"ă"'.encode("utf-8").__len__())
        self.commit(messages=[{"kind": "text", "content": "ășț"}])
        exact = retained_usage(self.session).history
        self.store.limits = replace(self.config, max_history_bytes=exact)
        op = self.store.begin_operation(self.session, "notice")
        before = self.store.history(self.session)
        with self.assertRaises(ApplicationError):
            self.store.commit_operation(op, CommitChange(messages=[{"content": "x"}]))
        self.assertEqual(before, self.store.history(self.session))
        self.store.finish_operation(op)
        # The exact limit is accepted; one byte less rejects the unchanged group.
        self.store.limits = replace(self.config, max_history_bytes=exact - 1)
        op = self.store.begin_operation(self.session, "notice")
        with self.assertRaises(ApplicationError):
            self.store.commit_operation(op, CommitChange())
        self.store.finish_operation(op)
        self.store.limits = self.config
        self.commit(report=("pdf", StoredReport(b"12345", "x.pdf", "x")))
        self.assertEqual(retained_usage(self.session).pdf, 5)
        self.assertEqual(self.session.report_bytes, b"12345")
        self.assertEqual(
            self.store.metrics()["retained_bytes"], retained_usage(self.session).total
        )

    def test_count_retention_evicts_complete_oldest_group(self):
        for i in range(13):
            self.search(str(i), str(i))
        self.assertEqual(len(self.session.searches), 12)
        self.assertNotIn("0", self.session.searches)
        self.assertFalse(
            any(
                m.get("searchId") == "0" or m.get("content") == "0"
                for m in self.session.history
            )
        )
        self.assertEqual(
            self.store.metrics()["retained_bytes"], retained_usage(self.session).total
        )

    def test_rejected_large_result_does_not_apply_planned_evictions(self):
        self.search("old", "old")
        self.commit(
            profile=HealthProfile(health_problem="new"),
            new_context=True,
            messages=[{"content": "new"}],
        )
        before = self.store.history(self.session)
        self.store.limits = replace(self.config, max_pdf_bytes=10)
        op = self.store.begin_operation(self.session, "notice")
        with self.assertRaises(ApplicationError):
            self.store.commit_operation(
                op, CommitChange(report=("huge", StoredReport(b"x" * 11, "x.pdf", "x")))
            )
        self.store.finish_operation(op)
        self.assertEqual(before, self.store.history(self.session))
        self.assertIn("old", self.session.searches)
        self.assertEqual(self.session.reports, {})
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)

    def test_pdf_limit_and_limit_plus_one(self):
        self.store.limits = replace(self.config, max_pdf_bytes=5)
        self.commit(report=("r", StoredReport(b"12345", "x.pdf", "x")))
        before = self.store.history(self.session)
        with self.assertRaises(ApplicationError):
            self.commit(report=("r2", StoredReport(b"1", "x.pdf", "x")))
        self.assertEqual(list(self.session.reports), ["r"])
        self.assertEqual(before, self.store.history(self.session))

    def test_rate_keys_swept_after_120_seconds_and_rejection_does_not_grow(self):
        limiter = self.store.creation_limiter
        limiter.check(("ip:gone", 1))
        with self.assertRaises(ApplicationError):
            limiter.check(("ip:gone", 1))
        self.assertEqual(len(limiter.events["ip:gone"]), 1)
        self.now += 119
        limiter.sweep()
        self.assertIn("ip:gone", limiter.events)
        self.now += 1
        limiter.sweep()
        self.assertNotIn("ip:gone", limiter.events)

    def test_only_marked_directories_are_cleaned(self):
        foreign = Path(self.temp.name) / "foreign"
        foreign.mkdir()
        (foreign / "keep").write_text("keep")
        self.store.shutdown()
        replacement = SessionStore(Path(self.temp.name), 60, 120, self.config)
        self.addCleanup(replacement.shutdown)
        self.assertTrue((foreign / "keep").is_file())

    def test_operation_identity_and_returned_messages_are_isolated(self):
        operation = self.store.begin_operation(self.session, "notice")
        impostor = copy.copy(operation)
        impostor.cancellation = threading.Event()
        before = self.store.metrics()
        self.assertTrue(
            self.store.commit_operation(
                impostor, CommitChange(messages=[{"content": "fake"}])
            ).cancelled
        )
        self.store.finish_operation(impostor)
        self.assertEqual(self.store.metrics(), before)
        result = self.store.commit_operation(
            operation, CommitChange(messages=[{"content": "original"}])
        )
        result.messages[0]["content"] = "outside mutation"
        self.assertEqual(self.store.history(self.session)[0]["content"], "original")
        self.store.finish_operation(operation)

    def test_global_reservation_is_atomic_and_released_after_failure(self):
        self.store.limits = replace(
            self.config,
            max_global_bytes=self.config.max_session_bytes,
            operation_reservation_bytes=40 * 1024 * 1024,
        )
        other = self.store.get("other", "tab", True, client_ip="other")
        barrier = threading.Barrier(2)

        def begin(session):
            barrier.wait()
            try:
                return self.store.begin_operation(session, "notice")
            except ApplicationError as error:
                return error

        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(begin, (self.session, other)))
        winner = next(
            result for result in results if not isinstance(result, ApplicationError)
        )
        rejected = next(
            result for result in results if isinstance(result, ApplicationError)
        )
        self.assertEqual((rejected.status, rejected.code), (503, "GLOBAL_BUDGET"))
        self.assertFalse(self.session.history or other.history)
        self.store.finish_operation(winner)
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)
        retried = self.store.begin_operation(other, "notice")
        self.store.finish_operation(retried)

    def test_deadline_prevents_publication_and_releases_only_its_reservation(self):
        operation = self.store.begin_operation(self.session, "notice")
        self.now += 1
        # Keep the session alive; the operation deadline alone must invalidate it.
        operation.deadline = self.now
        self.store.get("cookie", "tab")
        with self.assertRaises(OperationCancelled):
            self.store.checkpoint(operation)
        self.assertFalse(self.session.closed)
        self.assertTrue(
            self.store.commit_operation(
                operation, CommitChange(messages=[{"content": "late"}])
            ).cancelled
        )
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)
        self.assertEqual(self.store.metrics()["active_workers"], 1)
        self.store.finish_operation(operation)

    def test_exact_evidence_limit_and_one_extra_utf8_byte(self):
        self.search()
        exact = retained_usage(self.session).evidence
        self.store.limits = replace(self.config, max_evidence_bytes=exact)
        self.commit("notice")
        before = copy.deepcopy(self.session.searches)
        changed = copy.deepcopy(self.session.searches["s"])
        changed.evidence["C1"]["text"] += "a"
        with self.assertRaises(ApplicationError):
            self.commit("search", search=("s", changed))
        self.assertEqual(self.session.searches, before)
        self.assertEqual(retained_usage(self.session).evidence, exact)
        self.assertEqual(self.store.metrics()["reserved_bytes"], 0)

    def test_active_email_pins_report_group_during_retention(self):
        self.commit(
            new_context=True,
            report=("old", StoredReport(b"12345", "old.pdf", "old")),
            messages=[{"kind": "download", "reportId": "old"}],
        )
        self.commit(new_context=True, messages=[{"content": "new"}])
        email = self.store.begin_operation(self.session, "email")
        self.assertNotEqual(email.snapshot.group_id, self.session.current_group_id)
        self.store.limits = replace(self.config, max_pdf_bytes=5)
        with self.assertRaises(ApplicationError):
            self.commit("notice", report=("new", StoredReport(b"1", "new.pdf", "new")))
        self.assertIn("old", self.session.reports)
        self.assertEqual(email.snapshot.report.data, b"12345")
        self.store.finish_operation(email)
        result = self.commit(
            "notice", report=("new", StoredReport(b"1", "new.pdf", "new"))
        )
        self.assertIn("old", result.evicted_report_ids)
        self.assertFalse(
            any(
                message.get("reportId") == "old"
                for message in self.store.history(self.session)
            )
        )

    def test_report_count_cap_removes_complete_groups(self):
        for index in range(13):
            self.commit(
                new_context=True,
                report=(str(index), StoredReport(b"pdf", "x.pdf", str(index))),
                messages=[
                    {"kind": "download", "reportId": str(index)},
                    {"content": str(index)},
                ],
            )
        self.assertEqual(len(self.session.reports), 12)
        self.assertNotIn("0", self.session.reports)
        self.assertFalse(
            any(
                message.get("reportId") == "0" or message.get("content") == "0"
                for message in self.store.history(self.session)
            )
        )

    def test_cookie_and_ip_last_slots_are_atomic_independently(self):
        self.store.delete("cookie", "tab")
        for cookie_limit in (True, False):
            with self.subTest(cookie_limit=cookie_limit):
                self.store.limits = replace(
                    self.config, max_sessions_per_cookie=1, max_sessions_per_ip=1
                )
                barrier = threading.Barrier(4)

                def create(index):
                    barrier.wait()
                    try:
                        return self.store.get(
                            "same" if cookie_limit else f"cookie{index}",
                            f"tab{index}",
                            True,
                            client_ip=f"ip{index}" if cookie_limit else "same",
                        )
                    except ApplicationError as error:
                        return error

                with ThreadPoolExecutor(4) as executor:
                    results = list(executor.map(create, range(4)))
                self.assertEqual(
                    sum(not isinstance(result, ApplicationError) for result in results),
                    1,
                )
                self.assertTrue(
                    all(
                        result.status == 429
                        for result in results
                        if isinstance(result, ApplicationError)
                    )
                )
                winner = next(
                    result
                    for result in results
                    if not isinstance(result, ApplicationError)
                )
                self.store.delete(winner.cookie_id, winner.tab_id)
