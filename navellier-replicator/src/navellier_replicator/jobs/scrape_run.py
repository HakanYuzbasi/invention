"""Scrape job: authenticated collection -> raw page persistence -> safety.

This is the only job that touches the live site. It is defensive throughout:
it holds a run lock, persists every captured page (including failures), runs the
collection-time safety guards, and records audit flags. It never raises past the
top level without first recording run status.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from ..logging_config import add_run_file_handler, get_logger, remove_handler
from ..models.dto import PageCapture, SafetyResult
from ..models.enums import RunStatus
from ..safety import guards
from ..safety.health_checks import check_collection_ready
from ..safety.locks import RunLock
from ..settings import AppConfig, get_settings

log = get_logger(__name__)


def _make_run_dir(cfg: AppConfig) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = cfg.raw_dir / f"{stamp}_scrape"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def run_scrape(cfg: AppConfig | None = None) -> int:
    """Execute a full scrape run. Returns the scrape_runs.id."""

    from ..db.repositories import (
        AuditFlagRepository,
        RawPageRepository,
        ScrapeRunRepository,
    )
    from ..db.session import session_scope

    cfg = cfg or get_settings()
    run_dir = _make_run_dir(cfg)
    file_handler = add_run_file_handler(run_dir)

    lock = RunLock(cfg.data_dir / "scrape.lock")
    run_id: int | None = None
    try:
        lock.acquire()

        health = check_collection_ready(cfg)
        for w in health.warnings:
            log.warning("Health warning: %s", w)
        if not health.ok:
            for p in health.problems:
                log.error("Health problem: %s", p)
            raise RuntimeError("Collection health check failed: " + "; ".join(health.problems))

        # Create the run row up front so evidence is linked even on failure.
        with session_scope(cfg) as session:
            run = ScrapeRunRepository(session).create(
                status=RunStatus.STARTED,
                app_env=cfg.env.app_env,
                started_at=datetime.now(timezone.utc),
                run_dir=str(run_dir),
            )
            run_id = run.id
        log.info("Started scrape run id=%d dir=%s", run_id, run_dir)

        captures = _collect(cfg, run_dir)

        # Persist all captures.
        with session_scope(cfg) as session:
            raw_repo = RawPageRepository(session)
            for cap in captures:
                raw_repo.add(run_id, cap)
            run_repo = ScrapeRunRepository(session)
            run_repo.set_status(run_repo.get(run_id), RunStatus.COLLECTED)

        # Collection-time safety guards.
        safety = _run_collection_guards(cfg, captures)
        with session_scope(cfg) as session:
            flag_repo = AuditFlagRepository(session)
            for flag in safety.flags:
                flag_repo.add(run_id, flag)
            status = RunStatus.BLOCKED if not safety.passed else RunStatus.COLLECTED
            run_repo = ScrapeRunRepository(session)
            run_repo.set_status(
                run_repo.get(run_id), status, finished_at=datetime.now(timezone.utc)
            )
        if not safety.passed:
            log.error("Scrape run %d BLOCKED by safety guards.", run_id)
        else:
            log.info("Scrape run %d collected %d pages.", run_id, len(captures))
        return run_id

    except Exception as e:
        log.exception("Scrape run failed: %s", e)
        if run_id is not None:
            try:
                with session_scope(cfg) as session:
                    repo = ScrapeRunRepository(session)
                    repo.set_status(
                        repo.get(run_id), RunStatus.FAILED,
                        error=str(e), finished_at=datetime.now(timezone.utc),
                    )
            except Exception:  # pragma: no cover - best-effort status write
                log.debug("Could not record FAILED status for run %s", run_id)
        raise
    finally:
        lock.release()
        remove_handler(file_handler)


def _collect(cfg: AppConfig, run_dir: Path) -> list[PageCapture]:
    from ..collectors.browser import BrowserSession
    from ..collectors.investorplace_auth import login
    from ..collectors.platinum_portfolio import collect_portfolio
    from ..collectors.update_pages import collect_update_pages

    captures: list[PageCapture] = []
    with BrowserSession(
        run_dir=run_dir,
        headed=cfg.collection.headed,
        screenshots=cfg.collection.screenshots,
        nav_timeout_ms=cfg.collection.nav_timeout_ms,
        max_retries=cfg.collection.max_retries,
        retry_backoff_seconds=cfg.collection.retry_backoff_seconds,
    ) as session:
        captures.append(login(session, cfg))
        captures.append(collect_portfolio(session, cfg))
        captures.extend(collect_update_pages(session, cfg))
    return captures


def _run_collection_guards(cfg: AppConfig, captures: list[PageCapture]) -> SafetyResult:
    """Run content + source-shape guards, comparing against prior runs."""

    from ..db.repositories import RawPageRepository, ScrapeRunRepository
    from ..db.session import session_scope

    result = guards.check_login_content(captures, min_content_chars=cfg.collection.min_content_chars)

    # Compare against the previous run's portfolio hashes for shape drift.
    previous_hashes: set[str] = set()
    with session_scope(cfg) as session:
        runs = ScrapeRunRepository(session).latest(limit=3)
        raw_repo = RawPageRepository(session)
        for r in runs[1:]:  # skip current
            for p in raw_repo.for_run(r.id):
                if p.category == "PRIMARY_PORTFOLIO":
                    previous_hashes.add(p.content_sha256)
    result = result.merge(guards.check_source_shape(captures, previous_hashes))
    return result
