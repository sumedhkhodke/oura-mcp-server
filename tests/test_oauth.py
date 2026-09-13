"""Tests for the OAuth login helpers (loopback server not exercised)."""

import io
from typing import ClassVar

import httpx
import pytest
import respx

from oura_mcp_server import oauth
from oura_mcp_server.auth import StoredToken, save_token

TOKEN_URL = "https://api.ouraring.com/oauth/token"


@respx.mock
def test_exchange_code_for_token():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 86400,
                "scope": "daily heartrate",
            },
        )
    )
    tok = oauth.exchange_code_for_token("cid", "sec", "the-code", "http://localhost:8080/callback")
    assert tok.access_token == "AT"
    assert tok.refresh_token == "RT"
    assert tok.client_id == "cid"
    assert tok.scope == "daily heartrate"
    # request carried the right grant + code
    sent = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "the-code"


def test_login_command_without_creds_returns_2(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    rc = oauth.login_command(["--no-browser"])
    assert rc == 2
    assert "Register an app" in capsys.readouterr().err


def test_login_command_falls_back_to_stored_creds(monkeypatch, tmp_path):
    """Re-running `login` without flags/env reuses creds saved by a prior login."""
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    token_file = tmp_path / "tokens.json"
    monkeypatch.setenv("OURA_TOKEN_FILE", str(token_file))
    save_token(
        StoredToken(access_token="AT", refresh_token="RT", client_id="stored-cid", client_secret="stored-sec"),
        token_file,
    )

    captured = {}

    def fake_run_login(client_id, client_secret, **kwargs):
        captured["client_id"] = client_id
        captured["client_secret"] = client_secret
        return StoredToken(access_token="AT2")

    monkeypatch.setattr(oauth, "run_login", fake_run_login)
    rc = oauth.login_command(["--no-browser"])
    assert rc == 0
    assert captured == {"client_id": "stored-cid", "client_secret": "stored-sec"}


def test_login_command_flags_override_stored_creds(monkeypatch, tmp_path):
    token_file = tmp_path / "tokens.json"
    monkeypatch.setenv("OURA_TOKEN_FILE", str(token_file))
    save_token(StoredToken(access_token="AT", client_id="stored-cid", client_secret="stored-sec"), token_file)

    captured = {}

    def fake_run_login(client_id, client_secret, **kwargs):
        captured["client_id"] = client_id
        captured["client_secret"] = client_secret
        return StoredToken(access_token="AT2")

    monkeypatch.setattr(oauth, "run_login", fake_run_login)
    rc = oauth.login_command(["--client-id", "flag-cid", "--client-secret", "flag-sec", "--no-browser"])
    assert rc == 0
    assert captured == {"client_id": "flag-cid", "client_secret": "flag-sec"}


def test_default_scopes_are_broad():
    assert "daily" in oauth.DEFAULT_SCOPES
    assert "heartrate" in oauth.DEFAULT_SCOPES
    assert "personal" in oauth.DEFAULT_SCOPES


def test_login_command_points_to_developer_portal(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    assert oauth.login_command(["--no-browser"]) == 2
    err = capsys.readouterr().err
    assert "https://developer.ouraring.com/" in err
    assert "cloud.ouraring.com/oauth/applications" not in err


def test_token_url_shared_with_auth():
    from oura_mcp_server import auth

    assert oauth.OURA_TOKEN_URL is auth.OURA_TOKEN_URL


def _fake_handler(path):
    handler = oauth._CallbackHandler.__new__(oauth._CallbackHandler)
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.wfile = io.BytesIO()
    return handler


@pytest.fixture(autouse=True)
def _reset_callback_result():
    oauth._CallbackHandler.result = {}
    yield
    oauth._CallbackHandler.result = {}


def test_callback_handler_captures_code():
    handler = _fake_handler("/callback?code=abc&state=xyz")
    handler.do_GET()
    assert oauth._CallbackHandler.result == {"code": "abc", "state": "xyz"}
    out = handler.wfile.getvalue()
    assert out.split(b"\r\n", 1)[0].endswith(b"200 OK")
    assert b"Oura login complete" in out


def test_callback_handler_captures_error():
    handler = _fake_handler("/callback?error=access_denied&error_description=nope")
    handler.do_GET()
    assert oauth._CallbackHandler.result["error"] == "access_denied"
    assert b"Login failed" in handler.wfile.getvalue()


def test_callback_handler_ignores_stray_requests():
    handler = _fake_handler("/favicon.ico")
    handler.do_GET()
    assert oauth._CallbackHandler.result == {}
    assert b" 404 " in handler.wfile.getvalue().split(b"\r\n", 1)[0]
    handler.log_message("ignored %s", "x")


@respx.mock
def test_exchange_code_failure_exits():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, text="invalid_grant"))
    with pytest.raises(SystemExit, match="Token exchange failed"):
        oauth.exchange_code_for_token("cid", "sec", "bad", "http://localhost:8080/callback")


class _FakeServer:
    callback: ClassVar[dict[str, str]] = {}

    def __init__(self, address, handler):
        self.address = address
        self.handler = handler
        self.closed = False

    def handle_request(self):
        self.handler.result = dict(self.callback)

    def server_close(self):
        self.closed = True


@pytest.fixture
def login_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setattr(oauth.secrets, "token_urlsafe", lambda n: "fixed-state")
    monkeypatch.setattr(oauth, "HTTPServer", _FakeServer)
    opened = []
    monkeypatch.setattr(oauth.webbrowser, "open", lambda url: opened.append(url))
    return {"opened": opened, "token_file": tmp_path / "tokens.json"}


@respx.mock
def test_run_login_success(login_env, monkeypatch, capsys):
    monkeypatch.setattr(_FakeServer, "callback", {"code": "the-code", "state": "fixed-state"})
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
    )
    token = oauth.run_login("cid", "sec", port=8089, scopes=["daily"])
    assert token.access_token == "AT"
    assert route.called
    assert login_env["token_file"].exists()
    assert len(login_env["opened"]) == 1
    assert "state=fixed-state" in login_env["opened"][0]
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8089%2Fcallback" in login_env["opened"][0]
    assert "Success" in capsys.readouterr().out


def test_run_login_no_browser(login_env, monkeypatch):
    monkeypatch.setattr(_FakeServer, "callback", {"code": "c", "state": "fixed-state"})
    monkeypatch.setattr(oauth, "exchange_code_for_token", lambda *a: StoredToken(access_token="x"))
    oauth.run_login("cid", "sec", open_browser=False)
    assert login_env["opened"] == []


def test_run_login_state_mismatch(login_env, monkeypatch):
    monkeypatch.setattr(_FakeServer, "callback", {"code": "the-code", "state": "forged"})
    with pytest.raises(SystemExit, match="State mismatch"):
        oauth.run_login("cid", "sec")


def test_run_login_authorization_denied(login_env, monkeypatch):
    monkeypatch.setattr(_FakeServer, "callback", {"error": "access_denied", "state": "fixed-state"})
    with pytest.raises(SystemExit, match="Authorization denied"):
        oauth.run_login("cid", "sec")
