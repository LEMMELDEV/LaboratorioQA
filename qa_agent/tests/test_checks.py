"""Check engine tests against the live app (heuristic mode, real Playwright)."""
from __future__ import annotations

import pytest

from qa_agent.browser.session import BrowserSession
from qa_agent.checks import run_check
from qa_agent.models import BLOCKED, FAIL, PASS


@pytest.fixture
def session(base_url):
    with BrowserSession(base_url=base_url, headless=True) as s:
        yield s


def test_cart_totals_pass_and_fail(base_url, set_active_bugs):
    args = {"path": "/productos/teclado-mecanico-k7", "qty": 3,
            "expected_total": 164184.30}

    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("cart_totals", s, args).status == PASS

    set_active_bugs({"BUG-02"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("cart_totals", s, args).status == FAIL


def test_qty_minimum_catches_bug_03(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("cart_qty_minimum", s, {}).status == PASS

    set_active_bugs({"BUG-03"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        result = run_check("cart_qty_minimum", s, {})
        assert result.status == FAIL


def test_sort_price_catches_bug_08(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("sort_price_numeric", s, {"first_price": 12990}).status == PASS

    set_active_bugs({"BUG-08"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("sort_price_numeric", s, {"first_price": 12990}).status == FAIL


def test_last_page_catches_bug_06(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("last_page_has_content", s, {}).status == PASS

    set_active_bugs({"BUG-06"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        result = run_check("last_page_has_content", s, {})
        assert result.status == FAIL
        assert "VACIA" in result.detail


def test_checkout_address_catches_bug_09(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("checkout_address_required", s, {}).status == PASS

    set_active_bugs({"BUG-09"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        result = run_check("checkout_address_required", s, {})
        assert result.status == FAIL


def test_logout_catches_bug_10(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("logout_invalidates", s, {
            "email": "sofia@demo.com", "password": "demo1234",
        }).status == PASS

    set_active_bugs({"BUG-10"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        result = run_check("logout_invalidates", s, {
            "email": "sofia@demo.com", "password": "demo1234",
        })
        assert result.status == FAIL


def test_plus_email_catches_bug_04(base_url, set_active_bugs):
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("quote_plus_email", s, {
            "email": "usuario+tag@dominio.com"}).status == PASS

    set_active_bugs({"BUG-04"})
    with BrowserSession(base_url=base_url, headless=True) as s:
        result = run_check("quote_plus_email", s, {"email": "usuario+tag@dominio.com"})
        assert result.status == FAIL


def test_search_fix_no_more_false_positives(base_url, set_active_bugs):
    """Regression: plain fill() never fired the HTMX 'keyup changed' trigger,
    so the search never ran and both search checks reported false FAILs."""
    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("search_covers_catalog", s, {
            "q": "monitor", "expected": ["Monitor 24", "Monitor 27"],
        }).status == PASS

    set_active_bugs(set())
    with BrowserSession(base_url=base_url, headless=True) as s:
        assert run_check("search_no_results", s, {"q": "zzz-no-existe"}).status == PASS


def test_newsletter_blocked_without_api_layer(session):
    result = run_check("newsletter_persists", session, {})
    assert result.status == BLOCKED
    assert "API" in result.detail


def test_unknown_check_is_blocked(session):
    result = run_check("no_existe", session, {})
    assert result.status == BLOCKED
