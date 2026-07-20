"""Parse job: raw pages -> extracted items -> parser-time safety.

Deterministic and offline. Given a scrape run id, it re-reads the persisted raw
pages and produces extracted items with the current parser version. Re-running
with the same parser version is idempotent (it replaces that version's rows);
running a newer parser version ADDS rows, preserving prior evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..logging_config import get_logger
from ..models.dto import ParsedItem, SafetyResult
from ..models.enums import PageCategory, RunStatus
from ..parsers import PARSER_VERSION
from ..parsers.portfolio_parser import parse_portfolio_html
from ..parsers.update_parser import parse_update_html
from ..safety import guards
from ..settings import AppConfig, get_settings

log = get_logger(__name__)


def parse_page(category: str, html: str, cfg: AppConfig) -> list[ParsedItem]:
    """Dispatch a single page's HTML to the right parser."""

    threshold = cfg.parser.confidence_threshold
    if category == PageCategory.PRIMARY_PORTFOLIO.value:
        return parse_portfolio_html(
            html, confidence_threshold=threshold, selectors=cfg.selectors.portfolio
        )
    if category in (PageCategory.UPDATE.value, PageCategory.SUBPAGE.value):
        return parse_update_html(html, confidence_threshold=threshold)
    # Login and unknown pages are not parsed for signals.
    return []


def run_parse(run_id: int, cfg: AppConfig | None = None) -> SafetyResult:
    """Parse all raw pages for a run, persist items, run guards. Returns safety."""

    from ..db.repositories import (
        AuditFlagRepository,
        ExtractedItemRepository,
        RawPageRepository,
        ScrapeRunRepository,
    )
    from ..db.session import session_scope

    cfg = cfg or get_settings()
    all_items: list[ParsedItem] = []

    with session_scope(cfg) as session:
        run = ScrapeRunRepository(session).get(run_id)
        if run is None:
            raise ValueError(f"No scrape run with id={run_id}")

        raw_repo = RawPageRepository(session)
        item_repo = ExtractedItemRepository(session)

        # Idempotency for this parser version.
        removed = item_repo.delete_for_run_version(run_id, PARSER_VERSION)
        if removed:
            log.info("Removed %d prior items for parser %s (re-parse).", removed, PARSER_VERSION)

        pages = raw_repo.for_run(run_id)
        for page in pages:
            if page.error or not page.html:
                continue
            items = parse_page(page.category, page.html, cfg)
            for it in items:
                item_repo.add(run_id=run_id, raw_page_id=page.id, item=it)
            all_items.extend(items)
            log.info(
                "Parsed page %d (%s): %d items (%d actionable).",
                page.id, page.category, len(items),
                sum(1 for i in items if i.is_actionable),
            )

        # Parser-time safety guards.
        safety = guards.check_actionable_items(
            all_items, min_expected=cfg.parser.min_expected_actionable
        )
        safety = safety.merge(
            guards.check_confidence(all_items, threshold=cfg.parser.confidence_threshold)
        )

        flag_repo = AuditFlagRepository(session)
        for flag in safety.flags:
            flag_repo.add(run_id, flag)

        run_repo = ScrapeRunRepository(session)
        status = RunStatus.BLOCKED if not safety.passed else RunStatus.PARSED
        run_repo.set_status(run_repo.get(run_id), status, finished_at=datetime.now(timezone.utc))

    log.info(
        "Parse of run %d complete: %d items, safety=%s.",
        run_id, len(all_items), "PASS" if safety.passed else "BLOCK",
    )
    return safety
