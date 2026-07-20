"""Base classes and shared types for portfolio target policies.

Every policy consumes the current active recommendation state and emits a set of
:class:`TargetHolding`. **Every decision must carry a human-readable ``reason``**
so target portfolios stay explainable and auditable — this is enforced by the
dataclass requiring the field.

The base + types are real and importable in v0.1; the concrete policies are
enabled in v0.2 (mirror / fifo) and v0.3 (score).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models.enums import NormalizedAction


@dataclass(frozen=True)
class ActiveName:
    """An active recommendation the policy may include in the target."""

    ticker: str
    action: NormalizedAction
    confidence: float
    first_seen_rank: int  # lower == held longer (FIFO ordering)


@dataclass(frozen=True)
class TargetHolding:
    ticker: str
    weight: float
    reason: str
    rank: int | None = None
    dollars: float | None = None


@dataclass
class PolicyInput:
    active_names: list[ActiveName]
    explicit_removals: set[str] = field(default_factory=set)
    max_positions: int = 5
    sizing_mode: str = "equal_weight"
    fixed_dollar_per_position: float = 2000.0


@dataclass
class PolicyOutput:
    policy: str
    holdings: list[TargetHolding]
    reasons: list[str] = field(default_factory=list)


class TargetPolicy(ABC):
    """Interface all target policies implement."""

    name: str = "base"
    enabled: bool = False

    @abstractmethod
    def compute(self, data: PolicyInput) -> PolicyOutput:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def _weights(tickers: list[str], data: PolicyInput) -> dict[str, tuple[float, float | None]]:
        """Return {ticker: (weight, dollars)} per the configured sizing mode."""

        n = len(tickers)
        if n == 0:
            return {}
        if data.sizing_mode == "fixed_dollar":
            per = data.fixed_dollar_per_position
            total = per * n
            return {t: ((per / total) if total else 0.0, per) for t in tickers}
        # equal_weight
        w = 1.0 / n
        return {t: (w, None) for t in tickers}
