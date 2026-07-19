"""Order planning and routing (paper-only).

Computes the delta between a target portfolio and actual broker positions and
produces PLANNED order intents. Intents are always persisted BEFORE any (paper)
submission. Enabled in v0.3; fails closed in v0.1.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.3"


def plan_orders(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        f"Order planning is enabled in {STAGE}. v0.1 does not plan or route orders."
    )


def submit_orders(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        f"Order submission (paper-only) is enabled in {STAGE}, guarded behind "
        "all safety checks and an explicit toggle. v0.1 never submits."
    )
