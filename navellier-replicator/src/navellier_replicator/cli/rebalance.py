"""CLI: plan/submit paper orders (v0.3).

    python -m navellier_replicator.cli.rebalance --paper --dry-run

Fails closed in v0.1. Paper-only and dry-run by default when enabled; live
trading is never available.
"""

from __future__ import annotations

import typer

from ..logging_config import configure_logging

app = typer.Typer(add_completion=False, help="Plan (and optionally submit) PAPER orders (v0.3).")


@app.command()
def main(
    paper: bool = typer.Option(True, "--paper/--no-paper", help="Paper mode (only paper is supported)."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run (default)."),
) -> None:
    configure_logging()
    if not paper:
        typer.secho("Live trading is not supported. Only --paper is permitted.", fg=typer.colors.RED)
        raise typer.Exit(code=2)
    typer.secho(
        f"rebalance is enabled in v0.3 (paper={paper}, dry_run={dry_run}). "
        "v0.1 does not plan or route orders.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
