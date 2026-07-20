"""Ticker extraction and normalization.

Conservative by design: it is better to miss a ticker (and flag UNKNOWN
upstream) than to hallucinate one from a common English word.
"""

from __future__ import annotations

import re

# $-prefixed cashtags are the highest-confidence signal.
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})(?:\.[A-Z])?\b")
# Bare uppercase tokens of 1-5 letters, optionally with a single-letter class
# suffix (e.g. BRK.B). Requires standalone token boundaries.
_BARE_RE = re.compile(r"\b([A-Z]{1,5})(?:\.([A-Z]))?\b")

# Common uppercase words / abbreviations that are NOT tickers. Kept explicit so
# the exclusion set is auditable.
_BLACKLIST: frozenset[str] = frozenset(
    {
        "A", "I", "AN", "AND", "ARE", "AS", "AT", "BE", "BUY", "BY", "CEO", "CFO",
        "EPS", "ETF", "FOR", "GDP", "HOLD", "IN", "INC", "IPO", "IS", "IT", "LLC",
        "LTD", "NEW", "NO", "NYSE", "OF", "ON", "OR", "P", "PE", "Q", "Q1", "Q2",
        "Q3", "Q4", "SELL", "SO", "THE", "TO", "TRIM", "UP", "US", "USA", "USD",
        "VS", "YOY", "ADD", "AI", "OK", "IRA", "TV", "URL", "FAQ", "PDF", "HTML",
        "CSS", "API", "SEC", "FDA", "GMT", "EST", "EDT", "AM", "PM",
    }
)

# Exchange qualifiers frequently prefixing a ticker: "NYSE: AAPL", "NASDAQ:MSFT".
_EXCHANGE_QUALIFIER_RE = re.compile(
    r"\b(?:NYSE|NASDAQ|NYSEARCA|AMEX|OTC)\s*:\s*([A-Z]{1,5})\b"
)


def normalize_ticker(raw: str) -> str:
    """Normalize a candidate ticker to canonical uppercase form."""

    t = raw.strip().upper().lstrip("$")
    # Collapse whitespace, keep letters and a single dot class suffix.
    t = re.sub(r"\s+", "", t)
    return t


def is_plausible_ticker(token: str) -> bool:
    """Whether a normalized token looks like a real ticker."""

    base = token.split(".")[0]
    if not base or not base.isalpha():
        return False
    if not 1 <= len(base) <= 5:
        return False
    if base in _BLACKLIST:
        return False
    return True


def extract_tickers(text: str, *, allow_bare: bool = True) -> list[str]:
    """Extract plausible tickers from free text, de-duplicated, in first-seen order.

    Cashtags and exchange-qualified symbols are always considered. Bare
    uppercase tokens are only considered when ``allow_bare`` is True (used for
    structured cells where surrounding structure raises confidence).
    """

    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        norm = normalize_ticker(candidate)
        if is_plausible_ticker(norm) and norm not in seen:
            seen.add(norm)
            found.append(norm)

    for m in _EXCHANGE_QUALIFIER_RE.finditer(text):
        _add(m.group(1))
    for m in _CASHTAG_RE.finditer(text):
        _add(m.group(1))

    if allow_bare:
        for m in _BARE_RE.finditer(text):
            token = m.group(1)
            if m.group(2):
                token = f"{token}.{m.group(2)}"
            _add(token)

    return found


def first_ticker(text: str, *, allow_bare: bool = True) -> str | None:
    tickers = extract_tickers(text, allow_bare=allow_bare)
    return tickers[0] if tickers else None
