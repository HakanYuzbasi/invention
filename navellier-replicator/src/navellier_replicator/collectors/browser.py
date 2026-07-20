"""Browser session management and forensic page capture.

A thin, heavily instrumented wrapper over Playwright's sync API. Every visited
page yields a :class:`~navellier_replicator.models.dto.PageCapture` containing
HTML, visible text, a screenshot path, the SHA256 of the content, and the
post-redirect final URL. Failures produce a failure screenshot and are logged.

Playwright is imported lazily so the rest of the package (parsers, models, DB)
can be imported and tested without the browser dependency installed.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

from ..errors import CollectionError
from ..logging_config import get_logger
from ..models.dto import PageCapture
from ..models.enums import PageCategory

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import Browser, BrowserContext, Page

log = get_logger(__name__)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


class BrowserSession:
    """Owns a Playwright browser + context for the lifetime of a run."""

    def __init__(
        self,
        *,
        run_dir: Path,
        headed: bool = False,
        screenshots: bool = True,
        nav_timeout_ms: int = 45000,
        max_retries: int = 3,
        retry_backoff_seconds: list[int] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.headed = headed
        self.screenshots = screenshots
        self.nav_timeout_ms = nav_timeout_ms
        self.max_retries = max(1, max_retries)
        self.retry_backoff_seconds = retry_backoff_seconds or [2, 4, 8]

        self._pw: Any = None
        self._browser: "Browser | None" = None
        self._context: "BrowserContext | None" = None
        self._page: "Page | None" = None
        self._page_counter = 0

    # -- lifecycle ---------------------------------------------------------- #
    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover - exercised only without dep
            raise CollectionError(
                "Playwright is not installed. Run `pip install -e .` and "
                "`python -m playwright install chromium`."
            ) from e

        self._pw = sync_playwright().start()

        # In an egress-gated environment (e.g. a sandbox) Chromium must route
        # through the configured proxy or direct connections are reset. Honor
        # HTTPS_PROXY when present; on a normal machine (no proxy env) launch is
        # unchanged and TLS validation below stays strict.
        proxy_server = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        launch_kwargs: dict[str, object] = {"headless": not self.headed}
        if proxy_server:
            launch_kwargs["proxy"] = {"server": proxy_server}
            log.info("Routing browser through proxy: %s", proxy_server)
        self._browser = self._pw.chromium.launch(**launch_kwargs)

        # TLS verification is always left strict; a trusted CA (e.g. a corporate
        # or sandbox proxy CA) belongs in the browser's trust store, not disabled
        # here.
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 2200},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
        )
        self._context.set_default_timeout(self.nav_timeout_ms)
        self._page = self._context.new_page()
        log.info("Browser session started (headed=%s)", self.headed)

    def close(self) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            if closer is not None:
                try:
                    closer()
                except Exception as e:  # pragma: no cover
                    log.debug("Error during browser teardown: %s", e)
        self._page = self._context = self._browser = self._pw = None
        log.info("Browser session closed")

    @property
    def page(self) -> "Page":
        if self._page is None:
            raise CollectionError("Browser session not started")
        return self._page

    # -- navigation & capture ---------------------------------------------- #
    def goto(self, url: str, *, wait_until: str = "networkidle") -> None:
        """Navigate with bounded retries and exponential backoff."""

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info("Navigating (attempt %d/%d): %s", attempt, self.max_retries, url)
                self.page.goto(url, wait_until=wait_until)
                return
            except Exception as e:  # noqa: BLE001 - we log and retry deliberately
                last_err = e
                backoff = self.retry_backoff_seconds[min(attempt - 1, len(self.retry_backoff_seconds) - 1)]
                log.warning("Navigation failed (%s). Backing off %ss.", e, backoff)
                if attempt < self.max_retries:
                    time.sleep(backoff)
        raise CollectionError(f"Navigation to {url} failed after {self.max_retries} attempts: {last_err}")

    def _next_slug(self, category: PageCategory) -> str:
        self._page_counter += 1
        return f"{self._page_counter:02d}_{category.value.lower()}"

    def capture(self, *, category: PageCategory, requested_url: str) -> PageCapture:
        """Capture the current page state into a PageCapture and persist artifacts."""

        slug = self._next_slug(category)
        page = self.page
        error: str | None = None
        screenshot_path: str | None = None

        try:
            final_url = page.url
            html = page.content()
            try:
                visible_text = page.inner_text("body")
            except Exception:  # body may be missing on error pages
                visible_text = ""

            # Persist raw artifacts alongside the DB row for forensic replay.
            (self.run_dir / f"{slug}.html").write_text(html, encoding="utf-8")
            (self.run_dir / f"{slug}.txt").write_text(visible_text, encoding="utf-8")
            if self.screenshots:
                shot = self.run_dir / f"{slug}.png"
                try:
                    page.screenshot(path=str(shot), full_page=True)
                    screenshot_path = str(shot)
                except Exception as e:  # pragma: no cover
                    log.debug("Screenshot failed: %s", e)

            content_hash = sha256_text(html)
            log.info(
                "Captured %s (%d chars text, sha=%s) final_url=%s",
                category.value, len(visible_text), content_hash[:12], final_url,
            )
            return PageCapture(
                category=category,
                requested_url=requested_url,
                final_url=final_url,
                http_ok=True,
                html=html,
                visible_text=visible_text,
                screenshot_path=screenshot_path,
                content_sha256=content_hash,
                error=None,
            )
        except Exception as e:  # noqa: BLE001
            error = str(e)
            log.error("Capture failed for %s: %s", requested_url, error)
            self.failure_screenshot(slug)
            # Return a capture recording the failure rather than raising, so the
            # run persists evidence of what went wrong.
            return PageCapture(
                category=category,
                requested_url=requested_url,
                final_url=getattr(page, "url", requested_url),
                http_ok=False,
                html="",
                visible_text="",
                screenshot_path=screenshot_path,
                content_sha256=sha256_text(error or "error"),
                error=error,
            )

    def failure_screenshot(self, slug: str) -> str | None:
        if not self.screenshots or self._page is None:
            return None
        path = self.run_dir / f"{slug}_FAILURE.png"
        try:
            self._page.screenshot(path=str(path), full_page=True)
            log.info("Wrote failure screenshot: %s", path)
            return str(path)
        except Exception as e:  # pragma: no cover
            log.debug("Failure screenshot failed: %s", e)
            return None
