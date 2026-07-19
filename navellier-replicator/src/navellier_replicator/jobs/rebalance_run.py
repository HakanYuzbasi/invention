"""Rebalance job (v0.3): compute targets, plan paper orders, guarded submit.

Fails closed in v0.1/v0.2. Planning is enabled in v0.3 and is dry-run by default;
paper submission requires all safety checks to pass and an explicit toggle.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.3"


def run_rebalance(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        f"Rebalance/order planning is enabled in {STAGE}. v0.1 does not plan orders."
    )
