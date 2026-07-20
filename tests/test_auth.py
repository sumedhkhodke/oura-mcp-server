"""Tests for the token store and the OAuth refresh path."""

import time

import httpx
import pytest
import respx

from oura_mcp_server import auth

TOKEN_URL = "https://api.ouraring.com/oauth/token"


def test_token_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "tokens.json"
    tok = auth.StoredToken(
        access_token="a",
        refresh_token="r",
        expires_at=time.time() + 1000,
        client_id="cid",
        client_secret="secret",
        scope="daily",
    )
    auth.save_token(tok, path)
    loaded = auth.load_token(path)
    assert loaded.access_token == "a"
    assert loaded.refresh_token == "r"
    assert loaded.client_id == "cid"
    # file must not be world-readable
    assert (path.stat().st_mode & 0o077) == 0


def test_is_expired():
    assert auth.StoredToken("a", expires_at=time.time() - 10).is_expired()
    assert not auth.StoredToken("a", expires_at=time.time() + 10_000).is_expired()
    assert not auth.StoredToken("a", expires_at=None).is_expired()


def test_from_token_response_computes_expiry():
    tok = auth.StoredToken.from_token_response(
        {"access_token": "x", "refresh_token": "y", "expires_in": 3600, "scope": "daily"},
        client_id="cid",
        client_secret="sec",
    )
    assert tok.access_token == "x"
    assert tok.expires_at is not None and tok.expires_at > time.time()


@respx.mock
async def test_oauth_source_refreshes_when_expired(tmp_path):
    path = tmp_path / "tokens.json"
    expired = auth.StoredToken(
        access_token="old",
        refresh_token="r",
        expires_at=time.time() - 100,
        client_id="cid",
        client_secret="sec",
    )
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600})
    )
    src = auth.OAuthTokenSource(expired, path)
    token = await src.get()
    assert token == "new"
    # refreshed token should be persisted
    assert auth.load_token(path).access_token == "new"


@respx.mock
async def test_oauth_source_refresh_failure_raises(tmp_path):
    tok = auth.StoredToken(
        access_token="old",
        refresh_token="r",
        expires_at=time.time() - 100,
        client_id="cid",
        client_secret="sec",
    )
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, text="bad"))
    src = auth.OAuthTokenSource(tok, tmp_path / "t.json")
    with pytest.raises(auth.AuthError):
        await src.get()


async def test_static_source_cannot_refresh():
    src = auth.StaticTokenSource("tok")
    assert await src.get() == "tok"
    assert await src.force_refresh() is None


def test_default_source_prefers_env(monkeypatch):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "envtok")
    src = auth.default_token_source()
    assert isinstance(src, auth.StaticTokenSource)


def test_default_source_errors_without_anything(monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    with pytest.raises(auth.AuthError, match="No Oura credentials"):
        auth.default_token_source()
