"""OAuth2 authorization-code login flow (``oura-mcp-server login``).

Runs a one-shot loopback web server on localhost, opens the browser to Oura's
consent screen, captures the redirect, exchanges the code for tokens, and
persists them via :mod:`oura_mcp_server.auth`.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from .auth import StoredToken, load_token, save_token, token_file_path

OURA_AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"

# Broad read scopes so every tool has data. `email`/`personal` cover profile;
# `daily` covers the daily_* summaries; the rest gate their named resources.
DEFAULT_SCOPES = [
    "email",
    "personal",
    "daily",
    "heartrate",
    "workout",
    "tag",
    "session",
    "spo2",
    "ring_configuration",
    "stress",
    "heart_health",
]

_SUCCESS_HTML = (
    b"<html><body style='font-family:sans-serif;text-align:center;padding-top:4em'>"
    b"<h2>&#10003; Oura login complete</h2>"
    b"<p>You can close this tab and return to your terminal.</p></body></html>"
)
_ERROR_HTML = (
    b"<html><body style='font-family:sans-serif;text-align:center;padding-top:4em'>"
    b"<h2>Login failed</h2><p>Check the terminal for details.</p></body></html>"
)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the ``?code=...&state=...`` redirect from Oura."""

    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 (stdlib signature)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params or "error" in params:
            type(self).result = {k: v[0] for k, v in params.items()}
            ok = "code" in params
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML if ok else _ERROR_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:  # silence default stderr logging
        pass


def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> StoredToken:
    """Exchange an authorization code for an access/refresh token pair."""
    resp = httpx.post(
        OURA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30.0,
    )
    if resp.status_code >= 400:
        raise SystemExit(f"Token exchange failed ({resp.status_code}): {resp.text[:500]}")
    return StoredToken.from_token_response(resp.json(), client_id=client_id, client_secret=client_secret)


def run_login(
    client_id: str,
    client_secret: str,
    *,
    port: int = 8080,
    scopes: list[str] | None = None,
    open_browser: bool = True,
) -> StoredToken:
    """Execute the full authorization-code flow and persist the token."""
    scopes = scopes or DEFAULT_SCOPES
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(24)

    authorize_url = (
        OURA_AUTHORIZE_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes),
                "state": state,
            }
        )
    )

    print(f"\nOpening your browser to authorize Oura access...\n  {authorize_url}\n")
    if open_browser:
        webbrowser.open(authorize_url)

    httpd = HTTPServer(("localhost", port), _CallbackHandler)
    _CallbackHandler.result = {}
    try:
        # Serve requests until the real callback (with code/error) arrives,
        # ignoring stray hits like /favicon.ico.
        while not _CallbackHandler.result:
            httpd.handle_request()
    finally:
        httpd.server_close()

    result = _CallbackHandler.result
    if "error" in result:
        raise SystemExit(f"Authorization denied: {result.get('error')} {result.get('error_description', '')}")
    if result.get("state") != state:
        raise SystemExit("State mismatch — possible CSRF; aborting.")

    token = exchange_code_for_token(client_id, client_secret, result["code"], redirect_uri)
    path = save_token(token)
    print(f"Success. Tokens saved to {path} (chmod 600).")
    print("Granted scopes:", token.scope or " ".join(scopes))
    return token


def login_command(argv: list[str] | None = None) -> int:
    """CLI entry for ``oura-mcp-server login``."""
    parser = argparse.ArgumentParser(
        prog="oura-mcp-server login",
        description="Authenticate with Oura via OAuth2 and store tokens locally.",
    )
    parser.add_argument("--client-id", default=os.environ.get("OURA_CLIENT_ID"))
    parser.add_argument("--client-secret", default=os.environ.get("OURA_CLIENT_SECRET"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OURA_REDIRECT_PORT", "8080")),
        help="Loopback port; the registered redirect URI must be http://localhost:PORT/callback (default 8080).",
    )
    parser.add_argument("--scopes", nargs="*", default=None, help="Override the requested scopes.")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open the browser.")
    args = parser.parse_args(argv)

    if not args.client_id or not args.client_secret:
        # Re-login: reuse the app credentials persisted by a previous login.
        stored = load_token()
        if stored and stored.client_id and stored.client_secret:
            args.client_id = args.client_id or stored.client_id
            args.client_secret = args.client_secret or stored.client_secret

    if not args.client_id or not args.client_secret:
        print(
            "Missing OAuth credentials. Register an app at "
            "https://cloud.ouraring.com/oauth/applications with redirect URI\n"
            f"  http://localhost:{args.port}/callback\n"
            "then pass --client-id/--client-secret or set OURA_CLIENT_ID / "
            "OURA_CLIENT_SECRET.",
            file=sys.stderr,
        )
        return 2

    run_login(
        args.client_id,
        args.client_secret,
        port=args.port,
        scopes=args.scopes,
        open_browser=not args.no_browser,
    )
    print(f"\nDone. Start the server normally — it will read {token_file_path()}.")
    return 0
