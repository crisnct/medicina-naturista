"""Gmail API delivery for generated reports.

The application uses a single owner-authorized Google account. Runtime
delivery uses a stored OAuth2 refresh token, so chatbot users do not have to
sign in with Google. No Gmail password or App Password is used here.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_HTTP_TIMEOUT_SECONDS = 20

EMAIL_SKIPPED = "email_skipped"
EMAIL_SENT = "email_sent"


@dataclass(frozen=True)
class MailConfig:
    """Resolved Gmail OAuth2 configuration without exposing secret values."""

    from_address: str
    username: str
    client_id: str
    client_secret: str
    refresh_token: str
    token_uri: str = GMAIL_TOKEN_URI
    send_uri: str = GMAIL_SEND_URI
    timeout_seconds: int = GMAIL_HTTP_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        return bool(
            self.from_address
            and self.username
            and self.client_id
            and self.client_secret
            and self.refresh_token
        )


def load_mail_config() -> MailConfig:
    """Read Gmail OAuth2 settings from the environment."""
    username = os.getenv("GMAIL_USERNAME", "").strip()
    return MailConfig(
        from_address=os.getenv("MAIL_FROM", "").strip() or username,
        username=username,
        client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN", "").strip(),
    )


def build_report_message(
    problem: str,
    pdf_bytes: bytes,
    filename: str,
    from_address: str,
    to_address: str,
) -> EmailMessage:
    """Build the Romanian report email and attach the generated PDF."""
    clean_problem = problem.strip()
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = f"Raport recomandări naturiste pentru {clean_problem}"
    message.set_content(
        "Bună ziua,\n\n"
        "Atașat găsiți raportul cu recomandări naturiste pentru problema descrisă.\n\n"
        "Raportul are caracter informativ și nu înlocuiește consultul medical.\n"
    )
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )
    return message


def _http_error(operation: str, error: HTTPError) -> RuntimeError:
    """Create a safe error without including Google's response body or tokens."""
    return RuntimeError(f"Google Gmail {operation} failed with HTTP {error.code}")


def _refresh_access_token(
    config: MailConfig,
    *,
    urlopen_factory: Callable[..., object],
) -> str:
    form = urlencode(
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": config.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("ascii")
    request = Request(
        config.token_uri,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen_factory(request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise _http_error("OAuth token refresh", exc) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Google OAuth token refresh could not connect") from exc
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("Google OAuth token refresh returned invalid data") from exc

    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Google OAuth token refresh returned no access token")
    return access_token


def _send_gmail_message(
    config: MailConfig,
    access_token: str,
    message: EmailMessage,
    *,
    urlopen_factory: Callable[..., object],
) -> None:
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    body = json.dumps({"raw": raw_message}).encode("utf-8")
    request = Request(
        config.send_uri,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen_factory(request, timeout=config.timeout_seconds) as response:
            response.read()
    except HTTPError as exc:
        raise _http_error("message send", exc) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Google Gmail message send could not connect") from exc


def send_report(
    problem: str,
    pdf_bytes: bytes,
    filename: str,
    to_address: str,
    *,
    config: MailConfig | None = None,
    urlopen_factory: Callable[..., object] = urlopen,
) -> str:
    """Send one report or return ``email_skipped`` when OAuth is not configured."""
    config = config or load_mail_config()
    if not config.is_configured:
        return EMAIL_SKIPPED

    message = build_report_message(
        problem, pdf_bytes, filename, config.from_address, to_address
    )
    access_token = _refresh_access_token(config, urlopen_factory=urlopen_factory)
    _send_gmail_message(config, access_token, message, urlopen_factory=urlopen_factory)
    return EMAIL_SENT
