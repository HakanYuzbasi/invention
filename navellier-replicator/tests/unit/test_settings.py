from __future__ import annotations

import pytest
from pydantic import ValidationError

from navellier_replicator.settings import BrokerConfig, ParserConfig, build_config


def test_broker_rejects_live_mode():
    with pytest.raises(ValidationError):
        BrokerConfig(mode="live")


def test_broker_defaults_to_paper_dry_run():
    b = BrokerConfig()
    assert b.mode == "paper"
    assert b.dry_run is True


def test_parser_threshold_range_validated():
    with pytest.raises(ValidationError):
        ParserConfig(confidence_threshold=1.5)


def test_build_config_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = build_config(
        settings_file=tmp_path / "missing.yaml",
        selectors_file=tmp_path / "missing.yaml",
        data_dir=tmp_path / "data",
        db_url="sqlite:///:memory:",
    )
    assert cfg.portfolio.max_active_positions == 5
    assert cfg.runtime.dry_run is True
    assert cfg.broker.mode == "paper"
