"""Enumerations used across the pipeline.

String-valued enums so they serialize cleanly into SQLite and JSON and stay
human-readable in the raw evidence.
"""

from __future__ import annotations

from enum import Enum


class NormalizedAction(str, Enum):
    """The canonical recommendation-action taxonomy.

    Every extracted item is classified into exactly one of these. ``UNKNOWN`` is
    a first-class outcome, used whenever the parser is not confident.
    """

    NEW_BUY = "NEW_BUY"
    ACTIVE_HOLD = "ACTIVE_HOLD"
    REMOVE = "REMOVE"
    SELL = "SELL"
    TRIM = "TRIM"
    ADD_MORE = "ADD_MORE"
    CLOSED = "CLOSED"
    WATCHLIST = "WATCHLIST"
    UNKNOWN = "UNKNOWN"

    @property
    def is_actionable(self) -> bool:
        """Whether this action can drive a portfolio/trade decision."""

        return self in _ACTIONABLE

    @property
    def implies_active_holding(self) -> bool:
        """Whether the action implies the name should be an active holding."""

        return self in _ACTIVE_HOLDING

    @property
    def implies_exit(self) -> bool:
        """Whether the action implies the name should be removed/closed."""

        return self in _EXIT


_ACTIONABLE = frozenset(
    {
        NormalizedAction.NEW_BUY,
        NormalizedAction.ACTIVE_HOLD,
        NormalizedAction.REMOVE,
        NormalizedAction.SELL,
        NormalizedAction.TRIM,
        NormalizedAction.ADD_MORE,
        NormalizedAction.CLOSED,
    }
)
_ACTIVE_HOLDING = frozenset(
    {
        NormalizedAction.NEW_BUY,
        NormalizedAction.ACTIVE_HOLD,
        NormalizedAction.ADD_MORE,
        NormalizedAction.TRIM,  # still held, just smaller
    }
)
_EXIT = frozenset(
    {
        NormalizedAction.REMOVE,
        NormalizedAction.SELL,
        NormalizedAction.CLOSED,
    }
)


class RunStatus(str, Enum):
    STARTED = "STARTED"
    COLLECTED = "COLLECTED"
    PARSED = "PARSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class PageCategory(str, Enum):
    PRIMARY_PORTFOLIO = "PRIMARY_PORTFOLIO"
    UPDATE = "UPDATE"
    SUBPAGE = "SUBPAGE"
    LOGIN = "LOGIN"
    UNKNOWN = "UNKNOWN"


class ExtractionMethod(str, Enum):
    """How an item was extracted (for auditability)."""

    STRUCTURED_TABLE = "STRUCTURED_TABLE"
    TEXT_FALLBACK = "TEXT_FALLBACK"
    KEYWORD = "KEYWORD"


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @staticmethod
    def from_score(score: float, threshold: float) -> "ConfidenceBand":
        if score >= max(threshold, 0.8):
            return ConfidenceBand.HIGH
        if score >= threshold:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW


class AuditFlagType(str, Enum):
    LOGIN_OK_NO_CONTENT = "LOGIN_OK_NO_CONTENT"
    ZERO_ACTIONABLE_ITEMS = "ZERO_ACTIONABLE_ITEMS"
    LOW_CONFIDENCE_ACTION = "LOW_CONFIDENCE_ACTION"
    LARGE_SET_CHANGE = "LARGE_SET_CHANGE"
    UNRESOLVED_RECONCILIATION = "UNRESOLVED_RECONCILIATION"
    DUPLICATE_OPEN_ORDER = "DUPLICATE_OPEN_ORDER"
    INVALID_MARKET_WINDOW = "INVALID_MARKET_WINDOW"
    SOURCE_SHAPE_CHANGED = "SOURCE_SHAPE_CHANGED"
    COLLECTION_FAILURE = "COLLECTION_FAILURE"
    PARSER_ANOMALY = "PARSER_ANOMALY"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCK = "BLOCK"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PLANNED = "PLANNED"       # dry-run intent, never sent
    SUBMITTED = "SUBMITTED"   # paper submission only (v0.3)
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
