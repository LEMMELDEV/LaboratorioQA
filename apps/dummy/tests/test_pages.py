"""Smoke tests: every screen renders and navigation works."""
from __future__ import annotations

from tests.conftest import set_active_bugs

SCREENS = [
    ("/", "Tienda"),
    ("/productos", "Productos"),
    ("/servicios", "Servicios"),
    ("/carrito", "Carrito"),
    ("/contacto", "Contacto"),
    ("/login", "Ingresar"),
    ("/registro", "Crear cuenta"),
    ("/lab", "Defectos sembrados"),
]


def test_all_screens_render(client):
    for url, text in SCREENS:
        resp = client.get(url)
        assert resp.status_code == 200, f"{url} -> {resp.status_code}"
        assert text in resp.text


def test_home_shows_featured_and_newsletter(client):
    resp = client.get("/")
    assert "Teclado Mecanico K7" in resp.text
    assert "newsletter" in resp.text


def test_unknown_page_is_404(client):
    resp = client.get("/no-existe")
    assert resp.status_code == 404
    assert "404" in resp.text


def test_terminos_ok_without_bug(client):
    assert client.get("/terminos").status_code == 200


def test_terminos_broken_with_bug_07(client):
    set_active_bugs({"BUG-07"})
    assert client.get("/terminos").status_code == 404


def test_product_detail(client):
    resp = client.get("/productos/teclado-mecanico-k7")
    assert resp.status_code == 200
    assert "45,990" in resp.text


def test_product_detail_unknown_404(client):
    assert client.get("/productos/nope").status_code == 404


def test_footer_has_terms_link_and_lab_link(client):
    resp = client.get("/")
    assert '/terminos"' in resp.text
    assert "/lab" in resp.text
