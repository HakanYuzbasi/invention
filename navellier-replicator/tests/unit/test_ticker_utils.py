from __future__ import annotations

from navellier_replicator.parsers.ticker_utils import (
    extract_tickers,
    first_ticker,
    is_plausible_ticker,
    normalize_ticker,
)


def test_normalize_strips_cashtag_and_uppercases():
    assert normalize_ticker(" $aapl ") == "AAPL"
    assert normalize_ticker("brk.b") == "BRK.B"


def test_cashtag_extraction():
    assert extract_tickers("We like $NVDA and $AVGO here") == ["NVDA", "AVGO"]


def test_exchange_qualifier_extraction():
    assert first_ticker("Shares of NASDAQ: MSFT rose") == "MSFT"


def test_blacklist_excludes_common_words():
    # BUY / SELL / THE / AND must never be treated as tickers.
    got = extract_tickers("BUY THE AND SELL")
    assert got == []
    assert not is_plausible_ticker("BUY")
    assert not is_plausible_ticker("THE")


def test_bare_tokens_only_when_allowed():
    text = "PLTR is a new buy"
    assert "PLTR" in extract_tickers(text, allow_bare=True)
    assert extract_tickers(text, allow_bare=False) == []


def test_dedupe_preserves_first_seen_order():
    assert extract_tickers("$AAPL $MSFT $AAPL") == ["AAPL", "MSFT"]


def test_length_bounds():
    assert not is_plausible_ticker("TOOLONG")
    assert is_plausible_ticker("F")
