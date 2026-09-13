"""Tests for client-facing GitHub OAuth wiring."""

import fastmcp
import httpx
import pytest
from fastmcp.server.auth import OAuthProxy

from oura_mcp_server import server
from oura_mcp_server.mcp_auth import (
    ALLOWED_CLIENT_REDIRECT_URIS,
    AllowlistedGitHubTokenVerifier,
    McpAuthConfigurationError,
    build_github_oauth,
    parse_allowed_github_users,
    public_base_url,
)


@pytest.fixture
def oauth_env():
    return {
        "OURA_MCP_GITHUB_CLIENT_ID": "github-client-id",
        "OURA_MCP_GITHUB_CLIENT_SECRET": "github-client-secret",
        "OURA_MCP_ALLOWED_GITHUB_USERS": "SumedhKhodke",
        "OURA_MCP_JWT_SIGNING_KEY": "a-stable-random-signing-key",
        "OURA_MCP_BASE_URL": "https://oura.example.com",
    }


def test_allowlist_parsing_is_case_insensitive():
    assert parse_allowed_github_users(" SumedhKhodke, Friend ") == {"sumedhkhodke", "friend"}


def test_railway_domain_builds_public_base_url():
    assert public_base_url({"RAILWAY_PUBLIC_DOMAIN": "oura.example.com"}) == "https://oura.example.com"


@pytest.mark.parametrize(
    "url",
    ["http://oura.example.com", "https://oura.example.com/mcp", "https://oura.example.com?bad=1"],
)
def test_public_base_url_rejects_unsafe_or_non_origin_values(url):
    with pytest.raises(McpAuthConfigurationError):
        public_base_url({"OURA_MCP_BASE_URL": url})


def test_build_oauth_requires_every_security_setting(oauth_env):
    del oauth_env["OURA_MCP_ALLOWED_GITHUB_USERS"]
    with pytest.raises(McpAuthConfigurationError, match="OURA_MCP_ALLOWED_GITHUB_USERS"):
        build_github_oauth(oauth_env)


def test_builds_oauth_proxy_with_claude_redirects(monkeypatch, tmp_path, oauth_env):
    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)
    auth = build_github_oauth(oauth_env)
    assert isinstance(auth, OAuthProxy)
    assert auth._allowed_client_redirect_uris == ALLOWED_CLIENT_REDIRECT_URIS
    assert auth._token_validator.allowed_users == {"sumedhkhodke"}


def test_http_run_attaches_oauth_provider(monkeypatch, tmp_path, oauth_env):
    for name, value in oauth_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(fastmcp.settings, "home", tmp_path)

    run_args = {}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: run_args.update(kwargs))
    old_auth = server.mcp.auth
    try:
        server.run(transport="http", host="0.0.0.0", port=9000)
        assert isinstance(server.mcp.auth, OAuthProxy)
        assert run_args == {"transport": "http", "host": "0.0.0.0", "port": 9000}
    finally:
        server.mcp.auth = old_auth


async def test_verifier_accepts_allowlisted_user_case_insensitively():
    def respond(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 1, "login": "SumedhKhodke"})
        return httpx.Response(200, headers={"X-OAuth-Scopes": "read:user"}, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        verifier = AllowlistedGitHubTokenVerifier(
            frozenset({"sumedhkhodke"}), required_scopes=["read:user"], http_client=client
        )
        assert await verifier.verify_token("valid-token") is not None


async def test_verifier_rejects_non_allowlisted_user():
    def respond(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 2, "login": "someone-else"})
        return httpx.Response(200, headers={"X-OAuth-Scopes": "read:user"}, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        verifier = AllowlistedGitHubTokenVerifier(
            frozenset({"sumedhkhodke"}), required_scopes=["read:user"], http_client=client
        )
        assert await verifier.verify_token("valid-but-not-allowed") is None


def test_http_without_oauth_config_is_fail_closed(monkeypatch):
    for name in (
        "OURA_MCP_GITHUB_CLIENT_ID",
        "OURA_MCP_GITHUB_CLIENT_SECRET",
        "OURA_MCP_ALLOWED_GITHUB_USERS",
        "OURA_MCP_JWT_SIGNING_KEY",
        "OURA_MCP_BASE_URL",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="Refusing to start HTTP transport"):
        server.run(transport="http")


def test_public_base_url_requires_configuration():
    with pytest.raises(McpAuthConfigurationError, match="Missing OURA_MCP_BASE_URL"):
        public_base_url({})


def test_verifier_rejects_empty_allowlist():
    with pytest.raises(McpAuthConfigurationError, match="OURA_MCP_ALLOWED_GITHUB_USERS"):
        AllowlistedGitHubTokenVerifier(frozenset())


async def test_verifier_returns_none_when_upstream_rejects_token():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
        verifier = AllowlistedGitHubTokenVerifier(
            frozenset({"sumedhkhodke"}), required_scopes=["read:user"], http_client=client
        )
        assert await verifier.verify_token("revoked") is None
