"""Entry point: ``python -m oura_mcp_server`` / ``oura-mcp-server``.

Subcommands:
  (default) / serve   Run the MCP server (stdio by default, or --transport http).
  login               Authenticate with Oura via OAuth2 and store tokens.
"""

import argparse
import os
import sys


def _serve(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="oura-mcp-server serve")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="stdio (default, for Claude Desktop/Code) or http (remote/hosted).",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HOST", "127.0.0.1"),
        help="Host for --transport http (env HOST; default 127.0.0.1).",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("PORT", "8000")),
        help="Port for --transport http (env PORT; default 8000). Railway sets PORT.",
    )
    args = parser.parse_args(argv)

    from .server import run

    run(transport=args.transport, host=args.host, port=args.port)


def main() -> None:
    argv = sys.argv[1:]
    command = argv[0] if argv else "serve"

    if command == "login":
        from .oauth import login_command

        raise SystemExit(login_command(argv[1:]))

    if command in ("-h", "--help", "help"):
        print(__doc__)
        raise SystemExit(0)

    rest = argv[1:] if command in ("serve", "run") else argv
    _serve(rest)


if __name__ == "__main__":
    main()
