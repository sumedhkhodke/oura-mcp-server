"""Tests for HTTP transport bearer-token auth wiring."""

import pytest

from oura_mcp_server import server


def test_no_token_means_no_auth(monkeypatch):
    monkeypatch.delenv("OURA_MCP_AUTH_TOKEN", raising=False)
    assert server.build_auth_from_env() is None


def test_token_builds_verifier(monkeypatch):
    monkeypatch.setenv("OURA_MCP_AUTH_TOKEN", "secret-abc")
    verifier = server.build_auth_from_env()
    assert verifier is not None
    assert type(verifier).__name__ == "StaticTokenVerifier"


def test_multiple_tokens_supported(monkeypatch):
    monkeypatch.setenv("OURA_MCP_AUTH_TOKEN", "a, b ,c")
    verifier = server.build_auth_from_env()
    # tokens dict is stored on the verifier; all three should be present
    assert set(verifier.tokens) == {"a", "b", "c"}


def test_http_without_token_is_fail_closed(monkeypatch):
    monkeypatch.delenv("OURA_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OURA_MCP_ALLOW_NO_AUTH", raising=False)
    with pytest.raises(SystemExit, match="Refusing to start an unauthenticated"):
        server.run(transport="http")
