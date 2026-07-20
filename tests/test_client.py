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
