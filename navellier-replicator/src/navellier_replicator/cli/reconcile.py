"""CLI: reconcile broker positions/fills (v0.3).

    python -m navellier_replicator.cli.reconcile

Fails closed in v0.1.
"""

from __future__ import annotations

import typer

from ..logging_config import configure_logging

app = typer.Typer(add_completion=False, help="Reconcile broker positions/fills into the DB (v0.3).")


@app.command()
def main() -> None:
    configure_logging()
    typer.secho(
        "reconcile is enabled in v0.3. v0.1 has no broker integration.",
        fg=typer.colors.YELLOW,
    )
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
