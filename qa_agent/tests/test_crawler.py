"""M2 acceptance: the deterministic crawler discovers the site without being given routes."""
from __future__ import annotations

from qa_agent.browser.crawler import crawl


def test_crawler_discovers_core_pages(base_url):
    sitemap = crawl(base_url, headless=True, max_depth=3)
    paths = sitemap.paths()

    for expected in ["/", "/productos", "/servicios", "/carrito", "/contacto",
                     "/login", "/registro", "/terminos"]:
        assert expected in paths, f"falta {expected} en {paths}"

    # Product detail pages discovered through links
    product_pages = [p for p in paths if p.startswith("/productos/") ]
    assert len(product_pages) >= 10, f"solo descubrio {len(product_pages)} productos"

    # Second page of pagination discovered through links
    assert any("pagina=2" in p for p in paths), "no descubrio la pagina 2 del catalogo"

    # API and lab are excluded
    assert not any(p.startswith("/api") for p in paths)
    assert "/lab" not in paths

    assert sitemap.stats["broken_links"] == 0


def test_crawler_detects_broken_footer_link(base_url, set_active_bugs):
    set_active_bugs({"BUG-07"})
    sitemap = crawl(base_url, headless=True)
    broken = [l.href for l in sitemap.broken_links]
    assert "/terminos" in broken
    # The page itself was visited and recorded its 404
    page = sitemap.find_page("/terminos")
    assert page is not None and page.status == 404


def test_crawler_records_forms_and_observations(base_url):
    sitemap = crawl(base_url, headless=True)

    contact = sitemap.find_page("/contacto")
    assert contact is not None
    assert any(f.form_id or f.action for f in contact.forms)
    fields = [fld.name for f in contact.forms for fld in f.fields]
    assert {"nombre", "email", "mensaje"}.issubset(set(fields))

    home = sitemap.find_page("/")
    assert home is not None
    # home has nav links and add-to-cart buttons
    assert any(l.href == "/productos" for l in home.links)
    assert any(e.role == "button" and "Agregar al carrito" in e.name for e in home.elements)

    productos = sitemap.find_page("/productos")
    assert productos is not None
    assert any(e.tag == "select" and e.options for e in productos.elements)


def test_crawler_stats_within_budget(base_url):
    sitemap = crawl(base_url, headless=True, max_pages=25, max_depth=2)
    assert sitemap.stats["pages_visited"] <= 25
    assert sitemap.stats["max_depth_reached"] <= 2
