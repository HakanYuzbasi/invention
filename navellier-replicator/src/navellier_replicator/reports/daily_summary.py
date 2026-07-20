"""Daily markdown report.

Renders a run's forensic summary: scrape status, pages visited, parse counts,
the new-vs-previous recommendation diff, the current active set, target-by-policy
and proposed-orders placeholders (pending v0.2/v0.3), reconciliation status, and
all audit flags. Everything comes from the DB so the report is reproducible.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..models.enums import NormalizedAction
from ..parsers import PARSER_VERSION
from ..settings import AppConfig, get_settings


def _active_tickers(items) -> set[str]:
    """Tickers whose latest action implies an active holding."""

    result: set[str] = set()
    for it in items:
        try:
            action = NormalizedAction(it.action)
        except ValueError:
            continue
        if action.implies_active_holding:
            result.add(it.ticker)
    return result


def build_daily_report(run_id: int, cfg: AppConfig | None = None) -> str:
    from ..db.repositories import (
        AuditFlagRepository,
        ExtractedItemRepository,
        RawPageRepository,
        ScrapeRunRepository,
    )
    from ..db.session import session_scope

    cfg = cfg or get_settings()
    lines: list[str] = []

    with session_scope(cfg) as session:
        run_repo = ScrapeRunRepository(session)
        raw_repo = RawPageRepository(session)
        item_repo = ExtractedItemRepository(session)
        flag_repo = AuditFlagRepository(session)

        run = run_repo.get(run_id)
        if run is None:
            raise ValueError(f"No scrape run with id={run_id}")

        pages = raw_repo.for_run(run_id)
        items = item_repo.for_run(run_id, parser_version=PARSER_VERSION)
        flags = flag_repo.for_run(run_id)

        # Previous run for diffing.
        recent = run_repo.latest(limit=10)
        prev_run = next((r for r in recent if r.id < run_id), None)
        prev_items = (
            item_repo.for_run(prev_run.id, parser_version=PARSER_VERSION) if prev_run else []
        )

        cur_active = _active_tickers(items)
        prev_active = _active_tickers(prev_items)
        added = sorted(cur_active - prev_active)
        removed = sorted(prev_active - cur_active)
        action_counts = Counter(it.action for it in items)

        gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        lines.append(f"# Navellier Replicator — Daily Report (run {run_id})")
        lines.append("")
        lines.append(f"_Generated {gen} · parser {PARSER_VERSION} · env {run.app_env}_")
        lines.append("")

        # --- Scrape status ---
        lines.append("## Scrape status")
        lines.append("")
        lines.append(f"- Run id: **{run_id}**")
        lines.append(f"- Status: **{run.status}**")
        lines.append(f"- Started: {run.started_at}")
        lines.append(f"- Finished: {run.finished_at}")
        lines.append(f"- Artifacts dir: `{run.run_dir}`")
        if run.error:
            lines.append(f"- Error: `{run.error}`")
        lines.append("")

        # --- Pages visited ---
        lines.append("## Pages visited")
        lines.append("")
        if pages:
            lines.append("| # | Category | Final URL | Text chars | SHA256 (12) | OK |")
            lines.append("|---|----------|-----------|-----------:|-------------|----|")
            for i, p in enumerate(pages, 1):
                ok = "✓" if p.http_ok and not p.error else "✗"
                lines.append(
                    f"| {i} | {p.category} | {p.final_url} | {p.content_len} | "
                    f"`{(p.content_sha256 or '')[:12]}` | {ok} |"
                )
        else:
            lines.append("_No pages captured._")
        lines.append("")

        # --- Parse counts ---
        lines.append("## Parse counts")
        lines.append("")
        lines.append(f"- Total extracted items: **{len(items)}**")
        actionable = sum(
            1 for it in items
            if NormalizedAction(it.action).is_actionable and it.action != NormalizedAction.UNKNOWN.value
        )
        lines.append(f"- Actionable items: **{actionable}**")
        if action_counts:
            lines.append("")
            lines.append("| Action | Count |")
            lines.append("|--------|------:|")
            for action, count in sorted(action_counts.items()):
                lines.append(f"| {action} | {count} |")
        lines.append("")

        # --- Diff ---
        lines.append("## New vs previous recommendations")
        lines.append("")
        if prev_run is None:
            lines.append("_No previous run to compare against._")
        else:
            lines.append(f"Compared against run **{prev_run.id}**.")
            lines.append("")
            lines.append(f"- **Added active names:** {', '.join(added) if added else '_none_'}")
            lines.append(f"- **Removed active names:** {', '.join(removed) if removed else '_none_'}")
        lines.append("")

        # --- Current active set ---
        lines.append("## Current active recommendation set")
        lines.append("")
        if cur_active:
            for t in sorted(cur_active):
                lines.append(f"- {t}")
        else:
            lines.append("_No active names extracted._")
        lines.append("")

        # --- Targets (v0.2) ---
        lines.append("## Target portfolio by policy")
        lines.append("")
        lines.append(
            f"_Pending v0.2. Cap = {cfg.portfolio.max_active_positions} holdings; "
            f"default policy `{cfg.portfolio.default_policy}`; "
            f"sizing `{cfg.portfolio.sizing_mode}`._"
        )
        lines.append("")

        # --- Orders (v0.3) ---
        lines.append("## Proposed orders")
        lines.append("")
        lines.append("_Pending v0.3. Paper-only, dry-run by default; live trading is never enabled._")
        lines.append("")

        # --- Reconciliation (v0.3) ---
        lines.append("## Reconciliation status")
        lines.append("")
        lines.append("_Pending v0.3. No broker integration in v0.1._")
        lines.append("")

        # --- Audit flags ---
        lines.append("## Audit flags")
        lines.append("")
        if flags:
            lines.append("| Severity | Type | Message |")
            lines.append("|----------|------|---------|")
            for f in flags:
                lines.append(f"| {f.severity} | {f.flag_type} | {f.message} |")
        else:
            lines.append("_No audit flags raised._")
        lines.append("")

    return "\n".join(lines)


def write_daily_report(run_id: int, cfg: AppConfig | None = None) -> Path:
    cfg = cfg or get_settings()
    content = build_daily_report(run_id, cfg)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = cfg.exports_dir / f"daily_report_run{run_id}_{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return out
