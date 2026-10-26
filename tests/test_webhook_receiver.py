"""Tests for the /webhook callback endpoint (Oura verification + event intake)."""

import hashlib
import hmac
import json
import logging

import fastmcp
import httpx
import pytest

from oura_mcp_server import server, webhook_receiver
from oura_mcp_server.mcp_auth import build_github_oauth

SECRET = "oura-client-secret"
EVENT = {
    "event_type": "create",
    "data_type": "daily_sleep",
    "object_id": "obj-1",
    "event_time": "2026-07-20T08:00:00+00:00",
    "user_id": "user-1",
}


def oura_signature(timestamp: str, body: bytes, secret: str = SECRET) -> str:
    """Oura's scheme: uppercase hex HMAC-SHA256(client secret, timestamp + JSON body)."""
    return hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).hexdigest().upper()


def compact(event: dict) -> bytes:
    """What JavaScript's JSON.stringify produces for a parsed body."""
    return json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OURA_WEBHOOK_VERIFICATION_TOKEN", "vtok")
    monkeypatch.delenv("OURA_WEBHOOK_SIGNATURE_MODE", raising=False)
    monkeypatch.delenv("OURA_CLIENT_SECRET", raising=False)
    webhook_receiver.clear_events()
    transport = httpx.ASGITransport(app=server.mcp.http_app())
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def post_signed(client, body: bytes, timestamp: str = "1792980000", signature: str | None = None):
    headers = {"content-type": "application/json", "x-oura-timestamp": timestamp}
    headers["x-oura-signature"] = signature if signature is not None else oura_signature(timestamp, body)
    return await client.post("/webhook", content=body, headers=headers)


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


async def test_enforce_accepts_valid_signature(client, monkeypatch):
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "enforce")
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    resp = await post_signed(client, compact(EVENT))
    assert resp.status_code == 200
    assert webhook_receiver.recent_events()[0]["object_id"] == "obj-1"


async def test_enforce_accepts_lowercase_hex_signature(client, monkeypatch):
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "enforce")
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    body = compact(EVENT)
    resp = await post_signed(client, body, signature=oura_signature("1792980000", body).lower())
    assert resp.status_code == 200


async def test_enforce_accepts_signature_over_reserialized_body(client, monkeypatch):
    """Oura signs JSON.stringify(body); accept it even if the raw bytes had extra whitespace."""
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "enforce")
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    spaced = json.dumps(EVENT, indent=2).encode()
    resp = await post_signed(client, spaced, signature=oura_signature("1792980000", compact(EVENT)))
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "case",
    ["wrong-signature", "wrong-secret", "tampered-body", "wrong-timestamp", "missing-headers"],
)
async def test_enforce_rejects_bad_or_missing_signature(client, monkeypatch, case):
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "enforce")
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    body = compact(EVENT)
    if case == "missing-headers":
        resp = await client.post("/webhook", content=body, headers={"content-type": "application/json"})
    else:
        signature = {
            "wrong-signature": "DEADBEEF",
            "wrong-secret": oura_signature("1792980000", body, secret="someone-else"),
            "tampered-body": oura_signature("1792980000", compact({**EVENT, "object_id": "other"})),
            "wrong-timestamp": oura_signature("1700000000", body),
        }[case]
        resp = await post_signed(client, body, signature=signature)
    assert resp.status_code == 401
    assert webhook_receiver.recent_events() == []


async def test_enforce_without_client_secret_fails_closed(client, monkeypatch):
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "enforce")
    resp = await post_signed(client, compact(EVENT))
    assert resp.status_code == 401
    assert webhook_receiver.recent_events() == []


async def test_log_mode_records_unsigned_event_and_warns(client, monkeypatch, caplog):
    """Default mode: a bad signature is logged, not rejected, so rollout can't drop real events."""
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    with caplog.at_level(logging.WARNING, logger="oura_mcp_server"):
        resp = await post_signed(client, compact(EVENT), signature="DEADBEEF")
    assert resp.status_code == 200
    assert webhook_receiver.recent_events()[0]["object_id"] == "obj-1"
    assert "signature invalid" in caplog.text


async def test_log_mode_valid_signature_logs_no_warning(client, monkeypatch, caplog):
    monkeypatch.setenv("OURA_CLIENT_SECRET", SECRET)
    with caplog.at_level(logging.WARNING, logger="oura_mcp_server"):
        resp = await post_signed(client, compact(EVENT))
    assert resp.status_code == 200
    assert "signature" not in caplog.text


async def test_off_mode_skips_verification(client, monkeypatch, caplog):
    monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", "off")
    with caplog.at_level(logging.WARNING, logger="oura_mcp_server"):
        resp = await client.post("/webhook", json=EVENT)
    assert resp.status_code == 200
    assert "signature" not in caplog.text


@pytest.mark.parametrize(
    "raw, expected", [(None, "log"), ("", "log"), ("ENFORCE", "enforce"), ("off", "off"), ("bogus", "log")]
)
def test_signature_mode_parsing(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("OURA_WEBHOOK_SIGNATURE_MODE", raising=False)
    else:
        monkeypatch.setenv("OURA_WEBHOOK_SIGNATURE_MODE", raw)
    assert webhook_receiver.signature_mode() == expected


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
    server.mcp.auth = build_github_oauth()
    try:
        transport = httpx.ASGITransport(app=server.mcp.http_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webhook", params={"verification_token": "vtok", "challenge": "xyz"})
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "xyz"}
    finally:
        server.mcp.auth = old_auth
