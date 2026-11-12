"""Catalog, users, orders and in-memory stores for TiendaDemo.

Money: prices are integer COP. Cart math uses Decimal to avoid float noise.
Bug branches are marked with `BUG-xx` comments and controlled via defects.is_active().
"""
from __future__ import annotations

import itertools
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

IVA_RATE = Decimal("0.19")
PER_PAGE = 6
QUOTE_SEQ = itertools.count(1001)
ORDER_SEQ = itertools.count(10001)


def money(value: Decimal) -> Decimal:
    """Correct business rule: round money to 2 decimals (half up)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------- catalog ---
PRODUCTS: list[dict[str, Any]] = [
    {"slug": "teclado-mecanico-k7", "name": "Teclado Mecanico K7", "price": 45990,
     "category": "teclados", "stock": 15, "rating": 4.6,
     "description": "Switches rojos, formato TKL, keycaps PBT doubleshot."},
    {"slug": "teclado-inalambrico-k3", "name": "Teclado Inalambrico K3", "price": 38990,
     "category": "teclados", "stock": 22, "rating": 4.3,
     "description": "Bluetooth y 2.4 GHz, perfil bajo, bateria de 3 meses."},
    {"slug": "mouse-inalambrico-m2", "name": "Mouse Inalambrico M2", "price": 28990,
     "category": "mouses", "stock": 40, "rating": 4.5,
     "description": "Sensor 12.000 DPI, silencioso, 70 horas de autonomia."},
    {"slug": "mouse-gamer-rgb-g5", "name": "Mouse Gamer RGB G5", "price": 39990,
     "category": "mouses", "stock": 33, "rating": 4.7,
     "description": "26.000 DPI, peso ajustable, iluminacion RGB por zona."},
    {"slug": "audifonos-pro-x", "name": "Audifonos Pro X", "price": 89990,
     "category": "audio", "stock": 18, "rating": 4.8,
     "description": "Cancelacion activa de ruido, 40 horas, multipunto."},
    {"slug": "microfono-usb-studio", "name": "Microfono USB Studio", "price": 74990,
     "category": "audio", "stock": 12, "rating": 4.4,
     "description": "Capsula de condensador, patron cardiode, monitoreo cero-latencia."},
    {"slug": "monitor-24-ips", "name": 'Monitor 24" IPS', "price": 189990,
     "category": "monitores", "stock": 9, "rating": 4.6,
     "description": "1080p 100 Hz, borde delgado, soporte ergonomico."},
    {"slug": "monitor-27-curvo", "name": 'Monitor 27" Curvo', "price": 289990,
     "category": "monitores", "stock": 6, "rating": 4.5,
     "description": "QHD 165 Hz, 1500R, FreeSync Premium."},
    {"slug": "webcam-hd-1080p", "name": "Webcam HD 1080p", "price": 59990,
     "category": "accesorios", "stock": 27, "rating": 4.2,
     "description": " autofocus, microfono dual, tapa de privacidad."},
    {"slug": "hub-usb-c-7-en-1", "name": "Hub USB-C 7 en 1", "price": 42990,
     "category": "accesorios", "stock": 31, "rating": 4.1,
     "description": "HDMI 4K, 2x USB 3.0, SD/microSD, PD 100W."},
    {"slug": "soporte-laptop-aluminio", "name": "Soporte Laptop Aluminio", "price": 34990,
     "category": "accesorios", "stock": 24, "rating": 4.7,
     "description": "Aluminio, 6 niveles de altura, laptops hasta 17\"."},
    {"slug": "pad-mouse-xl", "name": "Pad Mouse XL", "price": 12990,
     "category": "accesorios", "stock": 60, "rating": 4.9,
     "description": "90x40 cm, base antideslizante, superficie microtexturada."},
]

CATEGORIES: dict[str, str] = {
    "teclados": "Teclados",
    "mouses": "Mouses",
    "audio": "Audio",
    "monitores": "Monitores",
    "accesorios": "Accesorios",
}

SORT_FIELDS = {"nombre", "precio", "rating"}

# --------------------------------------------------------------- services ---
SERVICES: list[dict[str, Any]] = [
    {"slug": "instalacion-equipos", "name": "Instalacion de equipos", "price": 55000,
     "summary": "Instalacion y configuracion de tu setup completo en domicilio.",
     "includes": ["Visita tecnica", "Montaje de perifericos", "Pruebas finales"]},
    {"slug": "mantenimiento-preventivo", "name": "Mantenimiento preventivo", "price": 39000,
     "summary": "Limpieza interna y externa de tu PC o laptop cada 6 meses.",
     "includes": ["Limpieza de componentes", "Cambio de pasta termica", "Informe de estado"]},
    {"slug": "soporte-remoto", "name": "Soporte remoto", "price": 25000,
     "summary": "Resolucion de problemas por sesion remota, mismo dia.",
     "includes": ["Diagnostico", "Hasta 2 horas de sesion", "Garantia de 7 dias"]},
    {"slug": "backup-y-recuperacion", "name": "Backup y recuperacion", "price": 68000,
     "summary": "Copia de seguridad completa y plan de recuperacion de datos.",
     "includes": ["Backup total", "Plan de restauracion", "Capacitacion basica"]},
]

# ------------------------------------------------------------------ users ---
USERS: dict[str, dict[str, Any]] = {}  # key: email (lowercase)

DEFAULT_USER = {
    "email": "sofia@demo.com",
    "name": "Sofia Ramirez",
    "password": "demo1234",
}
USERS[DEFAULT_USER["email"]] = dict(DEFAULT_USER)

# ------------------------------------------------------------------ state ---
ORDERS: dict[str, dict[str, Any]] = {}   # key: order id
QUOTES: dict[str, dict[str, Any]] = {}   # key: quote code
NEWSLETTER: list[dict[str, Any]] = []    # {email, subscribed_at}


def get_product(slug: str) -> dict[str, Any] | None:
    return next((p for p in PRODUCTS if p["slug"] == slug), None)


# ------------------------------------------------------------- catalog ops ---
def query_products(
    q: str = "",
    category: str = "",
    sort: str = "",
    page: int = 1,
    *,
    bugs: set[str] = frozenset(),  # type: ignore[assignment]
) -> dict[str, Any]:
    """Filter + sort + paginate the catalog. Bug branches noted inline."""
    items = PRODUCTS

    if q:
        term = q.strip().lower()
        # BUG-01: search only applies to the current page slice (applied later).
        if "BUG-01" not in bugs:
            items = [p for p in items if term in p["name"].lower()]

    if category:
        items = [p for p in items if p["category"] == category]

    if sort == "nombre":
        items = sorted(items, key=lambda p: p["name"].lower())
    elif sort == "precio":
        if "BUG-08" in bugs:
            # BUG-08: compare prices as strings.
            items = sorted(items, key=lambda p: str(p["price"]))
        else:
            items = sorted(items, key=lambda p: p["price"])
    elif sort == "rating":
        items = sorted(items, key=lambda p: p["rating"], reverse=True)

    total = len(items)
    total_pages = max(1, -(-total // PER_PAGE))
    # BUG-06: advertise one extra, empty page.
    if "BUG-06" in bugs:
        total_pages += 1

    page = max(1, page)
    start = (page - 1) * PER_PAGE
    page_items = items[start:start + PER_PAGE]

    # BUG-01: filter AFTER slicing, so only visible-page items are searched.
    if q and "BUG-01" in bugs:
        term = q.strip().lower()
        page_items = [p for p in page_items if term in p["name"].lower()]

    return {
        "items": page_items,
        "page": page,
        "total_pages": total_pages,
        "total_items": total,
        "per_page": PER_PAGE,
    }


# ---------------------------------------------------------------- cart ops ---
def cart_lines(cart: dict[str, int], *, bugs: set[str] = frozenset()) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for slug, qty in cart.items():
        product = get_product(slug)
        if not product:
            continue
        # BUG-03: qty 0 / negatives are accepted instead of clamped to 1.
        if "BUG-03" not in bugs:
            qty = max(1, qty)
        lines.append({
            "slug": slug,
            "name": product["name"],
            "price": product["price"],
            "qty": qty,
            "line_total": product["price"] * qty,
        })
    return lines


def cart_totals(
    cart: dict[str, int], *, bugs: set[str] = frozenset()
) -> dict[str, Decimal]:
    """Business rule: total = subtotal + IVA 19%, rounded to 2 decimals."""
    lines = cart_lines(cart, bugs=bugs)
    subtotal = Decimal(sum(l["line_total"] for l in lines))

    effective = subtotal
    # BUG-02: undocumented 5% discount when a line has >= 3 units.
    if "BUG-02" in bugs and any(l["qty"] >= 3 for l in lines):
        effective = subtotal * Decimal("0.95")

    iva = money(effective * IVA_RATE)
    total = money(effective + iva)
    return {"subtotal": money(subtotal), "iva": iva, "total": total}


# --------------------------------------------------------------- checkout ---
def validate_checkout(form: dict[str, Any], *, bugs: set[str] = frozenset()) -> dict[str, str]:
    """Return field_name -> error message (empty dict = valid)."""
    errors: dict[str, str] = {}
    required = ["nombre", "email", "direccion", "ciudad", "tarjeta"]
    if "BUG-09" in bugs:
        required.remove("direccion")  # BUG-09: address becomes optional
    for field_name in required:
        if not str(form.get(field_name, "")).strip():
            errors[field_name] = "Este campo es obligatorio."
    email = str(form.get("email", "")).strip()
    if email and "@" not in email:
        errors["email"] = "Email invalido."
    card = str(form.get("tarjeta", "")).replace(" ", "")
    if card and (not card.isdigit() or len(card) != 16):
        errors["tarjeta"] = "La tarjeta debe tener 16 digitos."
    return errors


def create_order(form: dict[str, Any], cart: dict[str, int], *, bugs: set[str] = frozenset()) -> dict[str, Any]:
    totals = cart_totals(cart, bugs=bugs)
    order_id = f"ORD-{next(ORDER_SEQ)}"
    order = {
        "id": order_id,
        "customer": {
            "nombre": form.get("nombre", ""),
            "email": form.get("email", ""),
            "direccion": form.get("direccion", ""),
            "ciudad": form.get("ciudad", ""),
        },
        "items": cart_lines(cart, bugs=bugs),
        "subtotal": str(totals["subtotal"]),
        "iva": str(totals["iva"]),
        "total": str(totals["total"]),
        "status": "confirmada",
    }
    ORDERS[order_id] = order
    return order


# ------------------------------------------------------------------ quotes ---
def validate_quote(form: dict[str, Any], *, bugs: set[str] = frozenset()) -> dict[str, str]:
    from app.validators import email_error  # local import to avoid cycle

    errors: dict[str, str] = {}
    for field_name in ("nombre", "email", "telefono", "presupuesto"):
        if not str(form.get(field_name, "")).strip():
            errors[field_name] = "Este campo es obligatorio."
    email = str(form.get("email", "")).strip()
    if email and email_error(email, bugs=bugs):
        errors["email"] = email_error(email, bugs=bugs)
    phone = str(form.get("telefono", "")).strip()
    if phone and (not phone.isdigit() or len(phone) < 9):
        errors["telefono"] = "El telefono debe tener al menos 9 digitos."
    budget = str(form.get("presupuesto", "")).strip()
    if budget and (not budget.isdigit() or int(budget) < 100000):
        errors["presupuesto"] = "El presupuesto minimo es 100000."
    return errors


def create_quote(form: dict[str, Any], service_slug: str) -> dict[str, Any]:
    code = f"COT-{next(QUOTE_SEQ)}"
    service = next(s for s in SERVICES if s["slug"] == service_slug)
    quote = {
        "code": code,
        "service": service["name"],
        "customer": {
            "nombre": form.get("nombre", ""),
            "email": form.get("email", ""),
            "telefono": form.get("telefono", ""),
            "presupuesto": form.get("presupuesto", ""),
        },
        "message": form.get("mensaje", ""),
        "status": "recibida",
    }
    QUOTES[code] = quote
    return quote


# -------------------------------------------------------------------- auth ---
def register_user(email: str, name: str, password: str) -> str | None:
    """Return an error message, or None on success."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return "Email invalido."
    if email in USERS:
        return "El email ya esta registrado."
    if len(password) < 6:
        return "La contrasena debe tener al menos 6 caracteres."
    USERS[email] = {"email": email, "name": name or email.split("@")[0], "password": password}
    return None


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = USERS.get(email.strip().lower())
    if user and user["password"] == password:
        return user
    return None
