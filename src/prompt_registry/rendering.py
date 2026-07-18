"""Strict {{ variable }} template rendering.

Deliberately tiny: no expressions, no filters, no code execution. A template
placeholder is `{{ name }}` where name matches [A-Za-z_][A-Za-z0-9_]*.

Strictness rules (all hard errors, never silent):
- every placeholder in the template must be declared in the variable schema
- every declared variable must appear in the template
- rendering with a missing required variable fails
- rendering with an unknown value key fails

Variable *values* are never logged by this module.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from .errors import RenderError, ValidationError
from .models import VariableSpec

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# Anything else brace-like that is not a valid placeholder, e.g. {{ 1bad }},
# {{missing_brace} is left alone on purpose: prompts legitimately contain
# braces (JSON examples, code). Only well-formed {{ name }} is a placeholder.


def extract_placeholders(body: str) -> tuple[str, ...]:
    """Unique placeholder names in first-appearance order."""
    seen: dict[str, None] = {}
    for match in PLACEHOLDER_RE.finditer(body):
        seen.setdefault(match.group(1))
    return tuple(seen)


def validate_template(body: str, variables: Sequence[VariableSpec]) -> None:
    """Enforce that the variable schema and the template agree exactly."""
    placeholders = set(extract_placeholders(body))
    declared = [v.name for v in variables]
    duplicates = {n for n in declared if declared.count(n) > 1}
    if duplicates:
        raise ValidationError(
            f"duplicate variable declarations: {', '.join(sorted(duplicates))}"
        )
    undeclared = placeholders - set(declared)
    unused = set(declared) - placeholders
    problems = []
    if undeclared:
        problems.append(
            f"placeholders not declared as variables: {', '.join(sorted(undeclared))}"
        )
    if unused:
        problems.append(
            f"declared variables not used in template: {', '.join(sorted(unused))}"
        )
    if problems:
        raise ValidationError("; ".join(problems))


def render(
    body: str,
    variables: Sequence[VariableSpec],
    values: Mapping[str, str],
) -> str:
    """Render the template with the given values, strictly."""
    spec_by_name = {v.name: v for v in variables}

    unknown = sorted(set(values) - set(spec_by_name))
    if unknown:
        raise RenderError(f"unknown variables provided: {', '.join(unknown)}")

    missing = sorted(
        name
        for name, spec in spec_by_name.items()
        if spec.required and name not in values
    )
    if missing:
        raise RenderError(f"missing required variables: {', '.join(missing)}")

    for name, value in values.items():
        if not isinstance(value, str):
            raise RenderError(f"variable '{name}': value must be a string")

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        spec = spec_by_name.get(name)
        if spec is None:
            # validate_template() at write time should make this unreachable,
            # but stay strict if a raw body sneaks through.
            raise RenderError(f"placeholder '{name}' is not a declared variable")
        if name in values:
            return values[name]
        assert spec.default is not None  # guaranteed by VariableSpec invariant
        return spec.default

    return PLACEHOLDER_RE.sub(substitute, body)
