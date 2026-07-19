"""Read-only access facade over the registry.

ReadOnlyRegistry wraps a RegistryStore by COMPOSITION and exposes only read
operations — no mutation method exists on this class, and the underlying
SQLite connection is opened in mode=ro, so even a bug reaching the wrapped
store cannot write. This is the only registry entry point the MCP package
is allowed to use.

Nothing in this module logs prompt bodies or variable values.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import NotFoundError
from .models import Prompt, PromptVersion
from .store import RegistryStore

PREVIEW_MAX_CHARS = 160
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_MAX = 50

_WHITESPACE_RE = re.compile(r"\s+")


def make_preview(body: str, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    """Whitespace-collapsed, safely truncated first slice of a prompt body."""
    collapsed = _WHITESPACE_RE.sub(" ", body).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "…"


class ReadOnlyRegistry:
    """Composition-only read facade. Use as a context manager or call close()."""

    def __init__(self, store: RegistryStore):
        self._store = store

    @classmethod
    def open(cls, path: str | Path) -> "ReadOnlyRegistry":
        return cls(RegistryStore.open(path, read_only=True))

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "ReadOnlyRegistry":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- reads ---------------------------------------------------------------

    def resolve(self, ref: str) -> str:
        """Accept a prompt id (slug) or exact name (case-insensitive); return id."""
        if not isinstance(ref, str) or not ref.strip():
            raise NotFoundError("prompt reference must be a non-empty string")
        ref = ref.strip()
        try:
            return self._store.get_prompt(ref).id
        except NotFoundError:
            pass
        matches = [
            p for p in self._store.list_prompts() if p.name.lower() == ref.lower()
        ]
        if len(matches) == 1:
            return matches[0].id
        if len(matches) > 1:
            ids = ", ".join(p.id for p in matches)
            raise NotFoundError(
                f"name '{ref}' is ambiguous (matches prompts: {ids}); use the id"
            )
        raise NotFoundError(f"no prompt with id or name '{ref}'")

    def get_prompt(self, ref: str) -> Prompt:
        return self._store.get_prompt(self.resolve(ref))

    def get_version(self, ref: str, version: int | None = None) -> PromptVersion:
        return self._store.get_version(self.resolve(ref), version)

    def list_versions(self, ref: str) -> list[PromptVersion]:
        return self._store.list_versions(self.resolve(ref))

    def search(
        self,
        query: str,
        tag: str | None = None,
        limit: int = SEARCH_LIMIT_DEFAULT,
    ) -> list[tuple[Prompt, str]]:
        """Search prompts; returns (prompt, latest-body preview) pairs."""
        limit = max(1, min(int(limit), SEARCH_LIMIT_MAX))
        if query.strip():
            prompts = self._store.search_prompts(query, tag=tag)
        else:
            prompts = self._store.list_prompts(tag=tag)
        results: list[tuple[Prompt, str]] = []
        for prompt in prompts[:limit]:
            latest = self._store.get_version(prompt.id)
            results.append((prompt, make_preview(latest.body)))
        return results
