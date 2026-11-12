"""Forms, auth, newsletter and lab panel (BUG-04, BUG-05, BUG-10)."""
from __future__ import annotations

QUOTE_OK = {
    "slug": "soporte-remoto",
    "nombre": "Luis Gomez",
    "email": "usuario+tag@dominio.com",  # valid RFC address with '+'
    "telefono": "3001234567",
    "presupuesto": "150000",
    "mensaje": "Necesito ayuda urgente",
}


def test_quote_accepts_plus_email(client):
    resp = client.post("/servicios/cotizar", data=QUOTE_OK)
    assert resp.status_code == 303
    code = resp.headers["location"].rsplit("/", 1)[-1]
    detail = client.get(f"/api/v1/quotes/{code}")
    assert detail.status_code == 200
    assert detail.json()["customer"]["email"] == QUOTE_OK["email"]


def test_bug_04_rejects_plus_email(client):
    from tests.conftest import set_active_bugs

    set_active_bugs({"BUG-04"})
    resp = client.post("/servicios/cotizar", data=QUOTE_OK)
    assert resp.status_code == 422
    assert "invalido" in resp.text


def test_quote_rejects_low_budget(client):
    bad = QUOTE_OK | {"presupuesto": "50000"}
    resp = client.post("/servicios/cotizar", data=bad)
    assert resp.status_code == 422
    assert "presupuesto" in resp.text


def test_quote_api_roundtrip(client):
    resp = client.post("/api/v1/quotes", json={
        "nombre": "Luis", "email": "luis@demo.com",
        "telefono": "3001234567", "presupuesto": "200000",
    })
    assert resp.status_code == 201
    code = resp.json()["code"]
    assert client.get(f"/api/v1/quotes/{code}").json()["status"] == "recibida"


def test_newsletter_persists(client):
    resp = client.post("/api/v1/newsletter", json={"email": "nuevo@demo.com"})
    assert resp.status_code == 201
    subs = client.get("/api/v1/newsletter/subscribers").json()
    assert subs["count"] == 1
    assert subs["items"][0]["email"] == "nuevo@demo.com"


def test_bug_05_newsletter_not_persisted(client):
    from tests.conftest import set_active_bugs

    set_active_bugs({"BUG-05"})
    resp = client.post("/api/v1/newsletter", json={"email": "nuevo@demo.com"})
    assert resp.status_code == 201  # pretends success...
    subs = client.get("/api/v1/newsletter/subscribers").json()
    assert subs["count"] == 0       # ...but nothing was saved


def test_register_login_me_logout(client):
    reg = client.post("/api/v1/auth/register", json={
        "nombre": "Test", "email": "test@demo.com", "password": "secret1",
    })
    assert reg.status_code == 201
    login = client.post("/api/v1/auth/login", json={
        "email": "test@demo.com", "password": "secret1",
    })
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").json()["email"] == "test@demo.com"
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_invalid_credentials(client):
    resp = client.post("/api/v1/auth/login", json={
        "email": "sofia@demo.com", "password": "wrong",
    })
    assert resp.status_code == 401


def test_cuenta_requires_auth(client):
    resp = client.get("/cuenta")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_bug_10_cuenta_renders_after_logout(client):
    from tests.conftest import set_active_bugs

    # Login via UI flow
    client.post("/login", data={"email": "sofia@demo.com", "password": "demo1234"})
    set_active_bugs({"BUG-10"})
    client.post("/logout")
    resp = client.get("/cuenta")
    assert resp.status_code == 200
    assert "invitado" in resp.text


def test_contact_form_validation_and_success(client):
    resp = client.post("/contacto", data={"nombre": "", "email": "", "mensaje": ""})
    assert resp.status_code == 422
    ok = client.post("/contacto", data={
        "nombre": "Ana", "email": "ana@demo.com", "mensaje": "Hola",
    })
    assert ok.status_code == 200
    assert "Mensaje enviado" in ok.text


def test_lab_toggle_and_profile(client):
    resp = client.post("/lab/bugs/BUG-02/toggle")
    assert resp.status_code == 303
    api_bugs = client.get("/api/v1/lab/bugs").json()
    bug_02 = next(b for b in api_bugs["bugs"] if b["id"] == "BUG-02")
    assert bug_02["active"] is False  # profile none: toggle marks it disabled

    client.post("/api/v1/lab/profile/default")
    api_bugs = client.get("/api/v1/lab/bugs").json()
    active = {b["id"] for b in api_bugs["bugs"] if b["active"]}
    assert "BUG-02" not in active     # it was explicitly disabled
    assert len(active) == 9           # the rest are on
