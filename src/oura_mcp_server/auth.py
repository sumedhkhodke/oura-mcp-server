"""Authentication for the Oura MCP server.

Three ways to authenticate, resolved automatically at runtime by
:func:`default_token_source` (highest precedence first):

1. ``OURA_REFRESH_TOKEN`` + ``OURA_CLIENT_ID`` + ``OURA_CLIENT_SECRET`` env vars
   — headless refresh mode for containers where ``oura-mcp-server login`` can't
   run. Optionally seeded with ``OURA_ACCESS_TOKEN``; refreshed tokens are
   persisted to the token file.
2. ``OURA_ACCESS_TOKEN`` env var alone — a static bearer token (a legacy
   Personal Access Token, or any access token you paste in). Cannot self-refresh.
3. An OAuth2 token file written by ``oura-mcp-server login`` (default
   ``~/.oura-mcp/tokens.json``). Auto-refreshes using the stored refresh token.

The OAuth2 authorization-code flow itself lives in :mod:`oura_mcp_server.oauth`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("oura_mcp_server.auth")

OURA_TOKEN_URL = "https://api.ouraring.com/oauth/token"

# Refresh a little before actual expiry to avoid racing the clock.
_EXPIRY_SKEW_SECONDS = 120


class AuthError(RuntimeError):
    """Raised when authentication cannot be established or refreshed."""


def token_file_path() -> Path:
    """Location of the persisted OAuth token file."""
    override = os.environ.get("OURA_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".oura-mcp" / "tokens.json"


@dataclass
class StoredToken:
    """Everything needed to use and refresh an OAuth2 grant.

    ``client_id``/``client_secret`` are persisted alongside the tokens so the
    server can refresh unattended without extra env vars. The file is written
    with ``0600`` permissions since it contains secrets.
    """

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None  # unix epoch seconds
    client_id: str | None = None
    client_secret: str | None = None
    scope: str | None = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False  # long-lived / unknown — assume valid, refresh on 401
        return time.time() >= (self.expires_at - _EXPIRY_SKEW_SECONDS)

    @classmethod
    def from_token_response(
        cls,
        payload: dict[str, Any],
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        fallback_refresh_token: str | None = None,
    ) -> StoredToken:
        expires_in = payload.get("expires_in")
        expires_at = time.time() + float(expires_in) if expires_in else None
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or fallback_refresh_token,
            expires_at=expires_at,
            client_id=client_id,
            client_secret=client_secret,
            scope=payload.get("scope"),
        )


def save_token(token: StoredToken, path: Path | None = None) -> Path:
    path = path or token_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(token), indent=2))
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return path


def load_token(path: Path | None = None) -> StoredToken | None:
    path = path or token_file_path()
    if not path.exists():
        return None
    unreadable = AuthError(f"Token file at {path} is unreadable; re-run `oura-mcp-server login`")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise unreadable from exc
    if not isinstance(data, dict) or not data.get("access_token"):
        raise unreadable
    known = {f.name for f in fields(StoredToken)}
    return StoredToken(**{k: v for k, v in data.items() if k in known})


class TokenSource:
    """Supplies a bearer token, and optionally refreshes it on demand."""

    async def get(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    async def force_refresh(self) -> str | None:
        """Return a freshly minted token, or ``None`` if not refreshable."""
        return None


class StaticTokenSource(TokenSource):
    """A fixed bearer token (env var / legacy PAT). Cannot refresh."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def get(self) -> str:
        return self._token


class OAuthTokenSource(TokenSource):
    """A token backed by the on-disk OAuth file, refreshed as needed."""

    def __init__(self, token: StoredToken, path: Path | None = None) -> None:
        self._token = token
        self._path = path or token_file_path()
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        if self._token.is_expired():
            async with self._lock:
                if self._token.is_expired():
                    await self._refresh()
        return self._token.access_token

    async def force_refresh(self) -> str | None:
        stale = self._token.access_token
        async with self._lock:
            if self._token.access_token != stale:
                return self._token.access_token
            return await self._refresh()

    async def _refresh(self) -> str | None:
        if not (self._token.refresh_token and self._token.client_id and self._token.client_secret):
            logger.warning("Cannot refresh Oura token: refresh_token/client_id/client_secret missing.")
            return None
        logger.info("Refreshing Oura access token (expires_at=%s).", self._token.expires_at)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OURA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._token.refresh_token,
                    "client_id": self._token.client_id,
                    "client_secret": self._token.client_secret,
                },
            )
        if resp.status_code >= 400:
            logger.error("Oura token refresh failed (%s): %s", resp.status_code, resp.text[:300])
            raise AuthError(
                f"Token refresh failed ({resp.status_code}). Re-run `oura-mcp-server login`. Detail: {resp.text[:300]}"
            )
        self._token = StoredToken.from_token_response(
            resp.json(),
            client_id=self._token.client_id,
            client_secret=self._token.client_secret,
            fallback_refresh_token=self._token.refresh_token,
        )
        saved = save_token(self._token, self._path)
        logger.info("Oura access token refreshed (expires_at=%s); saved to %s.", self._token.expires_at, saved)
        return self._token.access_token


def default_token_source() -> TokenSource:
    """Resolve the auth strategy.

    Precedence:

    1. ``OURA_REFRESH_TOKEN`` + ``OURA_CLIENT_ID`` + ``OURA_CLIENT_SECRET`` in
       the env — headless refresh mode for deployments (containers) where
       ``oura-mcp-server login`` can't run. Seeds a refreshable source from the
       env (plus ``OURA_ACCESS_TOKEN`` if given); refreshed tokens persist to
       the token file, which then wins on later resolutions.
    2. ``OURA_ACCESS_TOKEN`` alone — a static bearer (legacy PAT); can't refresh.
    3. The token file written by ``oura-mcp-server login``.
    """
    env_token = os.environ.get("OURA_ACCESS_TOKEN")
    refresh_token = os.environ.get("OURA_REFRESH_TOKEN")
    client_id = os.environ.get("OURA_CLIENT_ID")
    client_secret = os.environ.get("OURA_CLIENT_SECRET")
    if refresh_token and client_id and client_secret:
        # Headless refresh mode: an existing file (rotated by a previous
        # refresh) wins over the env seed.
        stored = load_token()
        if stored:
            return OAuthTokenSource(stored)
        seed = StoredToken(
            access_token=env_token or "",
            refresh_token=refresh_token,
            # No access token → mark expired so the first use refreshes eagerly.
            expires_at=None if env_token else 0,
            client_id=client_id,
            client_secret=client_secret,
        )
        return OAuthTokenSource(seed)
    if env_token:
        return StaticTokenSource(env_token)
    stored = load_token()
    if stored:
        return OAuthTokenSource(stored)
    raise AuthError(
        "No Oura credentials found. Either set OURA_ACCESS_TOKEN, or run "
        "`oura-mcp-server login` to authenticate with OAuth2."
    )
