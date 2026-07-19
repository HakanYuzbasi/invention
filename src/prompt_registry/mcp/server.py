"""FastMCP wrapper exposing the read-only tool surface over stdio.

This is the only module in the package that imports the MCP SDK. All tool
behavior lives in tools.py (SDK-free); this file only does registration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools

INSTRUCTIONS = (
    "Read-only access to a local prompt registry. Search prompts, inspect "
    "immutable prompt versions and their variable schemas, and render prompts "
    "with variables. This server cannot create, modify, evaluate, or execute "
    "anything; use the prompt-registry CLI for writes."
)


def create_server(db_path: Path) -> FastMCP:
    app = FastMCP(name="prompt-registry", instructions=INSTRUCTIONS)

    @app.tool()
    def search_prompts(
        query: str = "", tag: str | None = None, limit: int = 20
    ) -> dict[str, Any]:
        """Search prompts by substring over id, name, description, latest body,
        and tags. Empty query lists all prompts. Returns summaries with a short
        preview of the latest version (limit is capped at 50)."""
        return tools.search_prompts(db_path, query=query, tag=tag, limit=limit)

    @app.tool()
    def get_prompt(prompt: str, version: int | None = None) -> dict[str, Any]:
        """Fetch one prompt by id (slug) or exact name: metadata, tags, and the
        selected immutable version (default: latest) with its variable schema,
        full template body, and content hash."""
        return tools.get_prompt(db_path, prompt=prompt, version=version)

    @app.tool()
    def render_prompt(
        prompt: str,
        variables: dict[str, str] | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Render a prompt version (default: latest) with the given variable
        values. Strict: missing required variables or unknown names return a
        structured error. Values are used in-memory only — never stored."""
        return tools.render_prompt(
            db_path, prompt=prompt, variables=variables, version=version
        )

    @app.tool()
    def list_prompt_versions(prompt: str) -> dict[str, Any]:
        """List all immutable versions of a prompt (number, created_at, note,
        content hash), oldest first."""
        return tools.list_prompt_versions(db_path, prompt=prompt)

    return app
