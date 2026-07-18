"""Compare two prompt versions: unified diff of the body plus a human-readable
delta of the variable schema."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .models import PromptVersion, VariableSpec


def _describe(spec: VariableSpec) -> str:
    if spec.required:
        detail = "required"
    else:
        detail = f"optional, default={spec.default!r}"
    if spec.description:
        detail += f", desc={spec.description!r}"
    return f"{spec.name} ({detail})"


@dataclass(frozen=True)
class DiffReport:
    prompt_id: str
    from_version: int
    to_version: int
    identical: bool
    body_diff: str  # unified diff, empty if bodies are equal
    variable_changes: tuple[str, ...]  # human-readable lines, empty if equal

    def render_text(self) -> str:
        header = f"{self.prompt_id}: v{self.from_version} -> v{self.to_version}"
        if self.identical:
            return f"{header}\nversions are identical"
        parts = [header]
        if self.variable_changes:
            parts.append("variable schema changes:")
            parts.extend(f"  {line}" for line in self.variable_changes)
        if self.body_diff:
            parts.append(self.body_diff.rstrip("\n"))
        else:
            parts.append("(body unchanged)")
        return "\n".join(parts)


def diff_versions(a: PromptVersion, b: PromptVersion) -> DiffReport:
    body_diff = ""
    if a.body != b.body:
        body_diff = "".join(
            difflib.unified_diff(
                a.body.splitlines(keepends=True),
                b.body.splitlines(keepends=True),
                fromfile=f"{a.prompt_id}@v{a.version}",
                tofile=f"{b.prompt_id}@v{b.version}",
            )
        )

    a_vars = {v.name: v for v in a.variables}
    b_vars = {v.name: v for v in b.variables}
    changes: list[str] = []
    for name in sorted(set(a_vars) - set(b_vars)):
        changes.append(f"- removed {_describe(a_vars[name])}")
    for name in sorted(set(b_vars) - set(a_vars)):
        changes.append(f"+ added {_describe(b_vars[name])}")
    for name in sorted(set(a_vars) & set(b_vars)):
        if a_vars[name] != b_vars[name]:
            changes.append(f"~ changed {_describe(a_vars[name])} -> {_describe(b_vars[name])}")

    return DiffReport(
        prompt_id=a.prompt_id,
        from_version=a.version,
        to_version=b.version,
        identical=a.content_hash == b.content_hash,
        body_diff=body_diff,
        variable_changes=tuple(changes),
    )
