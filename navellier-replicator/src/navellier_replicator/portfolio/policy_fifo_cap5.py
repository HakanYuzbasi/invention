"""Policy: fifo_cap5.

Keep at most ``max_positions`` (default 5) active names. Explicit removals win.
If a new active name would exceed the cap and there is NO explicit removal, sell
the oldest held name (FIFO). Fully implemented; disabled until v0.2.
"""

from __future__ import annotations

from ..errors import NotEnabledError
from .policy_base import PolicyInput, PolicyOutput, TargetHolding, TargetPolicy


class FifoCap5(TargetPolicy):
    name = "fifo_cap5"
    enabled = False  # flipped on in v0.2
    stage = "v0.2"

    def compute(self, data: PolicyInput) -> PolicyOutput:
        if not self.enabled:
            raise NotEnabledError(
                f"Policy '{self.name}' is enabled in {self.stage}. "
                "v0.1 collects and parses only; it does not compute targets."
            )
        return self._compute(data)

    def _compute(self, data: PolicyInput) -> PolicyOutput:
        reasons: list[str] = []
        candidates = [
            n for n in data.active_names
            if n.ticker not in data.explicit_removals and n.action.implies_active_holding
        ]
        for t in data.explicit_removals:
            reasons.append(f"{t}: excluded — explicit publisher removal.")

        # FIFO: oldest (lowest first_seen_rank) held first; excess is evicted.
        by_age = sorted(candidates, key=lambda n: n.first_seen_rank)
        if len(by_age) > data.max_positions:
            evicted = by_age[: len(by_age) - data.max_positions]
            for n in evicted:
                reasons.append(
                    f"{n.ticker}: FIFO-evicted (oldest held) to keep <= {data.max_positions}."
                )
            selected = by_age[len(by_age) - data.max_positions:]
        else:
            selected = by_age

        weights = self._weights([n.ticker for n in selected], data)
        holdings = [
            TargetHolding(
                ticker=n.ticker,
                weight=weights[n.ticker][0],
                dollars=weights[n.ticker][1],
                rank=i + 1,
                reason=f"Held (FIFO rank {n.first_seen_rank}, action {n.action.value}).",
            )
            for i, n in enumerate(selected)
        ]
        return PolicyOutput(policy=self.name, holdings=holdings, reasons=reasons)
