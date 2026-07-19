"""Configuration loading and validation.

Two layers, deliberately kept separate:

* **Secrets** come from the environment (``.env`` via ``pydantic-settings``).
  Never from YAML, never committed.
* **Behavior** comes from ``config/settings.yaml`` and
  ``config/selectors.yaml`` (validated Pydantic models).

``get_settings()`` returns a single merged, validated :class:`AppConfig`. It is
cached; call :func:`reset_settings_cache` in tests to reload.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_inline_comment(value: object) -> object:
    """Tolerate env values that carry an inline ``# comment`` or stray whitespace.

    Some environments export e.g. ``IBKR_PORT=7497   # 7497=Paper`` — strip the
    comment so integer fields still parse instead of failing closed on startup.
    """

    if isinstance(value, str):
        return value.split("#", 1)[0].strip()
    return value

# Project root = two levels up from this file's package dir
# (.../src/navellier_replicator/settings.py -> repo root is parents[2]).
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]


# --------------------------------------------------------------------------- #
# Environment secrets
# --------------------------------------------------------------------------- #
class EnvSecrets(BaseSettings):
    """Secrets and connection info sourced from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    investorplace_username: str | None = None
    investorplace_password: str | None = None
    investorplace_login_url: str | None = None
    investorplace_portfolio_url: str | None = None

    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 71
    ibkr_account: str | None = None

    app_env: str = "dev"

    @field_validator("ibkr_port", "ibkr_client_id", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> object:
        return _strip_inline_comment(v)

    @field_validator("ibkr_host", "app_env", mode="before")
    @classmethod
    def _clean_str(cls, v: object) -> object:
        return _strip_inline_comment(v)

    # Optional path overrides (prefixed NR_ to avoid collisions).
    nr_data_dir: str | None = None
    nr_db_url: str | None = None
    nr_settings_file: str | None = None
    nr_selectors_file: str | None = None


# --------------------------------------------------------------------------- #
# YAML behavior config (validated)
# --------------------------------------------------------------------------- #
class SourcesConfig(BaseModel):
    login_url: str = "https://investorplace.com/login/"
    portfolio_url: str = ""
    update_urls: list[str] = Field(default_factory=list)


class ParserConfig(BaseModel):
    confidence_threshold: float = 0.60
    min_expected_actionable: int = 1

    @field_validator("confidence_threshold")
    @classmethod
    def _range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        return v


class CollectionConfig(BaseModel):
    headed: bool = False
    screenshots: bool = True
    nav_timeout_ms: int = 45000
    max_retries: int = 3
    retry_backoff_seconds: list[int] = Field(default_factory=lambda: [2, 4, 8])
    min_content_chars: int = 400


class TradingWindow(BaseModel):
    enabled: bool = True
    timezone: str = "America/New_York"
    open: str = "09:30"
    close: str = "16:00"
    weekdays_only: bool = True


class PortfolioConfig(BaseModel):
    max_active_positions: int = 5
    sizing_mode: str = "equal_weight"
    fixed_dollar_per_position: float = 2000.0
    default_policy: str = "mirror_published_if_explicit"

    @field_validator("sizing_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in {"equal_weight", "fixed_dollar"}:
            raise ValueError("sizing_mode must be 'equal_weight' or 'fixed_dollar'")
        return v


class SafetyConfig(BaseModel):
    max_set_change_fraction: float = 0.5
    trading_window: TradingWindow = Field(default_factory=TradingWindow)


class BrokerConfig(BaseModel):
    # 'paper' is the ONLY accepted mode. 'live' is rejected outright so that
    # no config edit or typo can ever enable real-money trading.
    mode: str = "paper"
    dry_run: bool = True

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v != "paper":
            raise ValueError(
                "broker.mode must be 'paper'. Live trading is not supported by this system."
            )
        return v


class RuntimeConfig(BaseModel):
    dry_run: bool = True


class Selectors(BaseModel):
    """Loose container — selector shape can evolve; we keep it as plain dicts."""

    login: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)


class AppConfig(BaseModel):
    """Fully merged, validated configuration used throughout the app."""

    env: EnvSecrets
    sources: SourcesConfig
    parser: ParserConfig
    collection: CollectionConfig
    portfolio: PortfolioConfig
    safety: SafetyConfig
    broker: BrokerConfig
    runtime: RuntimeConfig
    selectors: Selectors

    # Resolved absolute paths.
    data_dir: Path
    db_url: str

    # -- convenience resolvers (env overrides YAML for URLs) ---------------- #
    @property
    def login_url(self) -> str:
        return self.env.investorplace_login_url or self.sources.login_url

    @property
    def portfolio_url(self) -> str:
        return self.env.investorplace_portfolio_url or self.sources.portfolio_url

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must be a mapping at the top level")
    return data


def build_config(
    *,
    settings_file: str | Path | None = None,
    selectors_file: str | Path | None = None,
    data_dir: str | Path | None = None,
    db_url: str | None = None,
) -> AppConfig:
    """Construct an :class:`AppConfig` from env + YAML, applying overrides.

    Explicit arguments win over env vars, which win over defaults. This makes
    the loader fully deterministic and easy to drive from tests.
    """

    env = EnvSecrets()

    settings_path = Path(
        settings_file
        or env.nr_settings_file
        or (REPO_ROOT / "config" / "settings.yaml")
    )
    selectors_path = Path(
        selectors_file
        or env.nr_selectors_file
        or (REPO_ROOT / "config" / "selectors.yaml")
    )

    settings_raw = _read_yaml(settings_path)
    selectors_raw = _read_yaml(selectors_path)

    resolved_data_dir = Path(
        data_dir or env.nr_data_dir or (REPO_ROOT / "data")
    ).resolve()
    resolved_db_url = (
        db_url
        or env.nr_db_url
        or f"sqlite:///{(resolved_data_dir / 'navellier.db').as_posix()}"
    )

    return AppConfig(
        env=env,
        sources=SourcesConfig(**settings_raw.get("sources", {})),
        parser=ParserConfig(**settings_raw.get("parser", {})),
        collection=CollectionConfig(**settings_raw.get("collection", {})),
        portfolio=PortfolioConfig(**settings_raw.get("portfolio", {})),
        safety=SafetyConfig(**settings_raw.get("safety", {})),
        broker=BrokerConfig(**settings_raw.get("broker", {})),
        runtime=RuntimeConfig(**settings_raw.get("runtime", {})),
        selectors=Selectors(
            login=selectors_raw.get("login", {}),
            portfolio=selectors_raw.get("portfolio", {}),
        ),
        data_dir=resolved_data_dir,
        db_url=resolved_db_url,
    )


@functools.lru_cache(maxsize=1)
def get_settings() -> AppConfig:
    """Cached accessor for the application configuration."""

    cfg = build_config()
    # Ensure data directories exist (idempotent, no side effects on values).
    for d in (cfg.data_dir, cfg.raw_dir, cfg.snapshots_dir, cfg.exports_dir):
        d.mkdir(parents=True, exist_ok=True)
    return cfg


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests)."""

    get_settings.cache_clear()
