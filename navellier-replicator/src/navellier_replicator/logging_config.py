"""Structured logging setup.

Console logging via Rich, plus an optional per-run file handler so every
scrape/parse run leaves a durable, greppable log alongside its raw artifacts.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

_CONFIGURED = False
_LOG_FORMAT = "%(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Install the Rich console handler once (idempotent)."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=False,
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="[%X]"))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Quiet noisy third-party loggers.
    for noisy in ("asyncio", "urllib3", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def add_run_file_handler(run_dir: Path, level: int = logging.DEBUG) -> logging.Handler:
    """Attach a file handler writing DEBUG logs into ``run_dir/run.log``.

    Returns the handler so the caller can remove it when the run finishes.
    """

    run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    logging.getLogger().addHandler(file_handler)
    return file_handler


def remove_handler(handler: logging.Handler) -> None:
    """Detach and close a previously added handler."""

    logging.getLogger().removeHandler(handler)
    handler.close()


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, ensuring console logging is configured."""

    configure_logging()
    return logging.getLogger(name)
