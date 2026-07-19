from __future__ import annotations

from navellier_replicator.models.dto import PageCapture, ParsedItem
from navellier_replicator.models.enums import (
    ConfidenceBand,
    ExtractionMethod,
    NormalizedAction,
    PageCategory,
    Severity,
)
from navellier_replicator.parsers import PARSER_VERSION
from navellier_replicator.safety import guards


def _capture(text: str, *, category=PageCategory.PRIMARY_PORTFOLIO, error=None) -> PageCapture:
    return PageCapture(
        category=category,
        requested_url="https://example/portfolio",
        final_url="https://example/portfolio",
        http_ok=error is None,
        html="<html></html>",
        visible_text=text,
        content_sha256="abc123",
        error=error,
    )


def _item(ticker, action, conf) -> ParsedItem:
    return ParsedItem(
        ticker=ticker, action=action, confidence=conf,
        confidence_band=ConfidenceBand.MEDIUM,
        extraction_method=ExtractionMethod.STRUCTURED_TABLE,
        source_snippet="s", parser_version=PARSER_VERSION,
    )


def test_login_content_blocks_on_thin_page():
    res = guards.check_login_content([_capture("short")], min_content_chars=400)
    assert not res.passed
    assert res.blocking_flags


def test_login_content_passes_on_rich_page():
    res = guards.check_login_content([_capture("x" * 500)], min_content_chars=400)
    assert res.passed


def test_login_content_blocks_on_error_capture():
    res = guards.check_login_content([_capture("", error="boom")], min_content_chars=400)
    assert not res.passed


def test_zero_actionable_blocks():
    res = guards.check_actionable_items([], min_expected=1)
    assert not res.passed


def test_actionable_present_passes():
    items = [_item("NVDA", NormalizedAction.NEW_BUY, 0.9)]
    assert guards.check_actionable_items(items, min_expected=1).passed


def test_all_low_confidence_blocks():
    items = [_item("NVDA", NormalizedAction.NEW_BUY, 0.2)]
    res = guards.check_confidence(items, threshold=0.6)
    assert not res.passed


def test_some_low_confidence_warns_not_blocks():
    items = [
        _item("NVDA", NormalizedAction.NEW_BUY, 0.9),
        _item("MSFT", NormalizedAction.ACTIVE_HOLD, 0.2),
    ]
    res = guards.check_confidence(items, threshold=0.6)
    assert res.passed
    assert any(f.severity == Severity.WARNING for f in res.flags)


def test_large_set_change_blocks():
    res = guards.check_set_change({"AAA", "BBB"}, {"XXX", "YYY"}, max_change_fraction=0.5)
    assert not res.passed


def test_small_set_change_passes():
    res = guards.check_set_change({"AAA", "BBB", "CCC"}, {"AAA", "BBB", "DDD"}, max_change_fraction=0.7)
    assert res.passed


def test_set_change_no_previous_passes():
    assert guards.check_set_change({"AAA"}, set(), max_change_fraction=0.5).passed
