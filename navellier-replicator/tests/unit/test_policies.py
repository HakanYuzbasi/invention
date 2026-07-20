from __future__ import annotations

import pytest

from navellier_replicator.errors import NotEnabledError
from navellier_replicator.models.enums import NormalizedAction
from navellier_replicator.portfolio.policy_base import ActiveName, PolicyInput
from navellier_replicator.portfolio.policy_fifo_cap5 import FifoCap5
from navellier_replicator.portfolio.policy_mirror_explicit import MirrorPublishedIfExplicit
from navellier_replicator.portfolio.policy_score_cap5 import ScoreCap5


def _names() -> list[ActiveName]:
    return [
        ActiveName("AAA", NormalizedAction.NEW_BUY, 0.9, first_seen_rank=1),
        ActiveName("BBB", NormalizedAction.ACTIVE_HOLD, 0.8, first_seen_rank=2),
        ActiveName("CCC", NormalizedAction.ADD_MORE, 0.7, first_seen_rank=3),
        ActiveName("DDD", NormalizedAction.ACTIVE_HOLD, 0.6, first_seen_rank=4),
        ActiveName("EEE", NormalizedAction.ACTIVE_HOLD, 0.5, first_seen_rank=5),
        ActiveName("FFF", NormalizedAction.NEW_BUY, 0.95, first_seen_rank=6),
    ]


def test_policies_disabled_in_v01():
    data = PolicyInput(active_names=_names())
    for policy in (MirrorPublishedIfExplicit(), FifoCap5(), ScoreCap5()):
        with pytest.raises(NotEnabledError):
            policy.compute(data)


def test_score_policy_disabled_by_default():
    assert ScoreCap5().enabled is False


def test_fifo_evicts_oldest_when_over_cap():
    # Exercise the (disabled-by-default) algorithm directly to lock its behavior.
    policy = FifoCap5()
    out = policy._compute(PolicyInput(active_names=_names(), max_positions=5))
    tickers = [h.ticker for h in out.holdings]
    assert len(tickers) == 5
    assert "AAA" not in tickers  # oldest evicted
    assert any("FIFO-evicted" in r for r in out.reasons)


def test_mirror_honors_explicit_removal_first():
    policy = MirrorPublishedIfExplicit()
    data = PolicyInput(active_names=_names(), explicit_removals={"FFF"}, max_positions=5)
    out = policy._compute(data)
    tickers = [h.ticker for h in out.holdings]
    assert "FFF" not in tickers
    assert all(h.reason for h in out.holdings)  # every decision explained


def test_equal_weight_sums_to_one():
    out = FifoCap5()._compute(PolicyInput(active_names=_names()[:4], max_positions=5))
    assert abs(sum(h.weight for h in out.holdings) - 1.0) < 1e-9
