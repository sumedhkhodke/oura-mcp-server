"""Oura webhook subscription client.

Webhooks let Oura push a notification to a callback URL whenever new data of a
given type is created/updated/deleted, instead of polling. Unlike the data API,
the webhook endpoints authenticate with the OAuth **application** credentials
(``x-client-id`` / ``x-client-secret`` headers), not a user bearer token.

Creating a subscription triggers a verification handshake: Oura sends a GET to
your ``callback_url`` with a challenge that your server must echo back, and
subscriptions expire and must be renewed. Running that callback endpoint is your
responsibility — these tools manage the subscriptions themselves.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .auth import load_token
from .client import OuraError

WEBHOOK_BASE = "https://api.ouraring.com/v2/webhook/subscription"

EVENT_TYPES = ("create", "update", "delete")
DATA_TYPES = (
    "tag",
    "enhanced_tag",
    "workout",
    "session",
    "sleep",
    "daily_sleep",
    "daily_readiness",
    "daily_activity",
    "daily_spo2",
    "sleep_time",
    "rest_mode_period",
    "ring_configuration",
    "daily_stress",
    "daily_cycle_phases",
)


def client_credentials() -> tuple[str, str]:
    """Resolve OAuth app credentials from env, else the saved token file."""
    cid = os.environ.get("OURA_CLIENT_ID")
    csec = os.environ.get("OURA_CLIENT_SECRET")
    if cid and csec:
        return cid, csec
    stored = load_token()
    if stored and stored.client_id and stored.client_secret:
        return stored.client_id, stored.client_secret
    raise OuraError(
        "Webhook operations need your OAuth app credentials. Set OURA_CLIENT_ID "
        "and OURA_CLIENT_SECRET, or run `oura-mcp-server login` (which stores them)."
    )


class WebhookClient:
    """Async wrapper over the Oura webhook subscription endpoints."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        if client_id is None or client_secret is None:
            client_id, client_secret = client_credentials()
        self._client = httpx.AsyncClient(
            headers={"x-client-id": client_id, "x-client-secret": client_secret},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _do(self, method: str, url: str, json: dict[str, Any] | None = None) -> Any:
        try:
            resp = await self._client.request(method, url, json=json)
        except httpx.HTTPError as exc:
            raise OuraError(f"Webhook request failed: {exc}") from exc
        if resp.status_code == 401 or resp.status_code == 403:
            raise OuraError(
                f"Oura rejected the app credentials ({resp.status_code}). Check OURA_CLIENT_ID / OURA_CLIENT_SECRET."
            )
        if resp.status_code >= 400:
            raise OuraError(f"Webhook API error {resp.status_code}: {resp.text[:500]}")
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        return resp.json()

    async def list(self) -> Any:
        return await self._do("GET", WEBHOOK_BASE)

    async def create(self, callback_url: str, verification_token: str, event_type: str, data_type: str) -> Any:
        return await self._do(
            "POST",
            WEBHOOK_BASE,
            json={
                "callback_url": callback_url,
                "verification_token": verification_token,
                "event_type": event_type,
                "data_type": data_type,
            },
        )

    async def delete(self, subscription_id: str) -> Any:
        return await self._do("DELETE", f"{WEBHOOK_BASE}/{subscription_id}")

    async def renew(self, subscription_id: str) -> Any:
        return await self._do("PUT", f"{WEBHOOK_BASE}/renew/{subscription_id}")
