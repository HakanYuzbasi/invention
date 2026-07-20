"""CLI: compute a target portfolio (v0.2).

    python -m navellier_replicator.cli.plan --policy fifo_cap5 --as-of today

Fails closed in v0.1: target computation is enabled in v0.2.
"""

from __future__ import annotations

import typer

from ..logging_config import configure_logging

app = typer.Typer(add_completion=False, help="Compute a target portfolio by policy (v0.2).")


@app.command()
def main(
    policy: str = typer.Option("mirror_published_if_explicit", "--policy"),
    as_of: str = typer.Option("today", "--as-of"),
) -> None:
    configure_logging()
    typer.secho(
        f"plan is enabled in v0.2 (requested policy={policy}, as_of={as_of}). "
        "v0.1 performs authenticated collection and parsing only.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
