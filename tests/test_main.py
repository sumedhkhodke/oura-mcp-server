"""Tests for the CLI entry point (argument dispatch and logging setup)."""

import logging

import pytest

from oura_mcp_server import __main__ as cli


@pytest.fixture
def basic_config(monkeypatch):
    captured = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: captured.update(kwargs))
    return captured


@pytest.fixture
def run_args(monkeypatch):
    import oura_mcp_server.server as server

    captured = {}
    monkeypatch.setattr(server, "run", lambda **kwargs: captured.update(kwargs))
    return captured


def test_help_exits_zero(monkeypatch, basic_config, capsys):
    monkeypatch.setattr("sys.argv", ["oura-mcp-server", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert "login" in capsys.readouterr().out


def test_logging_level_from_env(monkeypatch, basic_config):
    monkeypatch.setenv("OURA_MCP_LOG_LEVEL", "debug")
    monkeypatch.setattr("sys.argv", ["oura-mcp-server", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    assert basic_config["level"] == "DEBUG"
    assert basic_config["stream"] is cli.sys.stderr


def test_invalid_logging_level_falls_back_to_info(monkeypatch, basic_config):
    monkeypatch.setenv("OURA_MCP_LOG_LEVEL", "LOUD")
    monkeypatch.setattr("sys.argv", ["oura-mcp-server", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert basic_config["level"] == "INFO"


def test_default_command_serves_stdio(monkeypatch, basic_config, run_args):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr("sys.argv", ["oura-mcp-server"])
    cli.main()
    assert run_args == {"transport": "stdio", "host": "127.0.0.1", "port": 8000}


@pytest.mark.parametrize("command", ["serve", "run"])
def test_serve_http_dispatch(monkeypatch, basic_config, run_args, command):
    monkeypatch.setattr(
        "sys.argv", ["oura-mcp-server", command, "--transport", "http", "--host", "0.0.0.0", "--port", "9001"]
    )
    cli.main()
    assert run_args == {"transport": "http", "host": "0.0.0.0", "port": 9001}


def test_serve_reads_host_and_port_from_env(monkeypatch, basic_config, run_args):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "7777")
    monkeypatch.setattr("sys.argv", ["oura-mcp-server", "--transport", "http"])
    cli.main()
    assert run_args == {"transport": "http", "host": "0.0.0.0", "port": 7777}


def test_login_dispatch(monkeypatch, basic_config):
    import oura_mcp_server.oauth as oauth

    seen = {}

    def fake_login(argv):
        seen["argv"] = argv
        return 3

    monkeypatch.setattr(oauth, "login_command", fake_login)
    monkeypatch.setattr("sys.argv", ["oura-mcp-server", "login", "--no-browser"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 3
    assert seen["argv"] == ["--no-browser"]


def test_run_alias_is_documented():
    assert "run" in (cli.__doc__ or "")
