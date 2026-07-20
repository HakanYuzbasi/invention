"""Collect update/article/subpage surfaces.

Platinum Growth is a combined offering and may expose more than one signal
surface, so this collector iterates every configured update URL and captures
each independently. A failure on one page does not abort the others.
"""

from __future__ import annotations

from ..logging_config import get_logger
from ..models.dto import PageCapture
from ..models.enums import PageCategory
from ..settings import AppConfig
from .browser import BrowserSession

log = get_logger(__name__)


def collect_update_pages(session: BrowserSession, cfg: AppConfig) -> list[PageCapture]:
    urls = list(cfg.sources.update_urls or [])
    captures: list[PageCapture] = []
    if not urls:
        log.info("No update URLs configured; skipping update-page collection.")
        return captures

    for url in urls:
        try:
            log.info("Collecting update page: %s", url)
            session.goto(url)
            captures.append(session.capture(category=PageCategory.UPDATE, requested_url=url))
        except Exception as e:  # noqa: BLE001 - isolate per-page failures
            log.error("Failed to collect update page %s: %s", url, e)
            captures.append(
                PageCapture(
                    category=PageCategory.UPDATE,
                    requested_url=url,
                    final_url=url,
                    http_ok=False,
                    html="",
                    visible_text="",
                    screenshot_path=None,
                    content_sha256="",
                    error=str(e),
                )
            )
    return captures
