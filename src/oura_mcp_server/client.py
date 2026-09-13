"""Async HTTP client for the Oura Ring v2 API.

Handles bearer authentication (static token or auto-refreshing OAuth),
transparent pagination over ``next_token``, and turns HTTP errors into readable
messages instead of raw stack traces.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .auth import AuthError, StaticTokenSource, TokenSource, default_token_source

DEFAULT_BASE_URL = "https://api.ouraring.com/v2"


class OuraError(RuntimeError):
    """Raised when the Oura API returns an error the caller should see."""


class OuraClient:
    """Thin async wrapper over the Oura v2 REST API.

    A single client instance is shared across all tool calls. It keeps one
    ``httpx.AsyncClient`` (connection pooling) and injects the current bearer
    token on every request, refreshing once on a 401 when possible.
    """

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        *,
        token_source: TokenSource | None = None,
        timeout: float = 30.0,
    ) -> None:
        if token_source is not None:
            self._auth = token_source
        elif access_token is not None:
            self._auth = StaticTokenSource(access_token)
        else:
            self._auth = default_token_source()

        self._base_url = (base_url or os.environ.get("OURA_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _authorized_get(self, path: str, params: dict[str, Any] | None) -> httpx.Response:
        token = await self._auth.get()
        resp = await self._client.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 401:
            # Token may have expired mid-flight; try one refresh then retry.
            new_token = await self._auth.force_refresh()
            if new_token:
                resp = await self._client.get(path, params=params, headers={"Authorization": f"Bearer {new_token}"})
        return resp

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._authorized_get(path, params)
        except AuthError as exc:
            raise OuraError(str(exc)) from exc
        except httpx.HTTPError as exc:  # network / timeout / DNS
            raise OuraError(f"Request to Oura failed: {exc}") from exc

        if resp.status_code == 401:
            raise OuraError(
                "Oura rejected the access token (401 Unauthorized). It may be invalid, "
                "expired, or missing the required scope. Re-run `oura-mcp-server login`."
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

    async def get_collection(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
