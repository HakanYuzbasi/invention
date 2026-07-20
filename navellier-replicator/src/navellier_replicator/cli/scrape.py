"""CLI: run an authenticated scrape.

    python -m navellier_replicator.cli.scrape
"""

from __future__ import annotations

import typer

from ..logging_config import configure_logging, get_logger
from ..settings import get_settings

app = typer.Typer(add_completion=False, help="Run an authenticated scrape of the source surfaces.")
log = get_logger(__name__)


@app.command()
def main() -> None:
    """Log in, capture the portfolio + update pages, persist raw evidence."""

    configure_logging()
    from ..jobs.scrape_run import run_scrape

    cfg = get_settings()
    run_id = run_scrape(cfg)
    typer.echo(f"Scrape run complete: run_id={run_id}")
    typer.echo(f"Next: python -m navellier_replicator.cli.parse --run-id {run_id}")


if __name__ == "__main__":
    app()
