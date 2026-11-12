"""REST API under /api/v1. Shares the same stores/rules as the HTML screens.

This is the surface the QA agent will later use for API-based validation.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import data
from app.defects import DEFECTS, lab_state

router = APIRouter(prefix="/api/v1")


class ProductFilters(BaseModel):
    q: str = ""
    category: str = ""
    sort: Literal["", "nombre", "precio", "rating"] = ""
    page: int = Field(1, ge=1)


class CartItem(BaseModel):
    slug: str
    qty: int = 1


class CartItemQty(BaseModel):
    qty: int


class CheckoutBody(BaseModel):
    nombre: str
    email: str
    direccion: str = ""
    ciudad: str = ""
    tarjeta: str = ""


class QuoteBody(BaseModel):
    nombre: str
    email: str
    telefono: str
    presupuesto: str
    mensaje: str = ""


class NewsletterBody(BaseModel):
    email: str


class RegisterBody(BaseModel):
    nombre: str
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


def _bugs() -> set[str]:
    return lab_state.active_ids()


# ---------------------------------------------------------------- products ---
@router.get("/products")
def list_products(q: str = "", category: str = "", sort: str = "", page: int = 1):
    result = data.query_products(q, category, sort, page, bugs=_bugs())
    return result


@router.get("/products/{slug}")
def get_product(slug: str):
    product = data.get_product(slug)
    if not product:
        return JSONResponse({"detail": "Producto no encontrado"}, status_code=404)
    return product


@router.get("/categories")
def categories():
    return data.CATEGORIES


# ---------------------------------------------------------------- services ---
@router.get("/services")
def list_services():
    return data.SERVICES


@router.post("/quotes", status_code=201)
def create_quote(body: QuoteBody):
    errors = data.validate_quote(body.model_dump(), bugs=_bugs())
    if errors:
        return JSONResponse({"detail": "Datos invalidos", "errors": errors}, status_code=422)
    # Default service when created via API (the UI picks one per screen).
    quote = data.create_quote(body.model_dump(), data.SERVICES[0]["slug"])
    return quote


@router.get("/quotes/{code}")
def get_quote(code: str):
    quote = data.QUOTES.get(code)
    if not quote:
        return JSONResponse({"detail": "Cotizacion no encontrada"}, status_code=404)
    return quote


# -------------------------------------------------------------------- cart ---
@router.get("/cart")
def get_cart(request: Request):
    cart = request.session.get("cart", {})
    bugs = _bugs()
    return {
        "items": data.cart_lines(cart, bugs=bugs),
        **data.cart_totals(cart, bugs=bugs),
    }


@router.post("/cart/items", status_code=201)
def add_cart_item(request: Request, body: CartItem):
    product = data.get_product(body.slug)
    if not product:
        return JSONResponse({"detail": "Producto no encontrado"}, status_code=404)
    qty = body.qty
    if "BUG-03" not in _bugs():
        qty = max(1, qty)
    cart = request.session.setdefault("cart", {})
    cart[body.slug] = cart.get(body.slug, 0) + qty
    request.session["cart"] = cart  # reassign so the session cookie is refreshed
    return data.cart_totals(cart, bugs=_bugs())


@router.patch("/cart/items/{slug}")
def update_cart_item(request: Request, slug: str, body: CartItemQty):
    cart = request.session.setdefault("cart", {})
    if slug not in cart:
        return JSONResponse({"detail": "Item no encontrado"}, status_code=404)
    qty = body.qty
    if "BUG-03" not in _bugs():
        qty = max(1, qty)
    cart[slug] = qty
    request.session["cart"] = cart  # reassign so the session cookie is refreshed
    return data.cart_totals(cart, bugs=_bugs())


@router.delete("/cart/items/{slug}")
def delete_cart_item(request: Request, slug: str):
    cart = request.session.setdefault("cart", {})
    cart.pop(slug, None)
    request.session["cart"] = cart  # reassign so the session cookie is refreshed
    return data.cart_totals(cart, bugs=_bugs())


# ------------------------------------------------------------------ orders ---
@router.post("/orders", status_code=201)
def create_order(request: Request, body: CheckoutBody):
    cart = request.session.get("cart", {})
    if not cart:
        return JSONResponse({"detail": "El carrito esta vacio"}, status_code=409)
    form = body.model_dump()
    errors = data.validate_checkout(form, bugs=_bugs())
    if errors:
        return JSONResponse({"detail": "Datos invalidos", "errors": errors}, status_code=422)
    order = data.create_order(form, cart, bugs=_bugs())
    request.session["cart"] = {}
    return order


@router.get("/orders/{order_id}")
def get_order(order_id: str):
    order = data.ORDERS.get(order_id)
    if not order:
        return JSONResponse({"detail": "Orden no encontrada"}, status_code=404)
    return order


# -------------------------------------------------------------------- auth ---
@router.post("/auth/register", status_code=201)
def register(body: RegisterBody):
    error = data.register_user(body.email, body.nombre, body.password)
    if error:
        return JSONResponse({"detail": error}, status_code=422)
    return {"email": body.email.strip().lower(), "name": body.nombre}


@router.post("/auth/login")
def login(request: Request, body: LoginBody):
    user = data.authenticate(body.email, body.password)
    if not user:
        return JSONResponse({"detail": "Credenciales invalidas"}, status_code=401)
    request.session["user"] = {"email": user["email"], "name": user["name"]}
    return {"email": user["email"], "name": user["name"]}


@router.post("/auth/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    user = request.session.get("user")
    # BUG-10: /auth/me keeps returning the session user after logout? No:
    # the session is popped. The buggy screen is the HTML /cuenta.
    if not user:
        return JSONResponse({"detail": "No autenticado"}, status_code=401)
    return user


# --------------------------------------------------------------- newsletter ---
@router.post("/newsletter", status_code=201)
def newsletter(body: NewsletterBody):
    if "BUG-05" in _bugs():
        # BUG-05: respond 201 but drop the subscription.
        return {"status": "suscrito", "email": body.email}
    data.NEWSLETTER.append({"email": body.email.strip().lower()})
    return {"status": "suscrito", "email": body.email.strip().lower()}


@router.get("/newsletter/subscribers")
def subscribers():
    return {"count": len(data.NEWSLETTER), "items": data.NEWSLETTER}


# ---------------------------------------------------------------------- lab ---
@router.get("/lab/bugs")
def lab_bugs():
    active = lab_state.active_ids()
    return {
        "profile": lab_state.profile,
        "disabled": sorted(lab_state.disabled),
        "bugs": [d.__dict__ | {"active": d.id in active} for d in DEFECTS.values()],
    }


@router.post("/lab/bugs/{bug_id}/toggle")
def lab_toggle(bug_id: str):
    if bug_id not in DEFECTS:
        return JSONResponse({"detail": "Bug desconocido"}, status_code=404)
    now_active = lab_state.toggle(bug_id)
    return {"bug_id": bug_id, "active": now_active}


@router.post("/lab/profile/{profile}")
def lab_profile(profile: str):
    try:
        lab_state.set_profile(profile)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    return {"profile": lab_state.profile, "active": sorted(lab_state.active_ids())}
