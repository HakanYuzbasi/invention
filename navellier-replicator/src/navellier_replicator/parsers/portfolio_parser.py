"""Portfolio page parser.

Hybrid strategy:

1. **Structured** — locate holdings table(s), map columns using configurable
   header hints, and read one item per row.
2. **Text fallback** — if no usable table is found, degrade to sentence-level
   keyword parsing so a layout change doesn't produce a silent zero result.

Every item keeps the exact source snippet (row text or sentence) it came from,
and anything ambiguous is emitted as ``UNKNOWN`` rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..models.dto import ParsedItem
from ..models.enums import ConfidenceBand, ExtractionMethod, NormalizedAction
from . import PARSER_VERSION
from .confidence import ConfidenceInputs, band, score
from .ticker_utils import extract_tickers, first_ticker, is_plausible_ticker, normalize_ticker
from .update_parser import classify_action

_DEFAULT_HEADER_HINTS: dict[str, list[str]] = {
    "ticker": ["ticker", "symbol"],
    "name": ["company", "name", "stock"],
    # NB: deliberately NOT "buy below" — that is a price column, not an action.
    "action": ["action", "status", "advice", "rating", "recommendation"],
}


@dataclass
class _ColumnMap:
    ticker: int | None = None
    name: int | None = None
    action: int | None = None

    @property
    def any_identified(self) -> bool:
        return any(v is not None for v in (self.ticker, self.name, self.action))


def _cell_text(cell: Tag) -> str:
    return cell.get_text(separator=" ", strip=True)


def _map_columns(header_cells: list[str], hints: dict[str, list[str]]) -> _ColumnMap:
    cmap = _ColumnMap()
    lowered = [h.lower() for h in header_cells]
    for idx, htext in enumerate(lowered):
        for field, needles in hints.items():
            if any(n in htext for n in needles):
                if getattr(cmap, field) is None:
                    setattr(cmap, field, idx)
    return cmap


def _iter_rows(table: Tag) -> list[list[Tag]]:
    rows: list[list[Tag]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if cells:
            rows.append(cells)
    return rows


def _parse_table(
    table: Tag, hints: dict[str, list[str]], confidence_threshold: float
) -> list[ParsedItem]:
    rows = _iter_rows(table)
    if len(rows) < 2:
        return []

    header = [_cell_text(c) for c in rows[0]]
    cmap = _map_columns(header, hints)
    items: list[ParsedItem] = []

    for cells in rows[1:]:
        texts = [_cell_text(c) for c in cells]
        row_text = " | ".join(texts)
        if not row_text.strip():
            continue

        # --- ticker ---
        ticker: str | None = None
        ticker_in_column = False
        if cmap.ticker is not None and cmap.ticker < len(texts):
            cand = normalize_ticker(texts[cmap.ticker])
            if is_plausible_ticker(cand):
                ticker = cand
                ticker_in_column = True
        if ticker is None:
            ticker = first_ticker(row_text, allow_bare=True)
        if ticker is None:
            # No plausible ticker: keep as audit-only UNKNOWN so a human can see
            # what row we couldn't resolve, but only if the row looks like data
            # (has several columns) rather than a spacer.
            if len(texts) >= 2:
                items.append(
                    _make_item(
                        ticker="UNKNOWN",
                        company=None,
                        action=NormalizedAction.UNKNOWN,
                        explicit=False,
                        conflict=False,
                        cashtag=False,
                        ticker_in_column=False,
                        method=ExtractionMethod.STRUCTURED_TABLE,
                        snippet=row_text,
                        threshold=confidence_threshold,
                    )
                )
            continue

        # --- company name ---
        company = None
        if cmap.name is not None and cmap.name < len(texts):
            company = texts[cmap.name] or None

        # --- action ---
        action_source = ""
        if cmap.action is not None and cmap.action < len(texts):
            action_source = texts[cmap.action]
        cls = classify_action(action_source or row_text)
        action = cls.action
        explicit = cls.explicit
        # A name present in an active holdings table with no explicit exit signal
        # is treated as ACTIVE_HOLD (still held), at reduced confidence.
        if action is NormalizedAction.UNKNOWN:
            action = NormalizedAction.ACTIVE_HOLD
            explicit = False

        items.append(
            _make_item(
                ticker=ticker,
                company=company,
                action=action,
                explicit=explicit,
                conflict=cls.conflict,
                cashtag="$" in (texts[cmap.ticker] if ticker_in_column and cmap.ticker is not None else row_text),
                ticker_in_column=ticker_in_column,
                method=ExtractionMethod.STRUCTURED_TABLE,
                snippet=row_text,
                threshold=confidence_threshold,
                company_present=bool(company),
            )
        )

    return items


def _make_item(
    *,
    ticker: str,
    company: str | None,
    action: NormalizedAction,
    explicit: bool,
    conflict: bool,
    cashtag: bool,
    ticker_in_column: bool,
    method: ExtractionMethod,
    snippet: str,
    threshold: float,
    company_present: bool = False,
) -> ParsedItem:
    ci = ConfidenceInputs(
        method=method,
        action=action,
        cashtag_ticker=cashtag,
        explicit_action_phrase=explicit,
        has_company_name=company_present,
        ticker_in_dedicated_column=ticker_in_column,
        multiple_action_signals_conflict=conflict,
    )
    conf = score(ci)
    return ParsedItem(
        ticker=ticker,
        company_name=company,
        action=action,
        confidence=conf,
        confidence_band=band(conf, threshold),
        extraction_method=method,
        source_snippet=snippet[:500],
        parser_version=PARSER_VERSION,
        notes={"components": str(ci.components)},
    )


def _text_fallback(soup: BeautifulSoup, confidence_threshold: float) -> list[ParsedItem]:
    text = soup.get_text(separator="\n")
    items: list[ParsedItem] = []
    seen: set[tuple[str, str]] = set()
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        tickers = extract_tickers(line, allow_bare=False)  # cashtags only — conservative
        if not tickers:
            continue
        cls = classify_action(line)
        action = cls.action if cls.action is not NormalizedAction.UNKNOWN else NormalizedAction.ACTIVE_HOLD
        for ticker in tickers:
            key = (ticker, action.value)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                _make_item(
                    ticker=ticker,
                    company=None,
                    action=action,
                    explicit=cls.explicit,
                    conflict=cls.conflict,
                    cashtag=True,
                    ticker_in_column=False,
                    method=ExtractionMethod.TEXT_FALLBACK,
                    snippet=line,
                    threshold=confidence_threshold,
                )
            )
    return items


def parse_portfolio_html(
    html: str,
    *,
    confidence_threshold: float,
    selectors: dict[str, Any] | None = None,
) -> list[ParsedItem]:
    """Parse a portfolio page into ParsedItems (structured first, text fallback)."""

    soup = BeautifulSoup(html or "", "lxml")
    selectors = selectors or {}
    hints_cfg = selectors.get("header_hints") or {}
    hints = {**_DEFAULT_HEADER_HINTS, **{k: list(v) for k, v in hints_cfg.items()}}

    table_selectors: list[str] = selectors.get("table_candidates") or []
    candidate_tables: list[Tag] = []
    for sel in table_selectors:
        candidate_tables.extend(t for t in soup.select(sel) if isinstance(t, Tag))
    if not candidate_tables:
        candidate_tables = [t for t in soup.find_all("table") if isinstance(t, Tag)]

    structured: list[ParsedItem] = []
    seen_tables: set[int] = set()
    for table in candidate_tables:
        if id(table) in seen_tables:
            continue
        seen_tables.add(id(table))
        structured.extend(_parse_table(table, hints, confidence_threshold))

    # If structured extraction produced at least one resolved (non-UNKNOWN)
    # ticker, trust it. Otherwise fall back to conservative text scanning.
    resolved = [it for it in structured if it.ticker != "UNKNOWN"]
    if resolved:
        return structured

    fallback = _text_fallback(soup, confidence_threshold)
    return fallback or structured
