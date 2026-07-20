"""Tests for the OAuth login helpers (loopback server not exercised)."""

import httpx
import respx

from oura_mcp_server import oauth

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


def test_login_command_without_creds_returns_2(capsys):
    rc = oauth.login_command(["--no-browser"])
    assert rc == 2
    assert "Register an app" in capsys.readouterr().err


def test_default_scopes_are_broad():
    assert "daily" in oauth.DEFAULT_SCOPES
    assert "heartrate" in oauth.DEFAULT_SCOPES
    assert "personal" in oauth.DEFAULT_SCOPES
