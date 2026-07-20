"""Reconciliation of broker positions/fills back into the database.

Enabled in v0.3; fails closed in v0.1.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.3"


def reconcile(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        f"Reconciliation is enabled in {STAGE}. v0.1 has no broker state to reconcile."
    )
