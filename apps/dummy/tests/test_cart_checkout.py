"""Cart math, checkout rules and their seeded bugs (BUG-02, BUG-03, BUG-09)."""
from __future__ import annotations

TECLADO = "teclado-mecanico-k7"


def add_to_cart(client, slug: str, qty: int = 1):
    return client.post("/api/v1/cart/items", json={"slug": slug, "qty": qty})


def test_clean_cart_totals(client):
    add_to_cart(client, TECLADO, 3)
    totals = client.get("/api/v1/cart").json()
    assert float(totals["subtotal"]) == 137970.00
    assert float(totals["iva"]) == 26214.30
    assert float(totals["total"]) == 164184.30


def test_bug_02_ghost_discount(client):
    from tests.conftest import set_active_bugs

    set_active_bugs({"BUG-02"})
    add_to_cart(client, TECLADO, 3)
    totals = client.get("/api/v1/cart").json()
    # 5% undocumented discount applied -> total differs from the criterion.
    assert float(totals["total"]) == 155975.09
    assert float(totals["total"]) != 164184.30


def test_qty_clamped_to_minimum(client):
    add_to_cart(client, TECLADO, 0)
    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["qty"] == 1


def test_bug_03_accepts_zero_and_negative(client):
    from tests.conftest import set_active_bugs

    set_active_bugs({"BUG-03"})
    add_to_cart(client, TECLADO, 0)
    cart = client.get("/api/v1/cart").json()
    assert cart["items"][0]["qty"] == 0
    add_to_cart(client, "pad-mouse-xl", -2)
    cart = client.get("/api/v1/cart").json()
    qtys = {i["slug"]: i["qty"] for i in cart["items"]}
    assert qtys["pad-mouse-xl"] == -2


def test_clean_cart_totals_with_qty_one(client):
    add_to_cart(client, TECLADO, 1)
    totals = client.get("/api/v1/cart").json()
    assert float(totals["total"]) == 54728.10  # 45990 * 1.19


def test_checkout_requires_address(client):
    add_to_cart(client, TECLADO, 1)
    resp = client.post("/api/v1/orders", json={
        "nombre": "Ana", "email": "ana@demo.com", "direccion": "",
        "ciudad": "Bogota", "tarjeta": "4111111111111111",
    })
    assert resp.status_code == 422
    assert "direccion" in resp.json()["errors"]
    assert resp.json()["errors"]["direccion"]


def test_bug_09_checkout_accepts_empty_address(client):
    from tests.conftest import set_active_bugs

    set_active_bugs({"BUG-09"})
    add_to_cart(client, TECLADO, 1)
    resp = client.post("/api/v1/orders", json={
        "nombre": "Ana", "email": "ana@demo.com", "direccion": "",
        "ciudad": "Bogota", "tarjeta": "4111111111111111",
    })
    assert resp.status_code == 201
    assert resp.json()["customer"]["direccion"] == ""


def test_checkout_happy_path_and_order_persisted(client):
    add_to_cart(client, TECLADO, 2)
    resp = client.post("/api/v1/orders", json={
        "nombre": "Ana", "email": "ana@demo.com", "direccion": "Calle 1",
        "ciudad": "Bogota", "tarjeta": "4111111111111111",
    })
    assert resp.status_code == 201
    order = resp.json()
    assert order["status"] == "confirmada"
    fetched = client.get(f"/api/v1/orders/{order['id']}")
    assert fetched.status_code == 200
    # Cart is emptied after checkout
    assert client.get("/api/v1/cart").json()["items"] == []


def test_checkout_invalid_card(client):
    add_to_cart(client, TECLADO, 1)
    resp = client.post("/api/v1/orders", json={
        "nombre": "Ana", "email": "ana@demo.com", "direccion": "Calle 1",
        "ciudad": "Bogota", "tarjeta": "123",
    })
    assert resp.status_code == 422
    assert "tarjeta" in resp.json()["errors"]


def test_checkout_empty_cart_conflict(client):
    resp = client.post("/api/v1/orders", json={
        "nombre": "Ana", "email": "ana@demo.com", "direccion": "Calle 1",
        "ciudad": "Bogota", "tarjeta": "4111111111111111",
    })
    assert resp.status_code == 409


def test_cart_ui_shows_totals(client):
    add_to_cart(client, TECLADO, 3)
    resp = client.get("/carrito")
    assert "137,970.00" in resp.text
    assert "164,184.30" in resp.text
