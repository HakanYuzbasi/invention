"""Shared pytest fixtures.

Every test runs against an isolated temp SQLite DB and an isolated working
directory so no real ``.env`` or ``data/`` is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from navellier_replicator import settings as settings_mod
from navellier_replicator.db import session as session_mod
from navellier_replicator.db.base import Base
from navellier_replicator.models import orm as _orm  # noqa: F401  (registers tables)

FIXTURES = Path(__file__).parent / "fixtures"

_CRED_ENV = [
    "INVESTORPLACE_USERNAME",
    "INVESTORPLACE_PASSWORD",
    "INVESTORPLACE_LOGIN_URL",
    "INVESTORPLACE_PORTFOLIO_URL",
    "NR_DATA_DIR",
    "NR_DB_URL",
    "NR_SETTINGS_FILE",
    "NR_SELECTORS_FILE",
]


@pytest.fixture
def app_cfg(tmp_path, monkeypatch):
    # Isolate: no stray env, no real .env in cwd.
    for k in _CRED_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"

    cfg = settings_mod.build_config(
        settings_file=tmp_path / "no_settings.yaml",
        selectors_file=tmp_path / "no_selectors.yaml",
        data_dir=data_dir,
        db_url=db_url,
    )

    session_mod.reset_engine()
    engine = session_mod.get_engine(cfg)
    Base.metadata.create_all(engine)

    yield cfg

    session_mod.reset_engine()


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
