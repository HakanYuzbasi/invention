"""Entry point for the read-only MCP stdio server.

Run as `prompt-registry-mcp` or `python -m prompt_registry.mcp`.

Rules:
- stdout carries MCP protocol traffic ONLY; all diagnostics go to stderr
- the resolved database path is printed only with --debug (paths can reveal
  usernames and machine layout)
- if the optional MCP SDK extra is not installed, print install guidance to
  stderr and exit with code 3 (base registry/CLI use never needs the SDK)
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from typing import Sequence

from .. import __version__
from ..store import resolve_db_path

EXIT_MISSING_SDK = 3

INSTALL_HINT = (
    "the MCP server requires the optional 'mcp' extra, which is not installed.\n"
    "Install it with:\n"
    "    pip install 'prompt-registry[mcp]'\n"
    "The base prompt-registry CLI works without it."
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-registry-mcp",
        description="Local read-only MCP stdio server for the prompt registry.",
    )
    parser.add_argument(
        "--db",
        help="path to the registry database "
             "(default: $PROMPT_REGISTRY_DB or ~/.prompt-registry/registry.db)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="verbose stderr diagnostics, including the resolved database path",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if importlib.util.find_spec("mcp") is None:
        print(f"error: {INSTALL_HINT}", file=sys.stderr)
        return EXIT_MISSING_SDK

    db_path = resolve_db_path(args.db)
    print(
        f"prompt-registry-mcp {__version__} starting "
        f"(transport=stdio, mode=read-only, database=configured)",
        file=sys.stderr,
    )
    if args.debug:
        print(f"debug: resolved database path: {db_path}", file=sys.stderr)
    if not db_path.exists():
        print(
            "warning: the configured registry database does not exist yet; "
            "tools will return 'registry_unavailable' until you run "
            "'prompt-registry init'",
            file=sys.stderr,
        )

    from .server import create_server  # deferred: requires the SDK

    create_server(db_path).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
