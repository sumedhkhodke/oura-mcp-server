"""Tests for the Oura client and MCP tools using a mocked HTTP layer."""

import httpx
import pytest
import respx

from oura_mcp_server.client import OuraClient, OuraError

BASE = "https://api.ouraring.com/v2"


@pytest.fixture
def client():
    return OuraClient(access_token="test-token")


@respx.mock
async def test_pagination_follows_next_token(client):
    route = respx.get(f"{BASE}/usercollection/daily_sleep")
    route.side_effect = [
        httpx.Response(200, json={"data": [{"id": "a"}], "next_token": "T2"}),
        httpx.Response(200, json={"data": [{"id": "b"}], "next_token": None}),
    ]
    data = await client.get_collection("daily_sleep", {"start_date": "2026-07-01"})
    assert [d["id"] for d in data] == ["a", "b"]
    # second request must carry the next_token from page one
    assert route.calls[1].request.url.params.get("next_token") == "T2"
    await client.aclose()


@respx.mock
async def test_none_params_are_dropped(client):
    route = respx.get(f"{BASE}/usercollection/daily_sleep").mock(
        return_value=httpx.Response(200, json={"data": [], "next_token": None})
    )
    await client.get_collection("daily_sleep", {"start_date": "2026-07-01", "end_date": None})
    assert "end_date" not in route.calls[0].request.url.params
    await client.aclose()


@respx.mock
async def test_401_raises_readable_error(client):
    respx.get(f"{BASE}/usercollection/personal_info").mock(return_value=httpx.Response(401))
    with pytest.raises(OuraError, match="401"):
        await client.get_single("personal_info")
    await client.aclose()


def test_missing_token_raises(monkeypatch, tmp_path):
    from oura_mcp_server.auth import AuthError

    monkeypatch.delenv("OURA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    with pytest.raises(AuthError, match="No Oura credentials"):
        OuraClient()


@respx.mock
async def test_tool_returns_wrapped_result(monkeypatch):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "test-token")
    # reset the module-level singleton so it picks up the test token
    import oura_mcp_server.server as server

    server._client = None
    respx.get(f"{BASE}/usercollection/daily_readiness").mock(
        return_value=httpx.Response(200, json={"data": [{"score": 88}], "next_token": None})
    )
    result = await server.get_daily_readiness(start_date="2026-07-01", end_date="2026-07-02")
    assert result["count"] == 1
    assert result["data"][0]["score"] == 88
    assert result["endpoint"] == "daily_readiness"


def test_client_prefers_refreshable_source_when_refresh_env_present(monkeypatch, tmp_path):
    """Refresh credentials in the env must win over a static OURA_ACCESS_TOKEN."""
    from oura_mcp_server import auth

    monkeypatch.setenv("OURA_ACCESS_TOKEN", "env-at")
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "env-rt")
    monkeypatch.setenv("OURA_CLIENT_ID", "env-cid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "env-sec")

    client = OuraClient()
    assert isinstance(client._auth, auth.OAuthTokenSource)


class _RefreshingSource:
    def __init__(self):
        self.refreshes = 0

    async def get(self):
        return "stale"

    async def force_refresh(self):
        self.refreshes += 1
        return "fresh"


@respx.mock
async def test_401_triggers_refresh_and_retry_with_warning(caplog):
    import logging

    route = respx.get(f"{BASE}/usercollection/personal_info")
    route.side_effect = [httpx.Response(401), httpx.Response(200, json={"id": "me"})]
    source = _RefreshingSource()
    client = OuraClient(token_source=source)
    with caplog.at_level(logging.WARNING, logger="oura_mcp_server.client"):
        out = await client.get_single("personal_info")
    assert out == {"id": "me"}
    assert source.refreshes == 1
    assert route.calls[1].request.headers["Authorization"] == "Bearer fresh"
    assert any(r.levelno == logging.WARNING and "401" in r.getMessage() for r in caplog.records)
    await client.aclose()


@respx.mock
async def test_network_error_becomes_oura_error(client):
    respx.get(f"{BASE}/usercollection/personal_info").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(OuraError, match="Request to Oura failed"):
        await client.get_single("personal_info")
    await client.aclose()


@respx.mock
async def test_auth_error_becomes_oura_error():
    from oura_mcp_server.auth import AuthError, TokenSource

    class Failing(TokenSource):
        async def get(self):
            raise AuthError("refresh broke")

    client = OuraClient(token_source=Failing())
    with pytest.raises(OuraError, match="refresh broke"):
        await client.get_single("personal_info")
    await client.aclose()


@respx.mock
@pytest.mark.parametrize(
    ("status", "match"),
    [(403, "403 Forbidden"), (429, "rate limit"), (500, "Oura API error 500")],
)
async def test_http_error_messages(client, status, match):
    respx.get(f"{BASE}/usercollection/personal_info").mock(return_value=httpx.Response(status, text="detail"))
    with pytest.raises(OuraError, match=match):
        await client.get_single("personal_info")
    await client.aclose()


def test_get_document_removed():
    assert not hasattr(OuraClient, "get_document")


def test_explicit_base_url_overrides_env(monkeypatch):
    monkeypatch.setenv("OURA_API_BASE_URL", "https://env.example/v2/")
    assert OuraClient(access_token="t")._base_url == "https://env.example/v2"
    assert OuraClient(access_token="t", base_url="https://arg.example/v2/")._base_url == "https://arg.example/v2"
