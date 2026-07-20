"""Safety guards. Each returns a SafetyResult and raises audit flags.

The system fails CLOSED: guards produce BLOCK-severity flags that stop
downstream planning/submission. Guards are pure functions over their inputs so
they are trivially unit-testable; persistence of the flags happens in the jobs.
"""

from __future__ import annotations

from ..models.dto import AuditFlag, PageCapture, ParsedItem, SafetyResult
from ..models.enums import AuditFlagType, NormalizedAction, Severity


def _flag(flag_type: AuditFlagType, severity: Severity, message: str,
          **context: str) -> AuditFlag:
    return AuditFlag(flag_type=flag_type, severity=severity, message=message, context=context)


def check_login_content(captures: list[PageCapture], *, min_content_chars: int) -> SafetyResult:
    """Block when collection 'succeeded' but the portfolio page is effectively empty."""

    flags: list[AuditFlag] = []
    portfolio_caps = [c for c in captures if c.category.value == "PRIMARY_PORTFOLIO"]
    for cap in portfolio_caps:
        if cap.error:
            flags.append(_flag(
                AuditFlagType.COLLECTION_FAILURE, Severity.BLOCK,
                f"Portfolio capture errored: {cap.error}",
                url=cap.requested_url,
            ))
        elif cap.content_len < min_content_chars:
            flags.append(_flag(
                AuditFlagType.LOGIN_OK_NO_CONTENT, Severity.BLOCK,
                f"Portfolio page has only {cap.content_len} chars of visible text "
                f"(< {min_content_chars}); likely a login wall or empty render.",
                url=cap.final_url, content_len=str(cap.content_len),
            ))
    passed = not any(f.severity == Severity.BLOCK for f in flags)
    return SafetyResult(passed=passed, flags=flags)


def check_actionable_items(items: list[ParsedItem], *, min_expected: int) -> SafetyResult:
    """Block when the parser unexpectedly returns zero actionable items."""

    actionable = [it for it in items if it.is_actionable and it.action is not NormalizedAction.UNKNOWN]
    flags: list[AuditFlag] = []
    if len(actionable) < min_expected:
        flags.append(_flag(
            AuditFlagType.ZERO_ACTIONABLE_ITEMS, Severity.BLOCK,
            f"Parser produced {len(actionable)} actionable items "
            f"(expected >= {min_expected}). Refusing to proceed.",
            actionable=str(len(actionable)), total=str(len(items)),
        ))
    return SafetyResult(passed=not flags, flags=flags)


def check_confidence(items: list[ParsedItem], *, threshold: float) -> SafetyResult:
    """Warn (do not hard-block) on low-confidence items, but block if EVERY
    actionable item is below threshold (nothing trustworthy to act on)."""

    flags: list[AuditFlag] = []
    actionable = [it for it in items if it.is_actionable]
    low = [it for it in actionable if it.confidence < threshold]
    for it in low:
        flags.append(_flag(
            AuditFlagType.LOW_CONFIDENCE_ACTION, Severity.WARNING,
            f"{it.ticker} {it.action.value} confidence {it.confidence:.2f} < {threshold:.2f}",
            ticker=it.ticker, action=it.action.value, confidence=f"{it.confidence:.3f}",
        ))
    if actionable and len(low) == len(actionable):
        flags.append(_flag(
            AuditFlagType.LOW_CONFIDENCE_ACTION, Severity.BLOCK,
            "All actionable items are below the confidence threshold.",
            threshold=f"{threshold:.2f}",
        ))
    passed = not any(f.severity == Severity.BLOCK for f in flags)
    return SafetyResult(passed=passed, flags=flags)


def check_set_change(
    current_tickers: set[str],
    previous_tickers: set[str],
    *,
    max_change_fraction: float,
) -> SafetyResult:
    """Block on a large recommendation-set change vs the previous run.

    A sudden wholesale change without corroboration is a classic scraper-broke /
    wrong-page symptom, so it fails closed.
    """

    flags: list[AuditFlag] = []
    if not previous_tickers:
        return SafetyResult(passed=True, flags=flags)  # nothing to compare against
    symdiff = current_tickers.symmetric_difference(previous_tickers)
    denom = max(len(previous_tickers), 1)
    change_fraction = len(symdiff) / denom
    if change_fraction > max_change_fraction:
        flags.append(_flag(
            AuditFlagType.LARGE_SET_CHANGE, Severity.BLOCK,
            f"Recommendation set changed by {change_fraction:.0%} vs previous run "
            f"(> {max_change_fraction:.0%}). Requires corroboration before acting.",
            added=",".join(sorted(current_tickers - previous_tickers)) or "-",
            removed=",".join(sorted(previous_tickers - current_tickers)) or "-",
        ))
    return SafetyResult(passed=not flags, flags=flags)


def check_source_shape(captures: list[PageCapture], previous_hashes: set[str]) -> SafetyResult:
    """Informational flag when a page's structure hash is entirely new.

    Not a hard block on its own (content legitimately changes), but surfaced so a
    human can confirm the page shape when combined with other anomalies.
    """

    flags: list[AuditFlag] = []
    if not previous_hashes:
        return SafetyResult(passed=True, flags=flags)
    for cap in captures:
        if cap.category.value == "PRIMARY_PORTFOLIO" and cap.content_sha256 not in previous_hashes:
            flags.append(_flag(
                AuditFlagType.SOURCE_SHAPE_CHANGED, Severity.INFO,
                "Primary portfolio content hash differs from all recent runs.",
                sha=cap.content_sha256[:16],
            ))
    return SafetyResult(passed=True, flags=flags)
