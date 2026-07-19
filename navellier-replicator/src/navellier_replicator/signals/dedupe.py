"""Deduplication helpers.

Pure functions, unit-tested in v0.1 and reused by the v0.2 event builder.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models.dto import ParsedItem


def dedupe_items(items: Iterable[ParsedItem]) -> list[ParsedItem]:
    """Collapse duplicate (ticker, action) items, keeping the highest confidence.

    Order of first appearance is preserved for the surviving items.
    """

    best: dict[tuple[str, str], ParsedItem] = {}
    order: list[tuple[str, str]] = []
    for it in items:
        key = (it.ticker.upper(), it.action.value)
        if key not in best:
            best[key] = it
            order.append(key)
        elif it.confidence > best[key].confidence:
            best[key] = it
    return [best[k] for k in order]


def dedupe_keys(keys: Iterable[str]) -> list[str]:
    """De-duplicate a sequence of dedupe keys, preserving first-seen order."""

    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out
