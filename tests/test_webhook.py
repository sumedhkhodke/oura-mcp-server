"""Tests for the webhook subscription client and tools."""

import httpx
import pytest
import respx

from oura_mcp_server.client import OuraError
from oura_mcp_server.webhook import WebhookClient, client_credentials

BASE = "https://api.ouraring.com/v2/webhook/subscription"


@respx.mock
async def test_list_uses_client_credential_headers():
    route = respx.get(BASE).mock(return_value=httpx.Response(200, json=[{"id": "s1"}]))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    out = await wc.list()
    assert out == [{"id": "s1"}]
    req = route.calls[0].request
    assert req.headers["x-client-id"] == "cid"
    assert req.headers["x-client-secret"] == "sec"
    await wc.aclose()


@respx.mock
async def test_create_posts_body():
    route = respx.post(BASE).mock(return_value=httpx.Response(201, json={"id": "new"}))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    out = await wc.create("https://cb.example/hook", "vtok", "create", "daily_sleep")
    assert out["id"] == "new"
    import json as _json

    body = _json.loads(route.calls[0].request.content)
    assert body["callback_url"] == "https://cb.example/hook"
    assert body["event_type"] == "create"
    assert body["data_type"] == "daily_sleep"
    await wc.aclose()


@respx.mock
async def test_delete_handles_no_content():
    respx.delete(f"{BASE}/s1").mock(return_value=httpx.Response(204))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    assert await wc.delete("s1") == {"status": "ok"}
    await wc.aclose()


@respx.mock
async def test_renew_puts_to_renew_path():
    route = respx.put(f"{BASE}/renew/s1").mock(return_value=httpx.Response(200, json={"id": "s1"}))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    await wc.renew("s1")
    assert route.called
    await wc.aclose()


@respx.mock
async def test_bad_credentials_message():
    respx.get(BASE).mock(return_value=httpx.Response(401))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    with pytest.raises(OuraError, match="app credentials"):
        await wc.list()
    await wc.aclose()


def test_client_credentials_from_env(monkeypatch):
    monkeypatch.setenv("OURA_CLIENT_ID", "envid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "envsec")
    assert client_credentials() == ("envid", "envsec")


def test_client_credentials_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    with pytest.raises(OuraError, match="OAuth app credentials"):
        client_credentials()


@respx.mock
async def test_tool_wrapper_returns_error_without_creds(monkeypatch, tmp_path):
    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("OURA_TOKEN_FILE", str(tmp_path / "none.json"))
    import oura_mcp_server.server as srv

    out = await srv.list_webhook_subscriptions()
    assert "error" in out


@respx.mock
async def test_base_url_honors_env(monkeypatch):
    monkeypatch.setenv("OURA_API_BASE_URL", "https://sandbox.example/v2/")
    route = respx.get("https://sandbox.example/v2/webhook/subscription").mock(return_value=httpx.Response(200, json=[]))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    assert await wc.list() == []
    assert route.called
    await wc.aclose()


def test_client_credentials_from_token_file(monkeypatch, tmp_path):
    from oura_mcp_server.auth import StoredToken, save_token

    monkeypatch.delenv("OURA_CLIENT_ID", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    path = tmp_path / "tokens.json"
    monkeypatch.setenv("OURA_TOKEN_FILE", str(path))
    save_token(StoredToken(access_token="a", client_id="file-cid", client_secret="file-sec"), path)
    assert client_credentials() == ("file-cid", "file-sec")


@respx.mock
async def test_network_error_message():
    respx.get(BASE).mock(side_effect=httpx.ConnectError("down"))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    with pytest.raises(OuraError, match="Webhook request failed"):
        await wc.list()
    await wc.aclose()


@respx.mock
async def test_server_error_message():
    respx.get(BASE).mock(return_value=httpx.Response(500, text="oops"))
    wc = WebhookClient(client_id="cid", client_secret="sec")
    with pytest.raises(OuraError, match="Webhook API error 500"):
        await wc.list()
    await wc.aclose()
