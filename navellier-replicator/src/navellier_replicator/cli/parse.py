"""CLI: parse a scrape run's raw pages into extracted items + report.

    python -m navellier_replicator.cli.parse --run-id <id>
"""

from __future__ import annotations

import typer

from ..logging_config import configure_logging, get_logger
from ..settings import get_settings

app = typer.Typer(add_completion=False, help="Parse captured pages into normalized items.")
log = get_logger(__name__)


@app.command()
def main(
    run_id: int = typer.Option(..., "--run-id", help="scrape_runs.id to parse."),
    report: bool = typer.Option(True, help="Also write the daily markdown report."),
) -> None:
    configure_logging()
    from ..jobs.parse_run import run_parse
    from ..reports.daily_summary import write_daily_report

    cfg = get_settings()
    safety = run_parse(run_id, cfg)
    typer.echo(
        f"Parse complete for run {run_id}: "
        f"{'PASSED' if safety.passed else 'BLOCKED'} "
        f"({len(safety.blocking_flags)} blocking flag(s))."
    )
    if report:
        path = write_daily_report(run_id, cfg)
        typer.echo(f"Report written: {path}")
    if not safety.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
