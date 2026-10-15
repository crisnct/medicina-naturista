"""Exercise the real FIFO with blocked synthetic workers, without AI or a database."""

from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from backend.config import Settings
from backend.core.errors import ApplicationError
from backend.core.models import CommitChange, HealthProfile, PendingSearch, StoredReport
from backend.core.report_generation import ReportGenerationService
from backend.core.sessions import SessionStore


class ReportQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 100.0
        self.store = SessionStore(
            Path(self.temp.name), 3600, 14400, Settings(), clock=lambda: self.now
        )
        self.addCleanup(self.store.shutdown)
        self.service = ReportGenerationService(self.store)
        self.addCleanup(self.service.close)
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.started = threading.Event()
        self.lock = threading.Lock()
        self.order = []
        self.active = self.maximum_active = 0
        self.fail_first = False
        self.conversation = SimpleNamespace(
            ai=SimpleNamespace(context_budget=lambda: None), generate=self.generate
        )

    def session(self, tab):
        session = self.store.get("synthetic-cookie", tab, True, client_ip="synthetic-ip")
        op = self.store.begin_operation(session, "message")
        self.store.commit_operation(
            op, CommitChange(profile=HealthProfile(health_problem="synthetic"), new_context=True)
        )
        self.store.finish_operation(op)
        op = self.store.begin_operation(session, "search")
        self.store.commit_operation(
            op,
            CommitChange(
                search=("search", PendingSearch({}, {"C1": {"text": "synthetic"}})),
                messages=[{"kind": "generate", "role": "assistant", "searchId": "search"}],
            ),
        )
        self.store.finish_operation(op)
        return session

    def start(self, session, request_id="request"):
        return self.service.start(
            self.conversation, session, "search", 0, request_id, "synthetic-model"
        )

    def generate(self, session, search_id, min_score, *, admitted):
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.order.append(session.tab_id)
            first = len(self.order) == 1
        try:
            if first:
                self.started.set()
                if not self.release.wait(5):
                    raise AssertionError("Test did not release the first worker")
                if self.fail_first:
                    raise RuntimeError("Synthetic failure")
            self.store.checkpoint(admitted)
            return self.store.commit_operation(
                admitted,
                CommitChange(
                    report=("report", StoredReport(b"synthetic", "test.pdf", "synthetic"))
                ),
            )
        finally:
            with self.lock:
                self.active -= 1

    def finish(self):
        self.release.set()
        self.assertTrue(self.store.wait_workers(3), "Queue did not drain")

    def test_fifo_and_idempotent_admission_across_sessions(self):
        sessions = [self.session(str(i)) for i in range(3)]
        first = self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second, third = self.start(sessions[1]), self.start(sessions[2])
        duplicate = self.start(sessions[1])
        self.assertEqual(duplicate["jobId"], second["jobId"])
        self.assertEqual((second["stage"], second["queuePosition"]), ("queued", 1))
        self.assertEqual(third["queuePosition"], 2)
        self.assertEqual(self.order, ["0"])
        self.finish()
        self.assertEqual(self.order, ["0", "1", "2"])
        self.assertEqual(self.maximum_active, 1)
        for session, job in zip(sessions, [first, second, third]):
            status = self.service.generation(session, job["jobId"])
            self.assertEqual(status["state"], "succeeded")
            self.assertIsNone(status["queuePosition"])

    def test_cancelling_queued_job_removes_it_without_ai_call(self):
        sessions = [self.session(str(i)) for i in range(3)]
        self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second, third = self.start(sessions[1]), self.start(sessions[2])
        cancelled = self.service.generation(sessions[1], second["jobId"], cancel=True)
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertFalse(cancelled["workerActive"])
        self.assertEqual(self.service.generation(sessions[2], third["jobId"])["queuePosition"], 1)
        self.finish()
        self.assertEqual(self.order, ["0", "2"])

    def test_cancelled_active_worker_still_blocks_next_job(self):
        first_session, second_session = self.session("first"), self.session("second")
        first = self.start(first_session)
        self.assertTrue(self.started.wait(2))
        self.start(second_session)
        cancelled = self.service.generation(first_session, first["jobId"], cancel=True)
        self.assertTrue(cancelled["workerActive"])
        self.assertEqual(self.order, ["first"])
        self.finish()
        self.assertEqual(self.order, ["first", "second"])
        self.assertEqual(self.maximum_active, 1)

    def test_queue_full_is_explicit_and_cancel_releases_capacity(self):
        self.store.limits = replace(self.store.limits, max_queued_generations=1)
        sessions = [self.session(str(i)) for i in range(3)]
        self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second = self.start(sessions[1])
        with self.assertRaises(ApplicationError) as caught:
            self.start(sessions[2])
        self.assertEqual(
            (caught.exception.code, caught.exception.status), ("GENERATION_QUEUE_FULL", 429)
        )
        self.service.generation(sessions[1], second["jobId"], cancel=True)
        self.start(sessions[2])
        self.finish()
        self.assertEqual(self.order, ["0", "2"])

    def test_worker_failure_does_not_stall_queue(self):
        self.fail_first = True
        sessions = [self.session(str(i)) for i in range(2)]
        first = self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second = self.start(sessions[1])
        self.finish()
        self.assertEqual(self.service.generation(sessions[0], first["jobId"])["state"], "failed")
        self.assertEqual(
            self.service.generation(sessions[1], second["jobId"])["state"], "succeeded"
        )

    def test_queue_wait_does_not_consume_execution_timeout(self):
        sessions = [self.session(str(i)) for i in range(2)]
        first = self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second = self.start(sessions[1])
        self.now += self.store.limits.report_generation_timeout_seconds + 1
        self.assertEqual(self.service.generation(sessions[0], first["jobId"])["state"], "timed_out")
        self.assertEqual(self.service.generation(sessions[1], second["jobId"])["state"], "accepted")
        self.finish()
        self.assertEqual(
            self.service.generation(sessions[1], second["jobId"])["state"], "succeeded"
        )

    def test_closed_session_is_skipped_and_status_stays_private(self):
        sessions = [self.session(str(i)) for i in range(3)]
        self.start(sessions[0])
        self.assertTrue(self.started.wait(2))
        second = self.start(sessions[1])
        self.start(sessions[2])
        with self.assertRaises(ApplicationError) as caught:
            self.service.generation(sessions[2], second["jobId"], cancel=True)
        self.assertEqual(caught.exception.status, 404)
        self.store.delete("synthetic-cookie", "1")
        self.finish()
        self.assertEqual(self.order, ["0", "2"])


if __name__ == "__main__":
    unittest.main()
