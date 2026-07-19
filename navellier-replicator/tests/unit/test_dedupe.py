from __future__ import annotations

from datetime import date

from navellier_replicator.models.dto import ParsedItem
from navellier_replicator.models.enums import ConfidenceBand, ExtractionMethod, NormalizedAction
from navellier_replicator.parsers import PARSER_VERSION
from navellier_replicator.signals.canonicalizer import dedupe_key
from navellier_replicator.signals.dedupe import dedupe_items, dedupe_keys


def _item(ticker: str, action: NormalizedAction, conf: float) -> ParsedItem:
    return ParsedItem(
        ticker=ticker,
        action=action,
        confidence=conf,
        confidence_band=ConfidenceBand.MEDIUM,
        extraction_method=ExtractionMethod.KEYWORD,
        source_snippet="snippet",
        parser_version=PARSER_VERSION,
    )


def test_dedupe_keeps_highest_confidence():
    items = [
        _item("NVDA", NormalizedAction.NEW_BUY, 0.6),
        _item("NVDA", NormalizedAction.NEW_BUY, 0.9),
        _item("MSFT", NormalizedAction.ACTIVE_HOLD, 0.7),
    ]
    out = dedupe_items(items)
    assert len(out) == 2
    nvda = next(i for i in out if i.ticker == "NVDA")
    assert nvda.confidence == 0.9


def test_dedupe_distinguishes_action():
    items = [
        _item("NVDA", NormalizedAction.NEW_BUY, 0.6),
        _item("NVDA", NormalizedAction.SELL, 0.6),
    ]
    assert len(dedupe_items(items)) == 2


def test_dedupe_keys_preserve_order():
    assert dedupe_keys(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_dedupe_key_is_stable_and_collapses_same_day():
    it = _item("NVDA", NormalizedAction.NEW_BUY, 0.9)
    k1 = dedupe_key(it, source_url="u", content_sha256="h", observed_on=date(2026, 7, 19))
    k2 = dedupe_key(it, source_url="u", content_sha256="h", observed_on=date(2026, 7, 19))
    k3 = dedupe_key(it, source_url="u", content_sha256="h", observed_on=date(2026, 7, 20))
    assert k1 == k2
    assert k1 != k3
