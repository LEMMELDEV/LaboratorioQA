"""Playwright-backed browser session with ref-based actions.

The agent never touches CSS selectors: every action targets a `ref`
issued by the latest observation. Refs are invalidated on navigation or
re-observation, forcing the agent to look before it acts.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from qa_agent.browser.models import Element, PageObservation
from qa_agent.browser.pacing import human_pause
from qa_agent.browser.snapshot import SNAPSHOT_JS
from qa_agent.config import agent_settings


class StaleRefError(RuntimeError):
    """Raised when the agent tries to act on a ref that no longer exists."""


class BrowserSession:
    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        headless: Optional[bool] = None,
        timeout_ms: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or agent_settings.base_url).rstrip("/")
        self.headless = agent_settings.headless if headless is None else headless
        self.timeout_ms = agent_settings.per_action_timeout_ms if timeout_ms is None else timeout_ms
        self._pw = None
        self._browser = None
        self._context = None
        self.page: Optional[Page] = None
        self._observation: Optional[PageObservation] = None
        self._snap_seq = 0
        self.steps_taken = 0

    # ------------------------------------------------------------- lifecycle
    def start(self) -> "BrowserSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            base_url=self.base_url, viewport={"width": 1280, "height": 900}
        )
        self._context.set_default_timeout(self.timeout_ms)
        self.page = self._context.new_page()
        return self

    def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer:
                closer.close()
        if self._pw:
            self._pw.stop()

    def __enter__(self) -> "BrowserSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------ navigation
    def goto(self, url_or_path: str, *, wait: str = "load") -> PageObservation:
        assert self.page is not None
        url = self.absolute_url(url_or_path)
        response = self.page.goto(url, wait_until=wait)
        self._post_action_settle()
        human_pause("navigate")  # reading time before acting on a new screen
        self._last_status = response.status if response else 0
        return self.observe()

    @property
    def last_status(self) -> int:
        return getattr(self, "_last_status", 0)

    def back(self) -> PageObservation:
        assert self.page
        self.page.go_back()
        self._post_action_settle()
        return self.observe()

    def absolute_url(self, url_or_path: str) -> str:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            return url_or_path
        return urljoin(self.base_url + "/", url_or_path.lstrip("/"))

    def same_origin(self, url: str) -> bool:
        base = urlsplit(self.base_url)
        other = urlsplit(self.absolute_url(url))
        return (base.scheme, base.netloc) == (other.scheme, other.netloc)

    # ------------------------------------------------------------- observing
    def observe(self) -> PageObservation:
        assert self.page is not None
        self._snap_seq += 1
        raw = self.page.evaluate(SNAPSHOT_JS, f"s{self._snap_seq}e")
        self._observation = PageObservation.model_validate(raw)
        return self._observation

    @property
    def observation(self) -> PageObservation:
        if self._observation is None:
            return self.observe()
        return self._observation

    def current_url(self) -> str:
        assert self.page
        return self.page.url

    def title(self) -> str:
        assert self.page
        return self.page.title()

    # ---------------------------------------------------------------- actions
    def _locator(self, ref: str):
        assert self.page
        locator = self.page.locator(f'[data-qa-ref="{ref}"]')
        if locator.count() == 0:
            raise StaleRefError(
                f"Ref {ref!r} no longer exists. Observe the page again to get fresh refs."
            )
        return locator

    def _settle_after(self) -> None:
        self.steps_taken += 1
        self._post_action_settle()
        human_pause("action")  # human-like rhythm between steps

    def click(self, ref: str) -> PageObservation:
        loc = self._locator(ref)
        loc.click()
        self._settle_after()
        return self.observe()

    def fill(self, ref: str, text: str) -> PageObservation:
        loc = self._locator(ref)
        loc.fill(text)
        # HTMX live widgets (keyup/change triggers) need an explicit event.
        try:
            loc.dispatch_event("keyup")
            loc.dispatch_event("change")
        except Exception:
            pass
        self._settle_after()
        return self.observe()

    def select(self, ref: str, value: str) -> PageObservation:
        loc = self._locator(ref)
        try:
            loc.select_option(label=value)
        except Exception:
            loc.select_option(value=value)
        self._settle_after()
        return self.observe()

    def press(self, ref: str, key: str) -> PageObservation:
        self._locator(ref).press(key)
        self._settle_after()
        return self.observe()

    def toggle_checkbox(self, ref: str) -> PageObservation:
        self._locator(ref).check()
        self._settle_after()
        return self.observe()

    # ----------------------------------------------------------- assertions
    def assert_text_visible(self, text: str, timeout_ms: Optional[int] = None) -> bool:
        assert self.page
        timeout = timeout_ms or self.timeout_ms
        try:
            self.page.get_by_text(text, exact=False).first.wait_for(timeout=timeout)
            return True
        except PWTimeout:
            return False

    def assert_url_contains(self, fragment: str) -> bool:
        return fragment in self.current_url()

    # ------------------------------------------------------------- evidence
    def screenshot(self, name: str, artifacts_dir: Optional[Path] = None) -> Path:
        assert self.page
        out_dir = artifacts_dir or (agent_settings.artifacts_dir / "session")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    # ------------------------------------------------------------- internal
    def _post_action_settle(self) -> None:
        """Wait for navigation + HTMX fetches to finish (best effort).

        HTMX widgets fire with `delay:400ms` AFTER the event, so plain
        networkidle can return before the request even starts. We wait a
        fixed grace period, then re-check network idle and the settle
        classes htmx leaves while swapping.
        """
        assert self.page
        try:
            self.page.wait_for_load_state("load", timeout=self.timeout_ms)
        except PWTimeout:
            pass
        try:
            self.page.wait_for_timeout(450)  # covers htmx delay:400ms triggers
        except Exception:
            pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=3_000)
        except PWTimeout:
            pass
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('.htmx-settling, .htmx-added')",
                timeout=2_000,
            )
        except PWTimeout:
            pass


@contextmanager
def browser_session(**kwargs) -> Iterator[BrowserSession]:
    session = BrowserSession(**kwargs)
    try:
        session.start()
        yield session
    finally:
        session.close()
