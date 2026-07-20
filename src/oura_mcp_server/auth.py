"""Authentication for the Oura MCP server.

Two ways to authenticate, resolved automatically at runtime by
:func:`default_token_source`:

1. ``OURA_ACCESS_TOKEN`` env var — a static bearer token (a legacy Personal
   Access Token, or any access token you paste in). Cannot self-refresh.
2. An OAuth2 token file written by ``oura-mcp-server login`` (default
   ``~/.oura-mcp/tokens.json``). Auto-refreshes using the stored refresh token.

The OAuth2 authorization-code flow itself lives in :mod:`oura_mcp_server.oauth`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

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
        payload: dict,
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
    try:
        path.chmod(0o600)
    except OSError:
        pass  # best-effort on platforms without POSIX perms
    return path


def load_token(path: Path | None = None) -> StoredToken | None:
    path = path or token_file_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return StoredToken(**data)


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

    async def get(self) -> str:
        if self._token.is_expired():
            await self.force_refresh()
        return self._token.access_token

    async def force_refresh(self) -> str | None:
        if not (self._token.refresh_token and self._token.client_id and self._token.client_secret):
            return None
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
            raise AuthError(
                f"Token refresh failed ({resp.status_code}). Re-run "
                f"`oura-mcp-server login`. Detail: {resp.text[:300]}"
            )
        self._token = StoredToken.from_token_response(
            resp.json(),
            client_id=self._token.client_id,
            client_secret=self._token.client_secret,
            fallback_refresh_token=self._token.refresh_token,
        )
        save_token(self._token, self._path)
        return self._token.access_token


def default_token_source() -> TokenSource:
    """Resolve the auth strategy: env var first, then the OAuth token file."""
    env_token = os.environ.get("OURA_ACCESS_TOKEN")
    if env_token:
        return StaticTokenSource(env_token)
    stored = load_token()
    if stored:
        return OAuthTokenSource(stored)
    raise AuthError(
        "No Oura credentials found. Either set OURA_ACCESS_TOKEN, or run "
        "`oura-mcp-server login` to authenticate with OAuth2."
    )
