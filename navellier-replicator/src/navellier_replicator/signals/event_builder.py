"""Recommendation event builder.

Turns deduped, canonicalized parsed items into immutable ``recommendation_events``
rows. Wired in v0.2 — in v0.1 it fails closed rather than writing a partial or
unvalidated event stream.
"""

from __future__ import annotations

from ..errors import NotEnabledError

STAGE = "v0.2"


def build_events(*args, **kwargs):  # noqa: ANN002, ANN003, ANN201
    raise NotEnabledError(
        "event_builder.build_events is enabled in v0.2. v0.1 persists extracted "
        "items and computes diffs directly; it does not build the event log yet."
    )
