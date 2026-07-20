"""Policy: score_cap5 (scaffolded, disabled by default).

Ranks active names by a composite score (confidence + recency) and keeps the top
``max_positions``. Scaffolded for v0.3 and disabled by default; ``compute`` fails
closed. The scoring is intentionally simple and transparent — no opaque model.
"""

from __future__ import annotations

from ..errors import NotEnabledError
from .policy_base import ActiveName, PolicyInput, PolicyOutput, TargetHolding, TargetPolicy


class ScoreCap5(TargetPolicy):
    name = "score_cap5"
    enabled = False  # remains disabled by default (v0.3+ opt-in)
    stage = "v0.3"

    @staticmethod
    def _score(n: ActiveName) -> float:
        # Higher confidence and more-recent (higher first_seen_rank) score higher.
        recency = 1.0 / (1.0 + max(n.first_seen_rank, 0))
        return 0.75 * n.confidence + 0.25 * recency

    def compute(self, data: PolicyInput) -> PolicyOutput:
        if not self.enabled:
            raise NotEnabledError(
                f"Policy '{self.name}' is scaffolded and disabled by default "
                f"(target {self.stage}). Enable explicitly to use it."
            )
        return self._compute(data)

    def _compute(self, data: PolicyInput) -> PolicyOutput:
        reasons: list[str] = []
        candidates = [
            n for n in data.active_names
            if n.ticker not in data.explicit_removals and n.action.implies_active_holding
        ]
        ranked = sorted(candidates, key=self._score, reverse=True)
        selected = ranked[: data.max_positions]
        weights = self._weights([n.ticker for n in selected], data)
        holdings = [
            TargetHolding(
                ticker=n.ticker,
                weight=weights[n.ticker][0],
                dollars=weights[n.ticker][1],
                rank=i + 1,
                reason=f"Score {self._score(n):.3f} (confidence {n.confidence:.2f}).",
            )
            for i, n in enumerate(selected)
        ]
        return PolicyOutput(policy=self.name, holdings=holdings, reasons=reasons)
