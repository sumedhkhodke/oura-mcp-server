"""Client-facing OAuth authentication for the remote MCP server.

The Oura API credentials identify the single Oura account exposed by this
personal server.  This module protects that account separately: MCP clients
authenticate with GitHub through FastMCP's OAuth proxy, and only explicitly
allowlisted GitHub users may finish the flow.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubTokenVerifier

logger = logging.getLogger("oura_mcp_server.auth")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

# Claude hosted surfaces use one fixed callback. Claude Code uses an ephemeral
# RFC 8252 loopback port, so both loopback host forms need wildcard ports.
ALLOWED_CLIENT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "http://localhost:*",
    "http://127.0.0.1:*",
]


class McpAuthConfigurationError(RuntimeError):
    """Raised when remote MCP OAuth is not safely configured."""


def parse_allowed_github_users(raw: str) -> frozenset[str]:
    """Parse a comma-separated GitHub login allowlist case-insensitively."""
    return frozenset(login.strip().casefold() for login in raw.split(",") if login.strip())


def public_base_url(env: Mapping[str, str]) -> str:
    """Resolve and validate the externally reachable OAuth server origin."""
    raw = env.get("OURA_MCP_BASE_URL", "").strip()
    if not raw:
        railway_domain = env.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            raw = f"https://{railway_domain}"
    if not raw:
        raise McpAuthConfigurationError(
            "Missing OURA_MCP_BASE_URL (for Railway, RAILWAY_PUBLIC_DOMAIN may be used instead)."
        )

    base_url = raw.rstrip("/")
    parsed = urlsplit(base_url)
    is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
        raise McpAuthConfigurationError("OURA_MCP_BASE_URL must use HTTPS (HTTP is allowed only for loopback testing).")
    if not parsed.netloc or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise McpAuthConfigurationError("OURA_MCP_BASE_URL must be an origin without a path, query, or fragment.")
    return base_url


class AllowlistedGitHubTokenVerifier(GitHubTokenVerifier):  # type: ignore[misc, unused-ignore]
    """Accept a valid GitHub token only when its login is allowlisted."""

    def __init__(self, allowed_users: frozenset[str], **kwargs: Any) -> None:
        if not allowed_users:
            raise McpAuthConfigurationError("OURA_MCP_ALLOWED_GITHUB_USERS must contain at least one GitHub login.")
        super().__init__(**kwargs)
        self.allowed_users = allowed_users

    async def verify_token(self, token: str) -> AccessToken | None:
        access_token = await super().verify_token(token)
        if access_token is None:
            return None

        login = access_token.claims.get("login")
        if not isinstance(login, str) or login.casefold() not in self.allowed_users:
            logger.warning("Rejected GitHub OAuth login %r: user is not allowlisted", login)
            return None
        return access_token


def build_github_oauth(env: Mapping[str, str] | None = None) -> OAuthProxy:
    """Build the production OAuth proxy from environment configuration."""
    env = os.environ if env is None else env
    required = {
        "OURA_MCP_GITHUB_CLIENT_ID": env.get("OURA_MCP_GITHUB_CLIENT_ID", "").strip(),
        "OURA_MCP_GITHUB_CLIENT_SECRET": env.get("OURA_MCP_GITHUB_CLIENT_SECRET", "").strip(),
        "OURA_MCP_ALLOWED_GITHUB_USERS": env.get("OURA_MCP_ALLOWED_GITHUB_USERS", "").strip(),
        "OURA_MCP_JWT_SIGNING_KEY": env.get("OURA_MCP_JWT_SIGNING_KEY", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise McpAuthConfigurationError(f"Missing remote OAuth configuration: {', '.join(missing)}")

    allowed_users = parse_allowed_github_users(required["OURA_MCP_ALLOWED_GITHUB_USERS"])
    verifier = AllowlistedGitHubTokenVerifier(
        allowed_users,
        required_scopes=["read:user"],
        cache_ttl_seconds=300,
    )
    return OAuthProxy(
        upstream_authorization_endpoint=GITHUB_AUTHORIZE_URL,
        upstream_token_endpoint=GITHUB_TOKEN_URL,
        upstream_client_id=required["OURA_MCP_GITHUB_CLIENT_ID"],
        upstream_client_secret=required["OURA_MCP_GITHUB_CLIENT_SECRET"],
        token_verifier=verifier,
        base_url=public_base_url(env),
        service_documentation_url="https://github.com/sumedhkhodke/oura-mcp-server",
        allowed_client_redirect_uris=ALLOWED_CLIENT_REDIRECT_URIS,
        valid_scopes=["read:user"],
        jwt_signing_key=required["OURA_MCP_JWT_SIGNING_KEY"],
        require_authorization_consent=True,
    )
