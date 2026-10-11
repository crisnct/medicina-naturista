"""Deadline propagation uses deterministic clocks and synthetic HTTP responses."""

import unittest
from dataclasses import replace
from unittest.mock import Mock

import httpx

from backend.ai.client import ResponsesClient, _collect_stream
from backend.ai.providers import provider_config
from backend.config import Settings
from backend.core.errors import OperationCancelled
from backend.core.operation_context import OperationBudget, operation_budget, remaining_timeout


class OperationContextTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.budget = OperationBudget(110.0, lambda: self.now, lambda: None)

    def test_nested_deadlines_restore_parent_and_exception_restores_default(self):
        with operation_budget(self.budget):
            self.assertEqual(remaining_timeout(300), 10)
            with self.assertRaisesRegex(ValueError, "synthetic"):
                with operation_budget(OperationBudget(103.0, lambda: self.now, lambda: None)):
                    self.assertEqual(remaining_timeout(300), 3)
                    raise ValueError("synthetic")
            self.assertEqual(remaining_timeout(300), 10)
        self.assertEqual(remaining_timeout(300), 300)

    def test_http_timeout_is_bounded_and_late_response_is_not_returned(self):
        config = replace(Settings(), ai_stream=False)
        client = ResponsesClient(provider_config(config), config)
        self.addCleanup(client.close)
        response = httpx.Response(200, json={"status": "completed"})
        client.http.post = Mock(return_value=response)
        with operation_budget(self.budget):
            self.assertIs(client._send({}, {}), response)
            timeout = client.http.post.call_args.kwargs["timeout"]
            self.assertEqual(timeout.read, 10)
            self.assertEqual(timeout.connect, 10)
            self.now = 108
            client._send({}, {})
            self.assertEqual(client.http.post.call_args.kwargs["timeout"].read, 2)

            def delayed_response(*args, **kwargs):
                self.now = 110
                return response

            client.http.post.side_effect = delayed_response
            with self.assertRaises(OperationCancelled):
                client._send({}, {})
            # Restore the clock before leaving the enclosing context.
            self.now = 109

    def test_stream_heartbeats_cannot_keep_an_expired_operation_alive(self):
        def heartbeats():
            yield ": heartbeat"
            self.now = 110
            yield ": another heartbeat"
            self.fail("stream consumed after deadline")

        with self.assertRaises(OperationCancelled), operation_budget(self.budget):
            _collect_stream(heartbeats())

    def test_cancelled_checkpoint_prevents_starting_io(self):
        def cancelled():
            raise OperationCancelled()

        with self.assertRaises(OperationCancelled):
            with operation_budget(OperationBudget(110, lambda: self.now, cancelled)):
                self.fail("cancelled operation entered I/O scope")
