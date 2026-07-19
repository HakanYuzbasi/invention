"""Collect the primary Platinum Growth portfolio page."""

from __future__ import annotations

from ..errors import ConfigError
from ..logging_config import get_logger
from ..models.dto import PageCapture
from ..models.enums import PageCategory
from ..settings import AppConfig
from .browser import BrowserSession

log = get_logger(__name__)


def collect_portfolio(session: BrowserSession, cfg: AppConfig) -> PageCapture:
    """Navigate to the configured portfolio URL and capture it.

    Assumes authentication has already happened in this session; the URL may
    still redirect (post-login navigation), which is why the capture records the
    final URL after redirects.
    """

    url = cfg.portfolio_url
    if not url:
        raise ConfigError(
            "No portfolio URL configured (env INVESTORPLACE_PORTFOLIO_URL or "
            "settings.yaml sources.portfolio_url)."
        )
    log.info("Collecting primary portfolio page: %s", url)
    session.goto(url)
    return session.capture(category=PageCategory.PRIMARY_PORTFOLIO, requested_url=url)
