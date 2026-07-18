"""Model adapter seam.

v1 is manual-first: outputs are produced OUTSIDE this tool (Claude Code, a
local Gemma via Ollama, anything) and fed back in for evaluation. The core
therefore stays model-agnostic and fully offline.

This module exists so that a future local-model adapter (e.g. an Ollama HTTP
adapter for Gemma) has an obvious, typed place to plug in without touching
the registry core: implement ModelAdapter, and the evaluator can call
`generate()` instead of requiring a pre-captured output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelAdapter(Protocol):
    """Anything that can turn a rendered prompt into an output string."""

    name: str

    def generate(self, prompt_text: str) -> str:
        """Produce a model output for the given rendered prompt."""
        ...


@dataclass(frozen=True)
class ManualAdapter:
    """v1 adapter: wraps an output the user captured elsewhere."""

    output_text: str
    name: str = "manual"

    def generate(self, prompt_text: str) -> str:
        return self.output_text
