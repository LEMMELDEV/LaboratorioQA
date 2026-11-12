"""HTML screens (Jinja2 templates). Session cart lives in request.session."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import data
from app.defects import DEFECTS, lab_state

router = APIRouter()
_TEMPLATES_DIR = str(Path(__file__).resolve().parents[1] / "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def money(value) -> str:
    """Format a money value with 2 decimals, US grouping: 164184.3 -> '164,184.30'."""
    from decimal import Decimal

    return "{:,.2f}".format(Decimal(str(value)))


def money0(value) -> str:
    """Format an integer amount with thousands grouping: 45990 -> '45,990'."""
    return "{:,.0f}".format(value)


templates.env.filters["money"] = money
templates.env.filters["money0"] = money0


def ctx(request: Request, **extra: Any) -> dict[str, Any]:
    """Base template context shared by every screen."""
    session = request.session
    cart: dict[str, int] = session.get("cart", {})
    flash = session.pop("flash", None)
    context: dict[str, Any] = {
        "request": request,
        "user": session.get("user"),
        "cart_count": sum(max(qty, 1) for qty in cart.values()),
        "categories": data.CATEGORIES,
        "flash": flash,
        "bugs": lab_state.active_ids(),
    }
    context.update(extra)
    return context


def render(request: Request, template: str, **extra: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, template, ctx(request, **extra))


def render_404(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "404.html", ctx(request), status_code=404)


def flash_and_redirect(request: Request, url: str, message: str, category: str = "ok") -> RedirectResponse:
    request.session["flash"] = {"category": category, "message": message}
    return RedirectResponse(url, status_code=303)


def current_bugs(request: Request) -> set[str]:
    return lab_state.active_ids()


# ------------------------------------------------------------------- home ---
@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    featured = data.PRODUCTS[:3]
    return render(request, "index.html", featured=featured)


@router.post("/newsletter")
def newsletter(request: Request, email: str = Form("")):
    # BUG-05: pretend success but never persist.
    if "BUG-05" in current_bugs(request):
        return flash_and_redirect(request, "/", "¡Gracias por suscribirte!")
    if not data.NEWSLETTER:
        pass  # store exists; keep behaviour explicit below
    from app.validators import email_error

    error = email_error(email, bugs=current_bugs(request))
    if error:
        return flash_and_redirect(request, "/", error, category="error")
    data.NEWSLETTER.append({"email": email.strip().lower()})
    return flash_and_redirect(request, "/", "¡Gracias por suscribirte!")


# -------------------------------------------------------------- productos ---
@router.get("/productos", response_class=HTMLResponse)
def productos(
    request: Request,
    q: str = "",
    categoria: str = "",
    orden: str = "",
    pagina: int = 1,
):
    result = data.query_products(
        q, categoria, orden, pagina, bugs=current_bugs(request)
    )
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request, "partials/grid.html", ctx(request, result=result, q=q)
        )
    return render(
        request,
        "productos.html",
        result=result,
        q=q,
        categoria=categoria,
        orden=orden,
    )


@router.get("/productos/{slug}", response_class=HTMLResponse)
def producto(request: Request, slug: str):
    product = data.get_product(slug)
    if not product:
        return render_404(request)
    related = [p for p in data.PRODUCTS if p["category"] == product["category"] and p["slug"] != slug][:3]
    return render(request, "producto.html", product=product, related=related)


# --------------------------------------------------------------- servicios ---
@router.get("/servicios", response_class=HTMLResponse)
def servicios(request: Request, servicio: str = ""):
    return render(
        request,
        "servicios.html",
        services=data.SERVICES,
        quote_form={},
        quote_errors={},
        servicio=servicio,
    )


@router.post("/servicios/cotizar")
async def cotizar(request: Request):
    form = dict(await request.form())
    slug = form.get("slug", "")
    service = next((s for s in data.SERVICES if s["slug"] == slug), None)
    if not service:
        return render_404(request)
    errors = data.validate_quote(form, bugs=current_bugs(request))
    if errors:
        return templates.TemplateResponse(
            request,
            "servicios.html",
            ctx(request, services=data.SERVICES, quote_form=form,
                quote_errors=errors, servicio=slug),
            status_code=422,
        )
    quote = data.create_quote(form, slug)
    return RedirectResponse(f"/servicios/cotizacion/{quote['code']}", status_code=303)


@router.get("/servicios/cotizacion/{code}", response_class=HTMLResponse)
def cotizacion(request: Request, code: str):
    quote = data.QUOTES.get(code)
    if not quote:
        return render_404(request)
    return render(request, "cotizacion.html", quote=quote)


# ----------------------------------------------------------------- carrito ---
@router.get("/carrito", response_class=HTMLResponse)
def carrito(request: Request):
    cart = request.session.get("cart", {})
    bugs = current_bugs(request)
    totals = data.cart_totals(cart, bugs=bugs)
    lines = data.cart_lines(cart, bugs=bugs)
    return render(request, "carrito.html", lines=lines, totals=totals)


def _cart_session(request: Request) -> dict[str, int]:
    return request.session.setdefault("cart", {})


@router.post("/carrito/agregar")
async def carrito_agregar(request: Request):
    form = dict(await request.form())
    slug = form.get("slug", "")
    try:
        qty = int(form.get("qty", "1"))
    except ValueError:
        qty = 1
    if not data.get_product(slug):
        return render_404(request)
    cart = _cart_session(request)
    # BUG-03: no clamping -> 0 / negatives accepted.
    if "BUG-03" not in current_bugs(request):
        qty = max(1, qty)
    cart[slug] = cart.get(slug, 0) + qty
    request.session["cart"] = cart  # reassign: nested mutation is not detected by SessionMiddleware
    return flash_and_redirect(request, "/carrito", f"Agregado: {data.get_product(slug)['name']}")


@router.post("/carrito/actualizar")
async def carrito_actualizar(request: Request):
    form = dict(await request.form())
    slug, raw_qty = form.get("slug", ""), form.get("qty", "1")
    try:
        qty = int(raw_qty)
    except ValueError:
        qty = 1
    cart = _cart_session(request)
    if slug in cart:
        # BUG-03: 0 and negatives are kept as-is.
        if "BUG-03" in current_bugs(request):
            cart[slug] = qty
        else:
            cart[slug] = max(1, qty)
        request.session["cart"] = cart  # reassign so the session cookie is refreshed
    return RedirectResponse("/carrito", status_code=303)


@router.post("/carrito/eliminar")
async def carrito_eliminar(request: Request):
    form = dict(await request.form())
    slug = form.get("slug", "")
    cart = _cart_session(request)
    cart.pop(slug, None)
    request.session["cart"] = cart  # reassign so the session cookie is refreshed
    return RedirectResponse("/carrito", status_code=303)


# ---------------------------------------------------------------- checkout ---
@router.get("/checkout", response_class=HTMLResponse)
def checkout_get(request: Request):
    cart = request.session.get("cart", {})
    if not cart:
        return RedirectResponse("/carrito", status_code=303)
    totals = data.cart_totals(cart, bugs=current_bugs(request))
    return render(request, "checkout.html", totals=totals, form={}, errors={})


@router.post("/checkout")
async def checkout_post(request: Request):
    cart = request.session.get("cart", {})
    if not cart:
        return RedirectResponse("/carrito", status_code=303)
    form = dict(await request.form())
    errors = data.validate_checkout(form, bugs=current_bugs(request))
    if errors:
        totals = data.cart_totals(cart, bugs=current_bugs(request))
        return templates.TemplateResponse(
            request, "checkout.html", ctx(request, totals=totals, form=form, errors=errors),
            status_code=422,
        )
    order = data.create_order(form, cart, bugs=current_bugs(request))
    request.session["cart"] = {}
    return RedirectResponse(f"/checkout/confirmado/{order['id']}", status_code=303)


@router.get("/checkout/confirmado/{order_id}", response_class=HTMLResponse)
def checkout_ok(request: Request, order_id: str):
    order = data.ORDERS.get(order_id)
    if not order:
        return render_404(request)
    return render(request, "checkout_ok.html", order=order)


# -------------------------------------------------------------------- auth ---
@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/cuenta", status_code=303)
    return render(request, "login.html", form={}, error=None)


@router.post("/login")
async def login_post(request: Request):
    form = dict(await request.form())
    user = data.authenticate(form.get("email", ""), form.get("password", ""))
    if not user:
        return templates.TemplateResponse(
            request, "login.html", ctx(request, form=form, error="Credenciales invalidas."),
            status_code=401,
        )
    request.session["user"] = {"email": user["email"], "name": user["name"]}
    return RedirectResponse("/cuenta", status_code=303)


@router.get("/registro", response_class=HTMLResponse)
def registro_get(request: Request):
    return render(request, "registro.html", form={}, errors={})


@router.post("/registro")
async def registro_post(request: Request):
    form = dict(await request.form())
    errors: dict[str, str] = {}
    if not form.get("nombre", "").strip():
        errors["nombre"] = "Este campo es obligatorio."
    if not form.get("email", "").strip():
        errors["email"] = "Este campo es obligatorio."
    if len(form.get("password", "")) < 6:
        errors["password"] = "La contrasena debe tener al menos 6 caracteres."
    if not errors:
        error = data.register_user(form.get("email", ""), form.get("nombre", ""), form.get("password", ""))
        if error:
            errors["email"] = error
    if errors:
        return templates.TemplateResponse(
            request, "registro.html", ctx(request, form=form, errors=errors), status_code=422
        )
    user = data.authenticate(form.get("email", ""), form.get("password", ""))
    request.session["user"] = {"email": user["email"], "name": user["name"]}
    return RedirectResponse("/cuenta", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse("/", status_code=303)


@router.get("/cuenta", response_class=HTMLResponse)
def cuenta(request: Request):
    user = request.session.get("user")
    # BUG-10: account screen renders even without an authenticated session.
    if not user and "BUG-10" not in current_bugs(request):
        return RedirectResponse("/login", status_code=303)
    my_orders = [
        o for o in data.ORDERS.values()
        if user and o["customer"]["email"] == user["email"]
    ]
    return render(request, "cuenta.html", user=user, orders=my_orders)


# ---------------------------------------------------------------- contacto ---
@router.get("/contacto", response_class=HTMLResponse)
def contacto_get(request: Request):
    return render(request, "contacto.html", form={}, errors={}, sent=False)


@router.post("/contacto")
async def contacto_post(request: Request):
    form = dict(await request.form())
    errors: dict[str, str] = {}
    for field_name in ("nombre", "email", "mensaje"):
        if not form.get(field_name, "").strip():
            errors[field_name] = "Este campo es obligatorio."
    if form.get("email") and "@" not in form["email"]:
        errors["email"] = "Email invalido."
    if errors:
        return templates.TemplateResponse(
            request, "contacto.html", ctx(request, form=form, errors=errors, sent=False),
            status_code=422,
        )
    return render(request, "contacto.html", form={}, errors={}, sent=True)


# ---------------------------------------------------------------------- lab ---
@router.get("/lab", response_class=HTMLResponse)
def lab(request: Request):
    from dataclasses import asdict

    active = lab_state.active_ids()
    defects = [asdict(d) for d in sorted(DEFECTS.values(), key=lambda d: d.id)]
    return render(request, "lab.html", defects=defects, active=active, profile=lab_state.profile)


@router.post("/lab/perfil")
async def lab_profile(request: Request):
    form = dict(await request.form())
    lab_state.set_profile(form.get("perfil", "none"))
    return RedirectResponse("/lab", status_code=303)


@router.post("/lab/bugs/{bug_id}/toggle")
def lab_toggle(request: Request, bug_id: str):
    lab_state.toggle(bug_id)
    return RedirectResponse("/lab", status_code=303)


# -------------------------------------------------------------- legal/404 ---
@router.get("/terminos", response_class=HTMLResponse)
def terminos(request: Request):
    # BUG-07: the footer link points here but the page "does not exist".
    if "BUG-07" in current_bugs(request):
        return render_404(request)
    return render(request, "terminos.html")
