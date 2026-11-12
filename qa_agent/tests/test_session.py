"""M2 acceptance: ref-based browser session (observe -> act -> observe)."""
from __future__ import annotations

import pytest

from qa_agent.browser.session import BrowserSession, StaleRefError


@pytest.fixture
def session(base_url):
    with BrowserSession(base_url=base_url, headless=True) as s:
        yield s


def _ref_for(session: BrowserSession, predicate) -> str:
    for el in session.observation.elements:
        if predicate(el):
            return el.ref
    raise AssertionError("elemento no encontrado en la observacion")


def test_observe_assigns_fresh_refs(session):
    obs = session.goto("/")
    assert obs.url.rstrip("/") == session.base_url
    assert obs.title
    assert obs.elements, "sin elementos interactivos"
    # refs are unique per snapshot state: s{seq}e{i}
    assert all(e.ref.startswith("s1e") for e in obs.elements)
    assert len({e.ref for e in obs.elements}) == len(obs.elements)
    # a second observation bumps the snapshot sequence
    obs2 = session.observe()
    assert all(e.ref.startswith("s2e") for e in obs2.elements)


def test_click_nav_link_discover_products(session):
    session.goto("/")
    ref = _ref_for(session, lambda e: e.role == "link" and e.name == "Productos")
    session.click(ref)
    assert "/productos" in session.current_url()
    obs = session.observation
    assert any("filtro" in (e.name or "").lower() or e.tag == "select" for e in obs.elements)


def test_htmx_live_search(session):
    session.goto("/productos")
    search_ref = _ref_for(session, lambda e: e.field_name == "q")
    session.fill(search_ref, "monitor")
    # After the HTMX swap, the grid only shows monitors.
    assert session.assert_text_visible("Monitor 24")
    obs = session.observe()
    names = [e.name for e in obs.elements if e.role == "link"]
    assert any("Monitor 27" in n for n in names)
    assert not any("Teclado" in n for n in names)


def test_add_to_cart_flow_with_refs(session):
    session.goto("/productos")
    btn = _ref_for(session, lambda e: e.role == "button" and e.name == "Agregar al carrito")
    session.click(btn)
    assert "/carrito" in session.current_url()
    assert session.assert_text_visible("45,990.00")   # line subtotal 1 x Teclado K7
    assert session.assert_text_visible("54,728.10")   # total with IVA


def test_stale_ref_fails_fast(session):
    obs = session.goto("/productos")
    ref = obs.elements[0].ref
    session.click(ref)  # navigation happened -> old refs are gone
    with pytest.raises(StaleRefError):
        session.click(ref)


def test_select_filter_via_ref(session):
    session.goto("/productos")
    cat_ref = _ref_for(session, lambda e: e.tag == "select" and "categoria" in (e.field_name or ""))
    session.select(cat_ref, "Audio")
    names = [e.name for e in session.observation.elements if e.role == "link"]
    assert any("Audifonos" in n for n in names)
    assert not any("Teclado" in n for n in names)
