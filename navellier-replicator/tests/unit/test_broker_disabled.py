from __future__ import annotations

import pytest

from navellier_replicator.broker import order_router, reconciliation
from navellier_replicator.broker.ibkr_client import IBKRClient
from navellier_replicator.errors import LiveTradingDisabledError, NotEnabledError


def test_broker_client_paper_only(app_cfg):
    client = IBKRClient(app_cfg)  # paper mode passes
    with pytest.raises(NotEnabledError):
        client.connect()
    with pytest.raises(NotEnabledError):
        client.submit_paper_order()


def test_broker_client_rejects_non_paper(app_cfg):
    app_cfg.broker.mode = "live"  # force-bypass validation to prove the guard
    with pytest.raises(LiveTradingDisabledError):
        IBKRClient(app_cfg)


def test_order_and_reconcile_disabled():
    with pytest.raises(NotEnabledError):
        order_router.plan_orders()
    with pytest.raises(NotEnabledError):
        order_router.submit_orders()
    with pytest.raises(NotEnabledError):
        reconciliation.reconcile()
