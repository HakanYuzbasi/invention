from __future__ import annotations

import pytest

from navellier_replicator.models.enums import NormalizedAction
from navellier_replicator.parsers.update_parser import classify_action


@pytest.mark.parametrize(
    "text,expected",
    [
        ("New Buy", NormalizedAction.NEW_BUY),
        ("We are initiating a position", NormalizedAction.NEW_BUY),
        ("Add More", NormalizedAction.ADD_MORE),
        ("buy more shares", NormalizedAction.ADD_MORE),
        ("Hold", NormalizedAction.ACTIVE_HOLD),
        ("Buy Below $50", NormalizedAction.ACTIVE_HOLD),
        ("Trim the position", NormalizedAction.TRIM),
        ("take partial profits", NormalizedAction.TRIM),
        ("Sell", NormalizedAction.SELL),
        ("remove from portfolio", NormalizedAction.REMOVE),
        ("We are closing this position", NormalizedAction.CLOSED),
        ("Add to watch list", NormalizedAction.WATCHLIST),
        ("the economy is fine", NormalizedAction.UNKNOWN),
    ],
)
def test_classify_action(text, expected):
    assert classify_action(text).action is expected


def test_explicit_flag_set_for_unambiguous_phrase():
    assert classify_action("Sell").explicit is True


def test_conflict_detection():
    cls = classify_action("We buy some and sell others")
    assert cls.conflict is True


def test_empty_is_unknown():
    assert classify_action("").action is NormalizedAction.UNKNOWN
