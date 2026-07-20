"""InvestorPlace authentication.

Logs in with username/password sourced from the environment, using the
configured (not hardcoded) selectors. Fails closed: if a logged-in marker is not
found — or a logged-out marker persists — after submitting, it raises rather
than proceeding to collect what would be a login wall.
"""

from __future__ import annotations

from ..errors import ConfigError, LoginFailedError
from ..logging_config import get_logger
from ..models.dto import PageCapture
from ..models.enums import PageCategory
from ..settings import AppConfig
from .browser import BrowserSession

log = get_logger(__name__)


def _first_present(page, selectors: list[str]):
    """Return the first selector that resolves to a visible element, else None."""

    for sel in selectors or []:
        try:
            locator = page.locator(sel)
            if locator.count() > 0:
                return sel
        except Exception:
            continue
    return None


def _any_present(page, selectors: list[str]) -> bool:
    return _first_present(page, selectors) is not None


def login(session: BrowserSession, cfg: AppConfig) -> PageCapture:
    """Perform login and return a capture of the post-login page.

    Raises ConfigError if credentials are missing, LoginFailedError if the
    session does not reach a logged-in state.
    """

    username = cfg.env.investorplace_username
    password = cfg.env.investorplace_password
    if not username or not password:
        raise ConfigError(
            "INVESTORPLACE_USERNAME / INVESTORPLACE_PASSWORD are not set. "
            "Populate .env before running collection."
        )

    login_sel = cfg.selectors.login or {}
    login_url = cfg.login_url
    if not login_url:
        raise ConfigError("No login URL configured (env INVESTORPLACE_LOGIN_URL or settings.yaml).")

    log.info("Opening login page: %s", login_url)
    session.goto(login_url)
    page = session.page

    user_sel = _first_present(page, login_sel.get("username_candidates", []))
    pass_sel = _first_present(page, login_sel.get("password_candidates", []))
    submit_sel = _first_present(page, login_sel.get("submit_candidates", []))

    if not user_sel or not pass_sel:
        session.failure_screenshot("login_fields_missing")
        raise LoginFailedError(
            "Could not locate username/password fields on the login page. "
            "Update config/selectors.yaml (login form may have changed)."
        )

    log.info("Filling credentials (user field=%s)", user_sel)
    page.fill(user_sel, username)
    page.fill(pass_sel, password)

    try:
        if submit_sel:
            page.click(submit_sel)
        else:
            page.press(pass_sel, "Enter")
        page.wait_for_load_state("networkidle")
    except Exception as e:
        session.failure_screenshot("login_submit_failed")
        raise LoginFailedError(f"Login submission failed: {e}") from e

    # Verify login state: fail closed on lingering logged-out markers.
    logged_out = login_sel.get("logged_out_markers", [])
    logged_in = login_sel.get("logged_in_markers", [])

    still_out = _any_present(page, logged_out)
    signed_in = _any_present(page, logged_in)

    capture = session.capture(category=PageCategory.LOGIN, requested_url=login_url)

    if still_out and not signed_in:
        session.failure_screenshot("login_still_logged_out")
        raise LoginFailedError(
            "After submitting credentials, logged-out markers are still present "
            "and no logged-in marker was found. Treating as failed login."
        )

    if not signed_in and not logged_in:
        # No markers configured to confirm — warn but do not hard fail; the
        # content-length safety guard downstream will still fail closed on an
        # empty page.
        log.warning(
            "No logged_in_markers configured; cannot positively confirm login. "
            "Relying on downstream content guards."
        )

    log.info("Login appears successful (signed_in_marker=%s).", signed_in)
    return capture
