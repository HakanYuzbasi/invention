"""Domain model. Frozen dataclasses with explicit (de)serialization.

Design rules:
- PromptVersion is immutable and append-only; identity is (prompt_id, version).
- The variable schema is stored on the version, so the variable contract
  always travels with the exact prompt text it belongs to.
- A variable is either required (no default) or optional (has a default);
  the two are mutually exclusive so rendering semantics stay unambiguous.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .errors import ValidationError

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def utc_now() -> str:
    """UTC timestamp, second precision, ISO 8601."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    """Short opaque identifier for cases and runs."""
    return uuid.uuid4().hex[:12]


def validate_slug(value: str, what: str = "id") -> str:
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise ValidationError(
            f"invalid {what} {value!r}: use lowercase letters, digits, '-' or '_' "
            f"(max 64 chars, must start with a letter or digit)"
        )
    return value


@dataclass(frozen=True)
class VariableSpec:
    """Schema for one template variable.

    Invariant: required XOR has-default. Required variables must be supplied
    at render time; optional variables fall back to their default.
    """

    name: str
    description: str = ""
    required: bool = True
    default: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not VAR_NAME_RE.match(self.name):
            raise ValidationError(
                f"invalid variable name {self.name!r}: use letters, digits, '_' "
                f"(must not start with a digit)"
            )
        if self.required and self.default is not None:
            raise ValidationError(
                f"variable '{self.name}': a required variable cannot have a default"
            )
        if not self.required and self.default is None:
            raise ValidationError(
                f"variable '{self.name}': an optional variable must define a default"
            )
        if self.default is not None and not isinstance(self.default, str):
            raise ValidationError(
                f"variable '{self.name}': default must be a string"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VariableSpec":
        if not isinstance(data, Mapping) or "name" not in data:
            raise ValidationError(f"invalid variable spec: {data!r}")
        return cls(
            name=data["name"],
            description=str(data.get("description", "")),
            required=bool(data.get("required", data.get("default") is None)),
            default=data.get("default"),
        )


def compute_content_hash(body: str, variables: Sequence[VariableSpec]) -> str:
    """Deterministic hash over prompt text + variable schema (canonical JSON)."""
    payload = json.dumps(
        {"body": body, "variables": [v.to_dict() for v in variables]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Prompt:
    id: str
    name: str
    description: str
    created_at: str
    tags: tuple[str, ...] = ()
    latest_version: int = 0


@dataclass(frozen=True)
class PromptVersion:
    prompt_id: str
    version: int
    body: str
    variables: tuple[VariableSpec, ...]
    note: str
    content_hash: str
    created_at: str

    def variables_json(self) -> str:
        return json.dumps([v.to_dict() for v in self.variables], ensure_ascii=False)

    @staticmethod
    def parse_variables(raw: str) -> tuple[VariableSpec, ...]:
        return tuple(VariableSpec.from_dict(d) for d in json.loads(raw))


@dataclass(frozen=True)
class CheckSpec:
    """One deterministic check applied to a model output.

    `type` is one of the registered check types in checks.py; `params` is a
    plain JSON-serializable mapping validated by checks.validate_check().
    """

    type: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CheckSpec":
        if not isinstance(data, Mapping) or "type" not in data:
            raise ValidationError(f"invalid check spec: {data!r}")
        params = data.get("params", {})
        if not isinstance(params, Mapping):
            raise ValidationError(f"check '{data['type']}': params must be an object")
        return cls(type=str(data["type"]), params=dict(params))


@dataclass(frozen=True)
class EvalCase:
    id: str
    prompt_id: str
    name: str
    variables: Mapping[str, str]
    checks: tuple[CheckSpec, ...]
    created_at: str

    def variables_json(self) -> str:
        return json.dumps(dict(self.variables), ensure_ascii=False)

    def checks_json(self) -> str:
        return json.dumps([c.to_dict() for c in self.checks], ensure_ascii=False)


@dataclass(frozen=True)
class EvalRun:
    id: str
    prompt_id: str
    prompt_version: int
    note: str
    output_source: str
    created_at: str


@dataclass(frozen=True)
class EvalResult:
    run_id: str
    case_id: str
    passed: bool | None  # None when the case has no automated checks
    details: tuple[Mapping[str, Any], ...]  # per-check outcome dicts
    rating: int | None = None
    comment: str = ""

    def details_json(self) -> str:
        return json.dumps([dict(d) for d in self.details], ensure_ascii=False)
