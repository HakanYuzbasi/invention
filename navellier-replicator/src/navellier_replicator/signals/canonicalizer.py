"""Canonicalization helpers.

Pure functions that turn a parsed item + its source metadata into the canonical
fields used by the event log. Implemented now (and unit-tested) because they are
side-effect-free and shared by both v0.1 diffing and v0.2 event building.
"""

from __future__ import annotations

import hashlib
from datetime import date

from ..models.dto import ParsedItem


def canonical_ticker(ticker: str) -> str:
    return ticker.strip().upper().lstrip("$")


def source_hash(source_url: str, content_sha256: str) -> str:
    """Stable hash identifying the exact source surface + content a signal came from."""

    h = hashlib.sha256()
    h.update(source_url.encode("utf-8"))
    h.update(b"|")
    h.update(content_sha256.encode("utf-8"))
    return h.hexdigest()


def dedupe_key(
    item: ParsedItem,
    *,
    source_url: str,
    content_sha256: str,
    observed_on: date,
) -> str:
    """Deterministic key that collapses re-observations of the same signal.

    Same ticker + action from the same source content on the same day is one
    logical event, regardless of how many times we scrape it.
    """

    parts = [
        observed_on.isoformat(),
        canonical_ticker(item.ticker),
        item.action.value,
        source_hash(source_url, content_sha256)[:16],
    ]
    return ":".join(parts)
