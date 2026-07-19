"""Shared exception types.

Fail-closed semantics: anything that could be ambiguous or unsafe raises rather
than proceeding on a guess.
"""

from __future__ import annotations


class NavellierError(Exception):
    """Base class for all application errors."""


class ConfigError(NavellierError):
    """Configuration missing or invalid."""


class NotEnabledError(NavellierError):
    """A feature exists in the tree but is not enabled in this release stage."""


class LiveTradingDisabledError(NavellierError):
    """Raised on any attempt to use a non-paper / live trading path.

    This is intentional and permanent: the system only ever supports paper mode.
    """


class CollectionError(NavellierError):
    """Browser collection failed (login, navigation, or capture)."""


class LoginFailedError(CollectionError):
    """Authentication did not reach a logged-in state."""


class SafetyBlock(NavellierError):
    """A safety guard blocked downstream work. Carries the failed check name."""

    def __init__(self, check: str, message: str) -> None:
        super().__init__(f"[{check}] {message}")
        self.check = check
        self.message = message


class LockHeldError(NavellierError):
    """Another run holds the process lock."""
