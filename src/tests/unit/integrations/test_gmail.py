"""Unit tests for Gmail API report delivery."""
from __future__ import annotations

import base64
import io
import json
import os
import unittest
from email import message_from_bytes
from unittest.mock import patch
from urllib.error import HTTPError

from backend.integrations.gmail import (
    EMAIL_SENT,
    EMAIL_SKIPPED,
    GMAIL_SEND_SCOPE,
    GMAIL_SEND_URI,
    GMAIL_TOKEN_URI,
    MailConfig,
    build_report_message,
    load_mail_config,
    send_report,
)


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class RecordingUrlopen:
    def __init__(self):
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if len(self.calls) == 1:
            return FakeHTTPResponse({"access_token": "access-token"})
        return FakeHTTPResponse({"id": "gmail-message-id"})


class MailerTests(unittest.TestCase):
    def test_build_report_message_has_headers_and_pdf_attachment(self):
        message = build_report_message(
            "Gripă și răceală",
            b"%PDF-test",
            "Raport gripă.pdf",
            "reports@gmail.com",
            "dest@example.com",
        )

        self.assertEqual(message["To"], "dest@example.com")
        self.assertEqual(message["From"], "reports@gmail.com")
        self.assertEqual(message["Subject"], "Raport recomandări naturiste pentru Gripă și răceală")
        attachment = next(message.iter_attachments())
        self.assertEqual(attachment.get_content_type(), "application/pdf")
        self.assertEqual(attachment.get_filename(), "Raport gripă.pdf")
        self.assertEqual(attachment.get_payload(decode=True), b"%PDF-test")

    def test_oauth_configuration_is_read_and_missing_config_is_skipped(self):
        with patch.dict(
            os.environ,
            {
                "MAIL_FROM": "reports@gmail.com",
                "GMAIL_USERNAME": "username@gmail.com",
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
                "GOOGLE_REFRESH_TOKEN": "refresh-token",
            },
        ):
            config = load_mail_config()

        self.assertTrue(config.is_configured)
        self.assertEqual(config.from_address, "reports@gmail.com")
        self.assertEqual(config.username, "username@gmail.com")
        self.assertEqual(config.client_id, "client-id")
        self.assertEqual(config.client_secret, "client-secret")
        self.assertEqual(config.refresh_token, "refresh-token")

        with patch.dict(
            os.environ,
            {
                "MAIL_FROM": "",
                "GMAIL_USERNAME": "username@gmail.com",
                "GOOGLE_CLIENT_ID": "",
                "GOOGLE_CLIENT_SECRET": "",
                "GOOGLE_REFRESH_TOKEN": "",
            },
        ):
            result = send_report("Gripă", b"%PDF-test", "raport.pdf", "dest@example.com", urlopen_factory=RecordingUrlopen())
        self.assertEqual(result, EMAIL_SKIPPED)

    def test_send_report_refreshes_token_and_sends_mime_message_once(self):
        config = MailConfig(
            from_address="reports@gmail.com",
            username="username@gmail.com",
            client_id="client-id",
            client_secret="client-secret",
            refresh_token="refresh-token",
        )
        opener = RecordingUrlopen()

        result = send_report(
            "Gripă",
            b"%PDF-test",
            "raport.pdf",
            "dest@example.com",
            config=config,
            urlopen_factory=opener,
        )

        self.assertEqual(result, EMAIL_SENT)
        self.assertEqual(len(opener.calls), 2)
        token_request, token_timeout = opener.calls[0]
        send_request, send_timeout = opener.calls[1]
        self.assertEqual(token_request.full_url, GMAIL_TOKEN_URI)
        self.assertEqual(send_request.full_url, GMAIL_SEND_URI)
        self.assertEqual(token_timeout, 20)
        self.assertEqual(send_timeout, 20)
        token_form = token_request.data.decode("ascii")
        self.assertIn("grant_type=refresh_token", token_form)
        self.assertIn("client_id=client-id", token_form)
        self.assertIn("refresh_token=refresh-token", token_form)
        self.assertEqual(send_request.get_header("Authorization"), "Bearer access-token")
        self.assertEqual(send_request.get_header("Content-type"), "application/json")

        payload = json.loads(send_request.data.decode("utf-8"))
        message = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
        self.assertEqual(message["To"], "dest@example.com")
        self.assertEqual(message.get_payload()[1].get_content_type(), "application/pdf")
        self.assertEqual(GMAIL_SEND_SCOPE, "https://www.googleapis.com/auth/gmail.send")

    def test_token_refresh_error_includes_only_oauth_error_code(self):
        config = MailConfig(
            from_address="reports@gmail.com",
            username="username@gmail.com",
            client_id="client-id",
            client_secret="client-secret",
            refresh_token="refresh-token",
        )

        def failing_urlopen(request, timeout):
            body = json.dumps(
                {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
            ).encode("utf-8")
            raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

        with self.assertRaises(RuntimeError) as raised:
            send_report(
                "Gripă",
                b"%PDF-test",
                "raport.pdf",
                "dest@example.com",
                config=config,
                urlopen_factory=failing_urlopen,
            )

        self.assertEqual(
            str(raised.exception),
            "Google Gmail OAuth token refresh failed with HTTP 400 (invalid_grant)",
        )


if __name__ == "__main__":
    unittest.main()
