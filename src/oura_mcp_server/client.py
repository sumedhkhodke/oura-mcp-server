"""Async HTTP client for the Oura Ring v2 API.

Handles bearer authentication, transparent pagination over ``next_token``,
and turns HTTP errors into readable messages instead of raw stack traces.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.ouraring.com/v2"


class OuraError(RuntimeError):
    """Raised when the Oura API returns an error the caller should see."""


class OuraClient:
    """Thin async wrapper over the Oura v2 REST API.

    A single client instance is shared across all tool calls. It keeps one
    ``httpx.AsyncClient`` (connection pooling) and injects the bearer token on
    every request.
    """

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        token = access_token or os.environ.get("OURA_ACCESS_TOKEN")
        if not token:
            raise OuraError(
                "No Oura access token found. Set the OURA_ACCESS_TOKEN environment "
                "variable (see .env.example)."
            )
        self._base_url = (base_url or os.environ.get("OURA_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:  # network / timeout / DNS
            raise OuraError(f"Request to Oura failed: {exc}") from exc

        if resp.status_code == 401:
            raise OuraError(
                "Oura rejected the access token (401 Unauthorized). The token may be "
                "invalid, expired, or missing the required scope."
            )
        if resp.status_code == 403:
            raise OuraError(
                "Oura returned 403 Forbidden. Your token likely lacks the scope for this "
                "data type, or the account has no active subscription for it."
            )
        if resp.status_code == 429:
            raise OuraError("Oura rate limit hit (429). Wait a moment and try again.")
        if resp.status_code >= 400:
            raise OuraError(f"Oura API error {resp.status_code}: {resp.text[:500]}")

        return resp.json()

    async def get_collection(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """GET a paginated ``usercollection`` endpoint and return all documents.

        Transparently follows ``next_token`` until the collection is exhausted.
        ``params`` with ``None`` values are dropped so callers can pass optional
        date filters without conditionals.
        """
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        path = f"/usercollection/{endpoint}"
        results: list[dict[str, Any]] = []
        next_token: str | None = None

        while True:
            page_params = dict(clean)
            if next_token:
                page_params["next_token"] = next_token
            payload = await self._request(path, page_params)
            results.extend(payload.get("data", []))
            next_token = payload.get("next_token")
            if not next_token:
                break
        return results

    async def get_document(self, endpoint: str, document_id: str) -> dict[str, Any]:
        """GET a single document by id from a ``usercollection`` endpoint."""
        return await self._request(f"/usercollection/{endpoint}/{document_id}")

    async def get_single(self, endpoint: str) -> dict[str, Any]:
        """GET a non-paginated single-object endpoint (e.g. personal_info)."""
        return await self._request(f"/usercollection/{endpoint}")
