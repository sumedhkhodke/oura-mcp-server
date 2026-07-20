"""Tests for the OAuth login helpers (loopback server not exercised)."""

import httpx
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
