"""Top-level CLI.

    python -m navellier_replicator.main run-daily --paper --dry-run

Aggregates the per-command apps and provides the daily orchestration entry
point. In v0.1 ``run-daily`` chains scrape -> parse -> report (no broker).
"""

from __future__ import annotations

import typer

from .logging_config import configure_logging, get_logger
from .settings import get_settings

app = typer.Typer(
    add_completion=False,
    help="navellier-replicator — paper-only signal-replication pipeline (dry-run by default).",
)
log = get_logger(__name__)


@app.command("run-daily")
def run_daily(
    paper: bool = typer.Option(True, "--paper/--no-paper", help="Paper mode (only paper is supported)."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run (default)."),
) -> None:
    """v0.1 daily run: scrape -> parse -> daily report. No orders are placed."""

    configure_logging()
    if not paper:
        typer.secho("Live trading is not supported. Only --paper is permitted.", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    from .jobs.parse_run import run_parse
    from .jobs.scrape_run import run_scrape
    from .reports.daily_summary import write_daily_report

    cfg = get_settings()
    typer.echo("[1/3] Scraping…")
    run_id = run_scrape(cfg)

    typer.echo(f"[2/3] Parsing run {run_id}…")
    safety = run_parse(run_id, cfg)

    typer.echo("[3/3] Writing daily report…")
    path = write_daily_report(run_id, cfg)

    typer.echo("")
    typer.echo(f"Done. run_id={run_id} · parse={'PASSED' if safety.passed else 'BLOCKED'} · report={path}")
    typer.echo("No orders were placed (order routing is v0.3, paper-only).")
    if not safety.passed:
        raise typer.Exit(code=1)


@app.command("version")
def version() -> None:
    from . import __version__

    typer.echo(__version__)


@app.command("check")
def check() -> None:
    """Run health checks and print configuration readiness (no network)."""

    configure_logging()
    from .safety.health_checks import check_broker_disabled, check_collection_ready

    cfg = get_settings()
    ready = check_collection_ready(cfg)
    broker = check_broker_disabled(cfg)

    typer.echo(f"Collection ready: {'YES' if ready.ok else 'NO'}")
    for p in ready.problems:
        typer.secho(f"  problem: {p}", fg=typer.colors.RED)
    for w in ready.warnings:
        typer.secho(f"  warning: {w}", fg=typer.colors.YELLOW)
    typer.echo(f"Broker paper-only: {'YES' if broker.ok else 'NO'}")
    typer.echo(f"DB URL: {cfg.db_url}")
    typer.echo(f"Data dir: {cfg.data_dir}")


if __name__ == "__main__":
    app()
