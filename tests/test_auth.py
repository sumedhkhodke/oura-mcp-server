"""Tests for the token store and the OAuth refresh path."""

import asyncio
import json
import logging
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


def test_default_source_env_refresh_creds_build_oauth_source(monkeypatch, tmp_path):
    """Headless deployments: OURA_REFRESH_TOKEN (+ client creds) in env → refreshable source."""
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "env-rt")
    monkeypatch.setenv("OURA_CLIENT_ID", "env-cid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "env-sec")
    src = auth.default_token_source()
    assert isinstance(src, auth.OAuthTokenSource)
    # no access token given → must refresh before first use
    assert src._token.is_expired()
    assert src._token.refresh_token == "env-rt"


def test_default_source_env_refresh_with_access_token(monkeypatch, tmp_path):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "env-at")
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "env-rt")
    monkeypatch.setenv("OURA_CLIENT_ID", "env-cid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "env-sec")
    src = auth.default_token_source()
    assert isinstance(src, auth.OAuthTokenSource)
    assert src._token.access_token == "env-at"
    assert not src._token.is_expired()  # use it until it 401s, then refresh


def test_default_source_env_refresh_prefers_existing_file(monkeypatch, tmp_path):
    """A token file (rotated by an earlier refresh) wins over the env seed."""
    path = tmp_path / "tokens.json"
    auth.save_token(
        auth.StoredToken(access_token="file-at", refresh_token="file-rt", client_id="cid", client_secret="sec"),
        path,
    )
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(path))
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "env-rt")
    monkeypatch.setenv("OURA_CLIENT_ID", "env-cid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "env-sec")
    src = auth.default_token_source()
    assert isinstance(src, auth.OAuthTokenSource)
    assert src._token.access_token == "file-at"
    assert src._token.refresh_token == "file-rt"


def test_default_source_static_env_token_unchanged(monkeypatch):
    """OURA_ACCESS_TOKEN alone (legacy PAT) still yields a static source."""
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "envtok")
    monkeypatch.delenv("OURA_REFRESH_TOKEN", raising=False)
    src = auth.default_token_source()
    assert isinstance(src, auth.StaticTokenSource)


def test_default_source_errors_without_anything(monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    with pytest.raises(auth.AuthError, match="No Oura credentials"):
        auth.default_token_source()


async def _slow_refresh(request):
    await asyncio.sleep(0.01)
    return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600})


@respx.mock
async def test_concurrent_gets_refresh_exactly_once(tmp_path):
    expired = auth.StoredToken(
        access_token="old", refresh_token="r", expires_at=time.time() - 100, client_id="cid", client_secret="sec"
    )
    route = respx.post(TOKEN_URL).mock(side_effect=_slow_refresh)
    src = auth.OAuthTokenSource(expired, tmp_path / "tokens.json")
    tokens = await asyncio.gather(src.get(), src.get())
    assert tokens == ["new", "new"]
    assert route.call_count == 1


@respx.mock
async def test_concurrent_force_refresh_refreshes_once(tmp_path):
    tok = auth.StoredToken(
        access_token="old", refresh_token="r", expires_at=time.time() + 1000, client_id="cid", client_secret="sec"
    )
    route = respx.post(TOKEN_URL).mock(side_effect=_slow_refresh)
    src = auth.OAuthTokenSource(tok, tmp_path / "tokens.json")
    tokens = await asyncio.gather(src.force_refresh(), src.force_refresh())
    assert tokens == ["new", "new"]
    assert route.call_count == 1


@respx.mock
async def test_refresh_failure_logs_error(tmp_path, caplog):
    tok = auth.StoredToken(
        access_token="old", refresh_token="r", expires_at=time.time() - 100, client_id="cid", client_secret="sec"
    )
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, text="invalid_grant"))
    src = auth.OAuthTokenSource(tok, tmp_path / "t.json")
    with caplog.at_level(logging.ERROR, logger="oura_mcp_server.auth"), pytest.raises(auth.AuthError):
        await src.get()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and "400" in errors[0].getMessage() and "invalid_grant" in errors[0].getMessage()


@respx.mock
async def test_refresh_success_logs_info(tmp_path, caplog):
    tok = auth.StoredToken(
        access_token="old", refresh_token="r", expires_at=time.time() - 100, client_id="cid", client_secret="sec"
    )
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600})
    )
    path = tmp_path / "t.json"
    with caplog.at_level(logging.INFO, logger="oura_mcp_server.auth"):
        await auth.OAuthTokenSource(tok, path).get()
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert len(messages) == 2
    assert str(path) in messages[1]


async def test_force_refresh_without_credentials_warns(tmp_path, caplog):
    src = auth.OAuthTokenSource(auth.StoredToken(access_token="only"), tmp_path / "t.json")
    with caplog.at_level(logging.WARNING, logger="oura_mcp_server.auth"):
        assert await src.force_refresh() is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_load_token_corrupt_json_raises(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text("{not json")
    with pytest.raises(auth.AuthError, match="unreadable"):
        auth.load_token(path)


def test_load_token_ignores_unknown_keys(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"access_token": "a", "refresh_token": "r", "token_type": "Bearer", "extra": 1}))
    tok = auth.load_token(path)
    assert tok is not None
    assert tok.access_token == "a"
    assert tok.refresh_token == "r"


def test_load_token_missing_access_token_raises(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"refresh_token": "r"}))
    with pytest.raises(auth.AuthError, match="unreadable"):
        auth.load_token(path)


def test_module_docstring_lists_three_auth_modes():
    assert "Three ways" in (auth.__doc__ or "")
    assert "OURA_REFRESH_TOKEN" in (auth.__doc__ or "")


def test_token_file_path_defaults_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_TOKEN_FILE", raising=False)
    monkeypatch.setattr(auth.Path, "home", classmethod(lambda cls: tmp_path))
    assert auth.token_file_path() == tmp_path / ".oura-mcp" / "tokens.json"


def test_save_token_tolerates_chmod_failure(monkeypatch, tmp_path):
    def boom(self, mode):
        raise OSError("no perms here")

    monkeypatch.setattr(auth.Path, "chmod", boom)
    path = auth.save_token(auth.StoredToken(access_token="a"), tmp_path / "t.json")
    assert auth.load_token(path).access_token == "a"


def test_default_source_uses_token_file(monkeypatch, tmp_path):
    for name in ("OURA_ACCESS_TOKEN", "OURA_REFRESH_TOKEN", "OURA_CLIENT_ID", "OURA_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "tokens.json"
    monkeypatch.setenv("OURA_TOKEN_FILE", str(path))
    auth.save_token(auth.StoredToken(access_token="file-at", refresh_token="rt"), path)
    src = auth.default_token_source()
    assert isinstance(src, auth.OAuthTokenSource)
    assert src._token.access_token == "file-at"
