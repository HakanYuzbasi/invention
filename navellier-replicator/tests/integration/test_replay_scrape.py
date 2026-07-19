"""Integration: replay saved scrape artifacts into parsed events and a report.

No network, no browser. Insert raw pages from the HTML fixtures (as a real scrape
would have persisted them), run the parse job, and verify extracted items,
safety, and the rendered daily report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from navellier_replicator.collectors.browser import sha256_text
from navellier_replicator.db.repositories import (
    ExtractedItemRepository,
    RawPageRepository,
    ScrapeRunRepository,
)
from navellier_replicator.db.session import session_scope
from navellier_replicator.jobs.parse_run import run_parse
from navellier_replicator.models.dto import PageCapture
from navellier_replicator.models.enums import PageCategory, RunStatus
from navellier_replicator.reports.daily_summary import build_daily_report

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _capture(category: PageCategory, url: str, html: str) -> PageCapture:
    return PageCapture(
        category=category,
        requested_url=url,
        final_url=url,
        http_ok=True,
        html=html,
        visible_text="x" * 600,  # rich enough to pass content guard
        content_sha256=sha256_text(html),
    )


def _seed_run(cfg) -> int:
    portfolio_html = (FIXTURES / "portfolio_sample.html").read_text(encoding="utf-8")
    update_html = (FIXTURES / "update_article_sample.html").read_text(encoding="utf-8")
    with session_scope(cfg) as session:
        run = ScrapeRunRepository(session).create(
            status=RunStatus.COLLECTED,
            app_env="test",
            started_at=datetime.now(timezone.utc),
            run_dir="/tmp/none",
        )
        raw = RawPageRepository(session)
        raw.add(run.id, _capture(PageCategory.PRIMARY_PORTFOLIO, "https://x/portfolio", portfolio_html))
        raw.add(run.id, _capture(PageCategory.UPDATE, "https://x/update", update_html))
        return run.id


def test_replay_parses_and_persists_items(app_cfg):
    run_id = _seed_run(app_cfg)
    safety = run_parse(run_id, app_cfg)
    assert safety.passed

    with session_scope(app_cfg) as session:
        items = ExtractedItemRepository(session).for_run(run_id)
    tickers = {it.ticker for it in items}
    # From the portfolio table + update article.
    assert {"NVDA", "PLTR", "SMCI", "CRWD"}.issubset(tickers)
    assert all(it.parser_version == "0.1.0" for it in items)


def test_reparse_same_version_is_idempotent(app_cfg):
    run_id = _seed_run(app_cfg)
    run_parse(run_id, app_cfg)
    with session_scope(app_cfg) as session:
        n1 = len(ExtractedItemRepository(session).for_run(run_id))
    run_parse(run_id, app_cfg)
    with session_scope(app_cfg) as session:
        n2 = len(ExtractedItemRepository(session).for_run(run_id))
    assert n1 == n2 and n1 > 0


def test_daily_report_renders_expected_sections(app_cfg):
    run_id = _seed_run(app_cfg)
    run_parse(run_id, app_cfg)
    report = build_daily_report(run_id, app_cfg)
    for section in [
        "## Scrape status",
        "## Pages visited",
        "## Parse counts",
        "## Current active recommendation set",
        "## Audit flags",
    ]:
        assert section in report
    assert "NVDA" in report


def test_diff_between_two_runs(app_cfg):
    first = _seed_run(app_cfg)
    run_parse(first, app_cfg)
    second = _seed_run(app_cfg)
    run_parse(second, app_cfg)
    report = build_daily_report(second, app_cfg)
    # Same fixtures => no added/removed active names on the second run.
    assert "New vs previous recommendations" in report
    assert f"Compared against run **{first}**" in report
