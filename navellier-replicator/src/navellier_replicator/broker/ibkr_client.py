"""IBKR client wrapper (paper-only).

Enabled in v0.3. In v0.1 every method fails closed and no socket is opened. The
class also enforces, at construction, that it can only ever run against a paper
configuration — a live/non-paper config raises immediately.
"""

from __future__ import annotations

from ..errors import LiveTradingDisabledError, NotEnabledError
from ..settings import AppConfig

STAGE = "v0.3"


class IBKRClient:
    """Thin wrapper around an IB Gateway / TWS paper session (v0.3)."""

    def __init__(self, cfg: AppConfig) -> None:
        # Hard invariant: refuse to exist outside paper mode.
        if cfg.broker.mode != "paper":
            raise LiveTradingDisabledError(
                "IBKRClient may only be constructed in paper mode. Live trading "
                "is not supported by this system."
            )
        self.cfg = cfg
        self._connected = False

    def connect(self) -> None:
        raise NotEnabledError(
            f"IBKR connectivity is enabled in {STAGE}. v0.1 does not connect to a broker."
        )

    def account_summary(self) -> dict:
        raise NotEnabledError(f"account_summary is enabled in {STAGE}.")

    def positions(self) -> list:
        raise NotEnabledError(f"positions is enabled in {STAGE}.")

    def submit_paper_order(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        raise NotEnabledError(
            f"Paper order submission is enabled in {STAGE}, and only after all "
            "safety checks pass. v0.1 never submits orders."
        )

    def disconnect(self) -> None:
        self._connected = False
