from __future__ import annotations

import json
from pathlib import Path

from navellier_replicator.models.enums import ExtractionMethod, NormalizedAction
from navellier_replicator.parsers import PARSER_VERSION
from navellier_replicator.parsers.portfolio_parser import parse_portfolio_html
from navellier_replicator.parsers.update_parser import parse_update_html

FIXTURES = Path(__file__).parents[1] / "fixtures"
SNAPSHOTS = Path(__file__).parents[1] / "snapshots"


def test_portfolio_snapshot():
    html = (FIXTURES / "portfolio_sample.html").read_text(encoding="utf-8")
    items = parse_portfolio_html(html, confidence_threshold=0.6)
    got = {it.ticker: it.action.value for it in items if it.ticker != "UNKNOWN"}

    expected = json.loads((SNAPSHOTS / "portfolio_sample.expected.json").read_text())
    assert expected["parser_version"] == PARSER_VERSION
    for ticker, action in expected["items"].items():
        assert got.get(ticker) == action, f"{ticker}: expected {action}, got {got.get(ticker)}"


def test_portfolio_structured_method_and_snippets():
    html = (FIXTURES / "portfolio_sample.html").read_text(encoding="utf-8")
    items = parse_portfolio_html(html, confidence_threshold=0.6)
    resolved = [it for it in items if it.ticker != "UNKNOWN"]
    assert resolved, "should extract at least one resolved item"
    # Structured table extraction and audit snippet retention.
    assert all(it.extraction_method is ExtractionMethod.STRUCTURED_TABLE for it in resolved)
    assert all(it.source_snippet for it in resolved)
    assert all(it.parser_version == PARSER_VERSION for it in resolved)


def test_text_fallback_when_no_table():
    html = "<html><body><p>New buy: $TSLA looks strong.</p></body></html>"
    items = parse_portfolio_html(html, confidence_threshold=0.6)
    assert any(it.ticker == "TSLA" for it in items)
    tsla = next(it for it in items if it.ticker == "TSLA")
    assert tsla.extraction_method is ExtractionMethod.TEXT_FALLBACK


def test_update_parser_extracts_actions():
    html = (FIXTURES / "update_article_sample.html").read_text(encoding="utf-8")
    items = parse_update_html(html, confidence_threshold=0.6)
    mapping = {(it.ticker, it.action) for it in items}
    assert ("CRWD", NormalizedAction.NEW_BUY) in mapping
    assert ("AVGO", NormalizedAction.ADD_MORE) in mapping
    assert ("SMCI", NormalizedAction.SELL) in mapping or ("SMCI", NormalizedAction.REMOVE) in mapping
