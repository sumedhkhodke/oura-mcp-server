"""Entry point: ``python -m oura_mcp_server`` / ``oura-mcp-server``.

Subcommands:
  (default) / serve   Run the MCP server over stdio.
  login               Authenticate with Oura via OAuth2 and store tokens.
"""

import sys


def main() -> None:
    argv = sys.argv[1:]
    command = argv[0] if argv else "serve"

    if command == "login":
        from .oauth import login_command

        raise SystemExit(login_command(argv[1:]))

    if command in ("serve", "run"):
        argv = argv[1:]  # allow explicit `serve`
    if command in ("-h", "--help", "help"):
        print(__doc__)
        raise SystemExit(0)

    from .server import run

    run()


if __name__ == "__main__":
    main()
