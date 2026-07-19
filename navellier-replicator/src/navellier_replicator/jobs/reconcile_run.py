"""Reconcile job (v0.3): pull broker positions/fills, reconcile into the DB.

Fails closed in v0.1/v0.2.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.3"


def run_reconcile(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        f"Reconciliation is enabled in {STAGE}. v0.1 has no broker state to reconcile."
    )
