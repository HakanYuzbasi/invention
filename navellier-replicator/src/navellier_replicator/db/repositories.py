"""Typed repository helpers.

Thin persistence helpers that translate DTOs into ORM rows and back. They keep
session/ORM details out of the jobs and make the append-only discipline
explicit (e.g. extracted items are always inserted, never updated).
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.dto import AuditFlag, PageCapture, ParsedItem
from ..models.enums import RunStatus
from ..models.orm import (
    AuditFlagRow,
    ExtractedItem,
    RawPage,
    ScrapeRun,
)


class ScrapeRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, status: RunStatus, app_env: str, started_at: datetime,
               run_dir: str | None) -> ScrapeRun:
        run = ScrapeRun(
            status=status.value,
            app_env=app_env,
            started_at=started_at,
            run_dir=run_dir,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id: int) -> ScrapeRun | None:
        return self.session.get(ScrapeRun, run_id)

    def set_status(self, run: ScrapeRun, status: RunStatus, *,
                   error: str | None = None, finished_at: datetime | None = None) -> None:
        run.status = status.value
        if error is not None:
            run.error = error
        if finished_at is not None:
            run.finished_at = finished_at
        self.session.flush()

    def latest(self, limit: int = 2) -> list[ScrapeRun]:
        stmt = select(ScrapeRun).order_by(ScrapeRun.id.desc()).limit(limit)
        return list(self.session.scalars(stmt))


class RawPageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run_id: int, capture: PageCapture) -> RawPage:
        page = RawPage(
            run_id=run_id,
            category=capture.category.value,
            requested_url=capture.requested_url,
            final_url=capture.final_url,
            http_ok=capture.http_ok,
            html=capture.html,
            visible_text=capture.visible_text,
            screenshot_path=capture.screenshot_path,
            content_sha256=capture.content_sha256,
            content_len=capture.content_len,
            captured_at=capture.captured_at,
            error=capture.error,
        )
        self.session.add(page)
        self.session.flush()
        return page

    def for_run(self, run_id: int) -> list[RawPage]:
        stmt = select(RawPage).where(RawPage.run_id == run_id).order_by(RawPage.id)
        return list(self.session.scalars(stmt))


class ExtractedItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *, run_id: int, raw_page_id: int, item: ParsedItem) -> ExtractedItem:
        """Append a parsed item. Never updates existing rows — parser upgrades
        add new evidence keyed by parser_version."""

        row = ExtractedItem(
            run_id=run_id,
            raw_page_id=raw_page_id,
            parser_version=item.parser_version,
            ticker=item.ticker,
            company_name=item.company_name,
            action=item.action.value,
            confidence=item.confidence,
            confidence_band=item.confidence_band.value,
            extraction_method=item.extraction_method.value,
            source_snippet=item.source_snippet,
            notes_json=json.dumps(item.notes) if item.notes else None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def for_run(self, run_id: int, parser_version: str | None = None) -> list[ExtractedItem]:
        stmt = select(ExtractedItem).where(ExtractedItem.run_id == run_id)
        if parser_version is not None:
            stmt = stmt.where(ExtractedItem.parser_version == parser_version)
        stmt = stmt.order_by(ExtractedItem.id)
        return list(self.session.scalars(stmt))

    def delete_for_run_version(self, run_id: int, parser_version: str) -> int:
        """Remove prior rows for a specific (run, parser_version) so re-parsing
        the SAME version is idempotent. Older/newer versions are untouched, so
        historical evidence from other parser versions is preserved."""

        rows = list(
            self.session.scalars(
                select(ExtractedItem).where(
                    ExtractedItem.run_id == run_id,
                    ExtractedItem.parser_version == parser_version,
                )
            )
        )
        for r in rows:
            self.session.delete(r)
        self.session.flush()
        return len(rows)


class AuditFlagRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run_id: int | None, flag: AuditFlag) -> AuditFlagRow:
        row = AuditFlagRow(
            run_id=run_id,
            flag_type=flag.flag_type.value,
            severity=flag.severity.value,
            message=flag.message,
            context_json=json.dumps(flag.context) if flag.context else None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def for_run(self, run_id: int) -> list[AuditFlagRow]:
        stmt = select(AuditFlagRow).where(AuditFlagRow.run_id == run_id).order_by(AuditFlagRow.id)
        return list(self.session.scalars(stmt))

    def unresolved(self) -> list[AuditFlagRow]:
        stmt = select(AuditFlagRow).where(AuditFlagRow.resolved.is_(False))
        return list(self.session.scalars(stmt))
