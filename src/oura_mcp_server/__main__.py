"""Entry point: ``python -m oura_mcp_server`` / ``oura-mcp-server``."""

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
