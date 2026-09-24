"""One-time Google OAuth2 bootstrap for the report sender.

Run this script on a machine with a browser after placing the OAuth desktop
client values in the project .env. It saves or replaces the refresh token in
.env and never prints the token.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
REDIRECT_URI = "http://127.0.0.1:8765/oauth2callback"
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/gmail.send"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        query = parse_qs(urlparse(self.path).query)
        OAuthCallbackHandler.result = {
            "code": query.get("code", [""])[0],
            "state": query.get("state", [""])[0],
            "error": query.get("error", [""])[0],
        }
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<html><body><h1>Autorizarea Google s-a încheiat.</h1>"
            "<p>Poți închide această fereastră și reveni în terminal.</p></body></html>".encode("utf-8")
        )

    def log_message(self, format, *args):  # noqa: A002 - required signature
        return


def _exchange_code(code: str) -> str:
    body = urlencode(
        {
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode("ascii")
    request = Request(
        TOKEN_URI,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise RuntimeError("Google nu a returnat un refresh token.")
    return refresh_token


def _save_refresh_token(refresh_token: str) -> None:
    """Replace or append GOOGLE_REFRESH_TOKEN in the project .env atomically."""
    env_path = ROOT / ".env"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
    else:
        content = ""

    newline = "\r\n" if "\r\n" in content else "\n"
    replacement = f"GOOGLE_REFRESH_TOKEN={refresh_token}{newline}"
    pattern = re.compile(r"(?m)^[ \t]*GOOGLE_REFRESH_TOKEN[ \t]*=.*(?:\r\n|\n|$)")
    if pattern.search(content):
        content = pattern.sub(replacement, content, count=1)
    else:
        if content and not content.endswith(("\n", "\r")):
            content += newline
        content += replacement

    env_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".env.",
        suffix=".tmp",
        dir=env_path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, env_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def main() -> int:
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Completează GOOGLE_CLIENT_ID și GOOGLE_CLIENT_SECRET în .env.", file=sys.stderr)
        return 2

    state = secrets.token_urlsafe(32)
    auth_url = AUTH_URI + "?" + urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    server = HTTPServer(("127.0.0.1", 8765), OAuthCallbackHandler)
    print("Se deschide pagina Google pentru autorizare...")
    print("Dacă nu se deschide automat, accesează:")
    print(auth_url)
    webbrowser.open(auth_url)
    server.handle_request()
    result = OAuthCallbackHandler.result
    server.server_close()

    if result.get("state") != state:
        print("Autorizarea a eșuat: state OAuth2 invalid.", file=sys.stderr)
        return 1
    if result.get("error"):
        print(f"Autorizarea Google a fost refuzată: {result['error']}", file=sys.stderr)
        return 1
    if not result.get("code"):
        print("Autorizarea Google nu a returnat un cod.", file=sys.stderr)
        return 1

    try:
        refresh_token = _exchange_code(result["code"])
    except (HTTPError, URLError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Nu s-a putut obține refresh token-ul Google: {type(exc).__name__}", file=sys.stderr)
        return 1

    try:
        _save_refresh_token(refresh_token)
    except OSError as exc:
        print(f"Tokenul a fost obținut, dar .env nu a putut fi actualizat: {type(exc).__name__}", file=sys.stderr)
        return 1

    print("\nAutorizare reușită. GOOGLE_REFRESH_TOKEN a fost salvat în .env.")
    print("Nu publica și nu trimite acest token altor persoane.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
