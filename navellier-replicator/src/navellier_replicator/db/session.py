"""Engine and session factory.

SQLite for v1. WAL + foreign-keys pragmas are enabled for durability and
referential integrity.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..settings import AppConfig, get_settings

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_engine_url: str | None = None


def _apply_sqlite_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - trivial
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_engine(cfg: AppConfig | None = None) -> Engine:
    """Return a process-wide engine, rebuilding it if the DB URL changed."""

    global _engine, _Session, _engine_url
    cfg = cfg or get_settings()
    if _engine is None or _engine_url != cfg.db_url:
        connect_args = {"check_same_thread": False} if cfg.db_url.startswith("sqlite") else {}
        _engine = create_engine(cfg.db_url, future=True, connect_args=connect_args)
        if cfg.db_url.startswith("sqlite"):
            event.listen(_engine, "connect", _apply_sqlite_pragmas)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        _engine_url = cfg.db_url
    return _engine


def get_sessionmaker(cfg: AppConfig | None = None) -> sessionmaker[Session]:
    get_engine(cfg)
    assert _Session is not None
    return _Session


@contextmanager
def session_scope(cfg: AppConfig | None = None) -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error."""

    factory = get_sessionmaker(cfg)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose and clear the cached engine (used by tests)."""

    global _engine, _Session, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None
    _engine_url = None
