"""Deterministic, non-LLM output checks.

Each check type has a validator (run when a case is stored, so bad specs are
rejected early) and a runner (run at eval time against the model output).
Messages describe the check spec, never quote the model output, so eval
records stay compact and cannot leak sensitive output content into tables
that are meant to be summaries.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .errors import ValidationError
from .models import CheckSpec


@dataclass(frozen=True)
class CheckOutcome:
    type: str
    passed: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "passed": self.passed, "message": self.message}


def _require_str(params: Mapping[str, Any], key: str, check: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or value == "":
        raise ValidationError(f"check '{check}': param '{key}' must be a non-empty string")
    return value


def _require_int(params: Mapping[str, Any], key: str, check: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"check '{check}': param '{key}' must be a non-negative integer")
    return value


def _validate_contains(params: Mapping[str, Any], check: str) -> None:
    _require_str(params, "value", check)
    if "case_sensitive" in params and not isinstance(params["case_sensitive"], bool):
        raise ValidationError(f"check '{check}': param 'case_sensitive' must be a boolean")


def _validate_regex(params: Mapping[str, Any], check: str) -> None:
    pattern = _require_str(params, "pattern", check)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValidationError(f"check '{check}': invalid regex: {exc}") from exc


def _validate_length(params: Mapping[str, Any], check: str) -> None:
    _require_int(params, "value", check)


def _validate_is_json(params: Mapping[str, Any], check: str) -> None:
    if params:
        raise ValidationError(f"check '{check}': takes no params")


def _run_contains(params: Mapping[str, Any], output: str) -> CheckOutcome:
    needle = params["value"]
    haystack = output
    if not params.get("case_sensitive", True):
        needle, haystack = needle.lower(), haystack.lower()
    passed = needle in haystack
    return CheckOutcome(
        "contains", passed,
        f"expected substring {params['value']!r} " + ("found" if passed else "NOT found"),
    )


def _run_not_contains(params: Mapping[str, Any], output: str) -> CheckOutcome:
    needle = params["value"]
    haystack = output
    if not params.get("case_sensitive", True):
        needle, haystack = needle.lower(), haystack.lower()
    passed = needle not in haystack
    return CheckOutcome(
        "not_contains", passed,
        f"forbidden substring {params['value']!r} " + ("absent" if passed else "PRESENT"),
    )


def _run_regex(params: Mapping[str, Any], output: str) -> CheckOutcome:
    passed = re.search(params["pattern"], output, re.MULTILINE) is not None
    return CheckOutcome(
        "regex", passed,
        f"pattern {params['pattern']!r} " + ("matched" if passed else "did NOT match"),
    )


def _run_not_regex(params: Mapping[str, Any], output: str) -> CheckOutcome:
    passed = re.search(params["pattern"], output, re.MULTILINE) is None
    return CheckOutcome(
        "not_regex", passed,
        f"forbidden pattern {params['pattern']!r} " + ("absent" if passed else "MATCHED"),
    )


def _run_is_json(params: Mapping[str, Any], output: str) -> CheckOutcome:
    try:
        json.loads(output.strip())
        return CheckOutcome("is_json", True, "output parses as JSON")
    except json.JSONDecodeError as exc:
        return CheckOutcome(
            "is_json", False, f"output is not valid JSON (line {exc.lineno}, col {exc.colno})"
        )


def _run_min_length(params: Mapping[str, Any], output: str) -> CheckOutcome:
    limit = params["value"]
    passed = len(output) >= limit
    return CheckOutcome("min_length", passed, f"length {len(output)} (minimum {limit})")


def _run_max_length(params: Mapping[str, Any], output: str) -> CheckOutcome:
    limit = params["value"]
    passed = len(output) <= limit
    return CheckOutcome("max_length", passed, f"length {len(output)} (maximum {limit})")


_Validator = Callable[[Mapping[str, Any], str], None]
_Runner = Callable[[Mapping[str, Any], str], CheckOutcome]

CHECK_TYPES: dict[str, tuple[_Validator, _Runner]] = {
    "contains": (_validate_contains, _run_contains),
    "not_contains": (_validate_contains, _run_not_contains),
    "regex": (_validate_regex, _run_regex),
    "not_regex": (_validate_regex, _run_not_regex),
    "is_json": (_validate_is_json, _run_is_json),
    "min_length": (_validate_length, _run_min_length),
    "max_length": (_validate_length, _run_max_length),
}


def validate_check(spec: CheckSpec) -> None:
    entry = CHECK_TYPES.get(spec.type)
    if entry is None:
        raise ValidationError(
            f"unknown check type '{spec.type}' (known: {', '.join(sorted(CHECK_TYPES))})"
        )
    entry[0](spec.params, spec.type)


def run_check(spec: CheckSpec, output: str) -> CheckOutcome:
    validate_check(spec)
    return CHECK_TYPES[spec.type][1](spec.params, output)
