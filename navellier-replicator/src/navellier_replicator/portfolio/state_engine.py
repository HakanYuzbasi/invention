"""Materialized active-state engine.

Derives the current active recommendation set from the append-only event log.
Wired in v0.2; fails closed in v0.1.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.2"


def materialize_active_state(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        "state_engine.materialize_active_state is enabled in v0.2. v0.1 computes "
        "run-to-run diffs directly from extracted items."
    )
