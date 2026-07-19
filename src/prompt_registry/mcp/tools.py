"""SDK-free implementations of the read-only MCP tools.

Each function returns a structured envelope:
    success: {"ok": True,  "data": {...}}
    failure: {"ok": False, "error": {"code": "...", "message": "..."}}

Safety rules enforced here:
- registry access goes exclusively through ReadOnlyRegistry (mode=ro SQLite)
- error messages never contain the database path, environment values, or
  exception traces; render errors name variables, never values
- supplied variables and rendered output are returned to the caller only —
  never persisted, never logged
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from ..errors import NotFoundError, RegistryError, RenderError, ValidationError
from ..models import Prompt, PromptVersion
from ..readonly import SEARCH_LIMIT_DEFAULT, ReadOnlyRegistry
from ..rendering import render

logger = logging.getLogger(__name__)

_INIT_HINT = (
    "the registry database does not exist yet; initialize it with "
    "'prompt-registry init' (or point the server at the right database "
    "via --db or PROMPT_REGISTRY_DB)"
)
_INVALID_HINT = (
    "the configured database file exists but is not a valid prompt-registry "
    "database; check that --db / PROMPT_REGISTRY_DB points at a registry "
    "created by 'prompt-registry init'"
)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _err(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _open(db_path: Path) -> ReadOnlyRegistry | dict[str, Any]:
    """Open the registry read-only, or return a safe structured error."""
    if not Path(db_path).expanduser().exists():
        return _err("registry_unavailable", _INIT_HINT)
    try:
        return ReadOnlyRegistry.open(db_path)
    except RegistryError:
        return _err("registry_invalid", _INVALID_HINT)


def _prompt_summary(prompt: Prompt) -> dict[str, Any]:
    return {
        "id": prompt.id,
        "name": prompt.name,
        "description": prompt.description,
        "tags": list(prompt.tags),
        "latest_version": prompt.latest_version,
    }


def _version_meta(version: PromptVersion) -> dict[str, Any]:
    return {
        "number": version.version,
        "created_at": version.created_at,
        "note": version.note,
        "content_hash": version.content_hash,
    }


def _check_version_arg(version: Any) -> int | None:
    if version is None:
        return None
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValidationError("version must be a positive integer")
    return version


def search_prompts(
    db_path: Path,
    query: str = "",
    tag: str | None = None,
    limit: int = SEARCH_LIMIT_DEFAULT,
) -> dict[str, Any]:
    registry = _open(db_path)
    if isinstance(registry, dict):
        return registry
    try:
        with registry:
            if not isinstance(query, str):
                raise ValidationError("query must be a string")
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise ValidationError("limit must be an integer")
            results = registry.search(query, tag=tag, limit=limit)
        return _ok(
            {
                "results": [
                    {**_prompt_summary(prompt), "preview": preview}
                    for prompt, preview in results
                ]
            }
        )
    except RegistryError as exc:
        return _domain_error(exc)
    except Exception:
        return _internal_error("search_prompts")


def get_prompt(
    db_path: Path, prompt: str, version: int | None = None
) -> dict[str, Any]:
    registry = _open(db_path)
    if isinstance(registry, dict):
        return registry
    try:
        with registry:
            wanted = _check_version_arg(version)
            meta = registry.get_prompt(prompt)
            selected = registry.get_version(meta.id, wanted)
        return _ok(
            {
                **_prompt_summary(meta),
                "selected_version": {
                    **_version_meta(selected),
                    "variables": [v.to_dict() for v in selected.variables],
                    "body": selected.body,
                },
            }
        )
    except RegistryError as exc:
        return _domain_error(exc)
    except Exception:
        return _internal_error("get_prompt")


def render_prompt(
    db_path: Path,
    prompt: str,
    variables: Mapping[str, Any] | None = None,
    version: int | None = None,
) -> dict[str, Any]:
    registry = _open(db_path)
    if isinstance(registry, dict):
        return registry
    try:
        with registry:
            wanted = _check_version_arg(version)
            values = _check_variables_arg(variables)
            meta = registry.get_prompt(prompt)
            selected = registry.get_version(meta.id, wanted)
            rendered = render(selected.body, selected.variables, values)
        return _ok(
            {
                "id": meta.id,
                "version_number": selected.version,
                "content_hash": selected.content_hash,
                "rendered": rendered,
            }
        )
    except RegistryError as exc:
        return _domain_error(exc)
    except Exception:
        return _internal_error("render_prompt")


def list_prompt_versions(db_path: Path, prompt: str) -> dict[str, Any]:
    registry = _open(db_path)
    if isinstance(registry, dict):
        return registry
    try:
        with registry:
            meta = registry.get_prompt(prompt)
            versions = registry.list_versions(meta.id)
        return _ok(
            {
                "id": meta.id,
                "versions": [_version_meta(v) for v in versions],
            }
        )
    except RegistryError as exc:
        return _domain_error(exc)
    except Exception:
        return _internal_error("list_prompt_versions")


def _check_variables_arg(variables: Mapping[str, Any] | None) -> dict[str, str]:
    if variables is None:
        return {}
    if not isinstance(variables, Mapping):
        raise ValidationError("variables must be an object of name -> string value")
    bad_keys = sorted(
        str(key)
        for key, value in variables.items()
        if not isinstance(key, str) or not isinstance(value, str)
    )
    if bad_keys:
        # names only — never echo the values themselves
        raise ValidationError(
            f"variables must map string names to string values; "
            f"offending name(s): {', '.join(bad_keys)}"
        )
    return dict(variables)


def _domain_error(exc: RegistryError) -> dict[str, Any]:
    if isinstance(exc, NotFoundError):
        return _err("not_found", str(exc))
    if isinstance(exc, RenderError):
        return _err("render_error", str(exc))
    if isinstance(exc, ValidationError):
        return _err("invalid_input", str(exc))
    # remaining RegistryError subtypes (e.g. storage problems mid-read):
    # message may contain a path, so do not forward it
    return _err("registry_invalid", _INVALID_HINT)


def _internal_error(tool: str) -> dict[str, Any]:
    # class name only to local stderr logs; no message, no trace, no payloads
    logger.warning("unexpected error in %s", tool)
    return _err(
        "internal_error",
        f"internal error while serving {tool}; check the server's stderr log",
    )
