"""Catalog behaviour: search, filters, sorting, pagination (and their seeded bugs)."""
from __future__ import annotations

import pytest

from tests.conftest import set_active_bugs


def api(client, **params):
    return client.get("/api/v1/products", params=params).json()


def test_pagination_math(client):
    result = api(client)
    assert result["total_items"] == 12
    assert result["total_pages"] == 2
    assert len(result["items"]) == 6


def test_search_full_catalog(client):
    result = api(client, q="monitor")
    slugs = [p["slug"] for p in result["items"]]
    assert set(slugs) == {"monitor-24-ips", "monitor-27-curvo"}


def test_bug_01_search_only_visible_page(client):
    set_active_bugs({"BUG-01"})
    # Monitors live on page 2; with BUG-01 the search sees only page 1.
    result = api(client, q="monitor")
    assert result["items"] == []
    assert result["total_items"] == 12  # counter still lies about the catalog


def test_sort_price_ascending(client):
    result = api(client, sort="precio")
    prices = [p["price"] for p in result["items"]]
    assert prices == sorted(prices)
    assert prices[0] == 12990


def test_bug_08_sort_price_as_string(client):
    set_active_bugs({"BUG-08"})
    result = api(client, sort="precio")
    prices = [p["price"] for p in result["items"]]
    assert prices != sorted(prices)


def test_category_filter(client):
    result = api(client, category="audio")
    assert {p["category"] for p in result["items"]} == {"audio"}


def test_bug_06_extra_empty_page(client):
    set_active_bugs({"BUG-06"})
    result = api(client, page=3)
    assert result["items"] == []
    assert result["page"] == 3


def test_no_empty_page_without_bug(client):
    result = api(client, page=3)
    assert result["total_pages"] == 2  # page 3 is not advertised...
    assert result["items"] == []       # ...and out-of-range is empty anyway


def test_htmx_search_returns_partial(client):
    resp = client.get("/productos", params={"q": "teclado"}, headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Teclado Mecanico K7" in resp.text
    assert "<!doctype" not in resp.text.lower()


def test_empty_search_message(client):
    resp = client.get("/productos", params={"q": "zzz"}, headers={"HX-Request": "true"})
    assert "Sin resultados" in resp.text
