"""Pre-run environment and configuration health checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..settings import AppConfig


@dataclass
class HealthReport:
    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_collection_ready(cfg: AppConfig) -> HealthReport:
    """Verify the minimum config needed to run a scrape is present."""

    problems: list[str] = []
    warnings: list[str] = []

    if not cfg.env.investorplace_username or not cfg.env.investorplace_password:
        problems.append("Missing INVESTORPLACE_USERNAME / INVESTORPLACE_PASSWORD in .env")
    if not cfg.login_url:
        problems.append("No login URL configured")
    if not cfg.portfolio_url:
        problems.append("No portfolio URL configured")
    if not cfg.selectors.login:
        warnings.append("No login selectors configured (config/selectors.yaml)")
    if not cfg.sources.update_urls:
        warnings.append("No update URLs configured; only the primary portfolio page will be captured")

    return HealthReport(ok=not problems, problems=problems, warnings=warnings)


def check_broker_disabled(cfg: AppConfig) -> HealthReport:
    """Confirm the broker is in paper mode. Live mode is impossible by config
    validation, but this makes the invariant explicit and testable."""

    problems: list[str] = []
    if cfg.broker.mode != "paper":
        problems.append(f"Broker mode is '{cfg.broker.mode}', expected 'paper'")
    return HealthReport(ok=not problems, problems=problems)
