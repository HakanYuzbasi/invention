"""Policy: mirror_published_if_explicit.

Mirror the publisher's active set, honoring explicit removals first. The
algorithm is implemented in full; it is *disabled* in v0.1 (``enabled = False``)
and turned on in v0.2. ``compute`` fails closed until then.
"""

from __future__ import annotations

from ..errors import NotEnabledError
from .policy_base import PolicyInput, PolicyOutput, TargetHolding, TargetPolicy


class MirrorPublishedIfExplicit(TargetPolicy):
    name = "mirror_published_if_explicit"
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
        # Explicit removals win outright.
        kept = [
            n for n in data.active_names
            if n.ticker not in data.explicit_removals and n.action.implies_active_holding
        ]
        for t in data.explicit_removals:
            reasons.append(f"{t}: excluded — explicit publisher removal.")

        # Respect the cap by keeping the highest-confidence names.
        kept_sorted = sorted(kept, key=lambda n: (-n.confidence, n.first_seen_rank))
        selected = kept_sorted[: data.max_positions]
        if len(kept_sorted) > data.max_positions:
            dropped = ", ".join(n.ticker for n in kept_sorted[data.max_positions:])
            reasons.append(f"Capped at {data.max_positions}; dropped lowest-confidence: {dropped}.")

        weights = self._weights([n.ticker for n in selected], data)
        holdings = [
            TargetHolding(
                ticker=n.ticker,
                weight=weights[n.ticker][0],
                dollars=weights[n.ticker][1],
                rank=i + 1,
                reason=f"Mirrored active {n.action.value} (confidence {n.confidence:.2f}).",
            )
            for i, n in enumerate(selected)
        ]
        return PolicyOutput(policy=self.name, holdings=holdings, reasons=reasons)
