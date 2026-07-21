"""Tests for the /webhook callback endpoint (Oura verification + event intake)."""

import fastmcp
import httpx
import pytest

from oura_mcp_server import server, webhook_receiver


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OURA_WEBHOOK_VERIFICATION_TOKEN", "vtok")
    webhook_receiver.clear_events()
    transport = httpx.ASGITransport(app=server.mcp.http_app())
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_verification_echoes_challenge(client):
    resp = await client.get("/webhook", params={"verification_token": "vtok", "challenge": "abc123"})
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


async def test_verification_rejects_bad_token(client):
    resp = await client.get("/webhook", params={"verification_token": "wrong", "challenge": "abc123"})
    assert resp.status_code == 403


async def test_unconfigured_receiver_is_disabled(client, monkeypatch):
    monkeypatch.delenv("OURA_WEBHOOK_VERIFICATION_TOKEN", raising=False)
    resp = await client.get("/webhook", params={"verification_token": "vtok", "challenge": "abc123"})
    assert resp.status_code == 503


async def test_post_event_is_recorded_and_readable_via_tool(client):
    event = {
        "event_type": "create",
        "data_type": "daily_sleep",
        "object_id": "obj-1",
        "event_time": "2026-07-20T08:00:00+00:00",
        "user_id": "user-1",
    }
    resp = await client.post("/webhook", json=event)
    assert resp.status_code == 200

    out = await server.get_recent_webhook_events()
    assert out["count"] == 1
    assert out["events"][0]["object_id"] == "obj-1"


async def test_post_rejects_invalid_json(client):
    resp = await client.post("/webhook", content=b"not json", headers={"content-type": "application/json"})
    assert resp.status_code == 400


def test_event_buffer_is_bounded():
    webhook_receiver.clear_events()
    for i in range(webhook_receiver.MAX_EVENTS + 50):
        webhook_receiver.record_event({"object_id": f"obj-{i}"})
    events = webhook_receiver.recent_events(limit=10_000)
    assert len(events) == webhook_receiver.MAX_EVENTS
    # newest first
    assert events[0]["object_id"] == f"obj-{webhook_receiver.MAX_EVENTS + 49}"
    webhook_receiver.clear_events()


async def test_webhook_route_bypasses_mcp_oauth(monkeypatch, tmp_path):
    """Oura cannot complete MCP OAuth, so /webhook stays independently gated."""
    monkeypatch.setenv("OURA_WEBHOOK_VERIFICATION_TOKEN", "vtok")
    monkeypatch.setenv("OURA_MCP_GITHUB_CLIENT_ID", "github-client-id")
    monkeypatch.setenv("OURA_MCP_GITHUB_CLIENT_SECRET", "github-client-secret")
    monkeypatch.setenv("OURA_MCP_ALLOWED_GITHUB_USERS", "sumedhkhodke")
    monkeypatch.setenv("OURA_MCP_JWT_SIGNING_KEY", "a-stable-random-signing-key")
    monkeypatch.setenv("OURA_MCP_BASE_URL", "http://localhost:8000")
    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    old_auth = server.mcp.auth
    server.mcp.auth = server.build_auth_from_env()
    try:
        transport = httpx.ASGITransport(app=server.mcp.http_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webhook", params={"verification_token": "vtok", "challenge": "xyz"})
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "xyz"}
    finally:
        server.mcp.auth = old_auth
