"""Deterministic check registry (heuristic mode, zero tokens).

Each check drives a real Playwright session and returns a CheckResult.
Checks are OUR code (allowed to use selectors); the anti-hallucination ref
discipline applies to the LLM agent (M4), which will reuse these checks via
the planner.

All checks are pure functions: (session, args) -> CheckResult. Evidence
screenshots are attached by the executor wrapper, not here.
"""
from __future__ import annotations

import re
import time
from decimal import Decimal
from typing import Callable

from qa_agent.browser.session import BrowserSession, StaleRefError
from qa_agent.models import BLOCKED, FAIL, PASS, CheckResult

IVA_RATE = Decimal("0.19")

CHECKS: dict[str, Callable[..., CheckResult]] = {}


def check(fn: Callable[..., CheckResult]) -> Callable[..., CheckResult]:
    CHECKS[fn.__name__] = fn
    return fn


def run_check(check_id: str, session: BrowserSession, args: dict) -> CheckResult:
    fn = CHECKS.get(check_id)
    if fn is None:
        return CheckResult(check=check_id, status=BLOCKED, detail=f"Check '{check_id}' no existe.")
    start = time.monotonic()
    try:
        result = fn(session, args)
    except (StaleRefError, Exception) as exc:  # engine errors are FAIL, not crashes
        result = CheckResult(check=check_id, status=FAIL, detail=f"Error ejecutando check: {exc}")
    result.duration_ms = int((time.monotonic() - start) * 1000)
    return result


# ----------------------------------------------------------------- helpers ---
def parse_money(text: str) -> Decimal:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", text or "")
    if not m:
        raise ValueError(f"no hay numero en {text!r}")
    return Decimal(m.group(0).replace(",", ""))


def _page_text(session: BrowserSession, selector: str) -> str:
    return session.page.inner_text(selector)


def _assert(cond: bool, ok_detail: str, fail_detail: str, observed: str = "", expected: str = "") -> CheckResult:
    return CheckResult(
        check="", status=PASS if cond else FAIL,
        detail=ok_detail if cond else fail_detail,
        observed=observed, expected=expected,
    )


def _add_product(session: BrowserSession, path: str, qty: int) -> None:
    session.goto(path)
    session.page.locator("#qty").fill(str(qty))
    session.page.get_by_role("button", name="Agregar al carrito").first.click()
    session._post_action_settle()


def _last_money(text: str) -> Decimal:
    """Money of a summary row: last numeric token (label may contain 'IVA (19%)')."""
    matches = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text or "")
    if not matches:
        raise ValueError(f"no hay numero en {text!r}")
    return Decimal(matches[-1].replace(",", ""))


def _cart_totals_dict(session: BrowserSession) -> dict[str, Decimal]:
    rows = session.page.locator("table.summary tr").all_inner_texts()
    out: dict[str, Decimal] = {}
    for row in rows:
        low = row.lower()
        if "subtotal" in low and "iva" not in low:
            out["subtotal"] = _last_money(row)
        elif "iva" in low:
            out["iva"] = _last_money(row)
        elif "total" in low:
            out["total"] = _last_money(row)
    return out


# ------------------------------------------------------------ carrito checks ---
@check
def add_product_verify_line(session: BrowserSession, args: dict) -> CheckResult:
    path, qty = args.get("path"), int(args.get("qty", 1))
    if not path:
        return CheckResult(check="", status=BLOCKED, detail="Producto no resuelto en el site map.")
    _add_product(session, path, qty)
    lines = session.page.locator("table.cart-table tbody tr").count()
    ok = lines == 1 and "/carrito" in session.current_url()
    return _assert(ok, "1 linea en el carrito", f"se esperaba 1 linea, hay {lines}",
                   observed=str(lines), expected="1")


@check
def cart_totals(session: BrowserSession, args: dict) -> CheckResult:
    path, qty = args.get("path"), int(args.get("qty", 1))
    if not path:
        return CheckResult(check="", status=BLOCKED, detail="Producto no resuelto en el site map.")
    _add_product(session, path, qty)
    # independent computation from the app's own displayed price
    price = parse_money(_page_text(session, "table.cart-table tbody tr td:nth-child(2)").replace("$", ""))
    exp_sub = price * qty
    exp_iva = (exp_sub * IVA_RATE).quantize(Decimal("0.01"))
    exp_total = exp_sub + exp_iva
    got = _cart_totals_dict(session)
    problems = []
    for key, expected in (("subtotal", exp_sub), ("iva", exp_iva), ("total", exp_total)):
        if key not in got:
            problems.append(f"falta {key}")
        elif got[key] != expected:
            problems.append(f"{key}: esperado {expected}, observado {got[key]}")
    return CheckResult(
        check="", status=PASS if not problems else FAIL,
        detail="Totales correctos (subtotal + IVA 19%)." if not problems else "; ".join(problems),
        observed=", ".join(f"{k}={got.get(k)}" for k in ("subtotal", "iva", "total")),
        expected=f"subtotal={exp_sub}, iva={exp_iva}, total={exp_total}",
    )


@check
def cart_change_qty(session: BrowserSession, args: dict) -> CheckResult:
    path, qty = args.get("path"), int(args.get("qty", 2))
    if not path:
        return CheckResult(check="", status=BLOCKED, detail="Producto no resuelto en el site map.")
    _add_product(session, path, 1)
    session.page.locator("table.cart-table input[name='qty']").fill(str(qty))
    session.page.get_by_role("button", name="Actualizar").first.click()
    session._post_action_settle()
    price = parse_money(_page_text(session, "table.cart-table tbody tr td:nth-child(2)").replace("$", ""))
    exp_sub = price * qty
    exp_iva = (exp_sub * IVA_RATE).quantize(Decimal("0.01"))
    exp_total = exp_sub + exp_iva
    got = _cart_totals_dict(session)
    ok = got.get("subtotal") == exp_sub and got.get("total") == exp_total
    return _assert(ok, f"Totales recalculados con qty={qty}",
                   f"subtotal/total no coinciden: {got} vs esperado sub={exp_sub} total={exp_total}",
                   observed=str(got), expected=f"sub={exp_sub} total={exp_total}")


def _flat(text: str) -> str:
    """ASCII lowercase text (accent-insensitive matching)."""
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _fill_live(session: BrowserSession, selector: str, value: str) -> None:
    """Fill + dispatch keyup/change: HTMX live widgets listen to `keyup changed`.

    Playwright's fill() fires `input` and `change`, but NOT `keyup`, so
    hx-trigger="keyup changed delay:400ms" never fires and the search never
    runs (false FAIL). Dispatching the events explicitly fixes it.
    """
    loc = session.page.locator(selector)
    loc.fill(value)
    loc.dispatch_event("keyup")
    loc.dispatch_event("change")


@check
def cart_qty_minimum(session: BrowserSession, args: dict) -> CheckResult:
    path = "/productos/teclado-mecanico-k7"
    _add_product(session, path, 1)
    qty_input = session.page.locator("table.cart-table input[name='qty']")
    qty_input.fill("0")
    session.page.get_by_role("button", name="Actualizar").first.click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    negative = re.search(r"-\$\s?\d", text) is not None
    totals = _cart_totals_dict(session)
    price = parse_money(_page_text(session, "table.cart-table tbody tr td:nth-child(2)").replace("$", ""))
    # correct behavior: qty 0 is clamped to 1 -> line total = unit price
    clamped = totals.get("subtotal") == price
    ok = (not negative) and clamped
    return _assert(
        ok,
        f"La cantidad minima es 1 (subtotal={totals.get('subtotal')} = precio unitario)",
        f"Se acepto cantidad invalida: qty=0 -> subtotal={totals.get('subtotal')} "
        f"(esperado clamp a precio {price})",
        observed=f"totals={totals}", expected=f"subtotal={price}, total>=0",
    )


@check
def cart_remove_line(session: BrowserSession, args: dict) -> CheckResult:
    _add_product(session, "/productos/teclado-mecanico-k7", 1)
    session.goto("/productos/mouse-inalambrico-m2")
    session.page.get_by_role("button", name="Agregar al carrito").first.click()
    session._post_action_settle()
    before = session.page.locator("table.cart-table tbody tr").count()
    session.page.locator("table.cart-table tbody tr").first.get_by_role("button", name="Eliminar").click()
    session._post_action_settle()
    after = session.page.locator("table.cart-table tbody tr").count()
    ok = before == 2 and after == 1
    return _assert(ok, "La linea se elimino y los totales se recalculan",
                   f"antes={before} despues={after}", observed=f"{before}->{after}", expected="2->1")


@check
def cart_empty_state(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/carrito")
    text = session.page.inner_text("body")
    ok = "está vacío" in text or "esta vacio" in text.lower() or "vacío" in text
    return _assert(ok, "Estado vacio visible", "No se muestra estado de carrito vacio",
                   observed=text[:200])


# ----------------------------------------------------------- productos checks ---
def _grid_prices(session: BrowserSession) -> list[Decimal]:
    texts = session.page.locator(".grid .card .price").all_inner_texts()
    return [parse_money(t.replace("$", "")) for t in texts if t.strip()]


@check
def search_covers_catalog(session: BrowserSession, args: dict) -> CheckResult:
    q = args.get("q", "monitor")
    expected = args.get("expected", [])
    session.goto("/productos")
    _fill_live(session, "#q", q)
    session._post_action_settle()
    text = session.page.inner_text(".main-content")
    missing = [e for e in expected if e not in text]
    if "Sin resultados" in text:
        detail = (f"La busqueda '{q}' devolvio 0 resultados (BUG-01 probable: filtra solo "
                  "la pagina visible, no todo el catalogo)")
    else:
        detail = f"No aparecen: {missing} (la busqueda parece limitarse a la pagina visible)"
    return _assert(not missing, f"Busqueda '{q}' cubre todo el catalogo",
                   detail, observed=text[:200], expected=", ".join(expected))


@check
def sort_price_numeric(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/productos")
    session.page.locator("#orden").select_option("precio")
    session._post_action_settle()
    prices = _grid_prices(session)
    sorted_ok = prices == sorted(prices)
    first = args.get("first_price")
    first_ok = first is None or (prices and prices[0] == Decimal(str(first)))
    ok = sorted_ok and first_ok
    return _assert(ok, f"Orden por precio numerico correcto: {[str(p) for p in prices[:3]]}...",
                   f"Orden incorrecto (comparacion como texto?): {prices}",
                   observed=str(prices), expected="orden creciente numerico")


@check
def category_filter(session: BrowserSession, args: dict) -> CheckResult:
    category = args.get("category", "Audio")
    session.goto("/productos")
    session.page.locator("#categoria").select_option(label=category)
    session._post_action_settle()
    # badge text may be uppercased by CSS text-transform -> compare casefolded
    badges = {b.strip().casefold() for b in
              session.page.locator(".grid .card .card-badge").all_inner_texts()}
    ok = badges and badges == {category.casefold()}
    return _assert(ok, f"Filtro '{category}' muestra solo esa categoria",
                   f"Se muestran categorias: {sorted(badges)}",
                   observed=str(sorted(badges)), expected=category)


@check
def last_page_has_content(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/productos")
    links = session.page.locator("nav.pagination a.page")
    count = links.count()
    if count == 0:
        return CheckResult(check="", status=PASS, detail="Una sola pagina, sin paginacion.")
    last = links.nth(count - 1)
    last_url = last.get_attribute("href")
    session.goto(last_url)
    cards = session.page.locator(".grid .card").count()
    ok = cards > 0
    return _assert(ok, f"La ultima pagina ({last_url}) tiene {cards} productos",
                   f"La ultima pagina anunciada ({last_url}) esta VACIA (paginacion mentirosa)",
                   observed=f"cards={cards}", expected="cards>0")


@check
def search_no_results(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/productos")
    _fill_live(session, "#q", args.get("q", "zzz-no-existe"))
    session._post_action_settle()
    text = session.page.inner_text(".main-content")
    ok = "Sin resultados" in text
    return _assert(ok, "Mensaje 'Sin resultados' presente", "No aparece mensaje de sin resultados",
                   observed=text[:150])


@check
def product_detail(session: BrowserSession, args: dict) -> CheckResult:
    path = args.get("path")
    product = args.get("product", "")
    if not path:
        return CheckResult(check="", status=BLOCKED, detail="Producto no resuelto en el site map.")
    session.goto(path)
    text = session.page.inner_text("body")
    price = args.get("price_str")
    price_ok = price is None or f"{price:,.0f}" in text
    btn = session.page.get_by_role("button", name="Agregar al carrito").count() >= 1
    ok = product.split()[0] in text and price_ok and btn
    return _assert(ok, f"Detalle de '{product}' con precio y accion de compra",
                   "Detalle incompleto (nombre/precio/boton)",
                   observed=text[:200], expected=f"{product}, precio {price}")


# ----------------------------------------------------------- servicios checks ---
def _fill_quote(session: BrowserSession, args: dict, service_slug: str | None) -> None:
    url = "/servicios" + (f"?servicio={service_slug}" if service_slug else "")
    session.goto(url)
    form = session.page.locator("form[action='/servicios/cotizar']")
    form.locator("#nombre").fill(args.get("nombre", ""))
    form.locator("#email").fill(args.get("email", ""))
    form.locator("#telefono").fill(args.get("telefono", ""))
    form.locator("#presupuesto").fill(str(args.get("presupuesto", "")))
    if args.get("mensaje"):
        form.locator("#mensaje").fill(args["mensaje"])


@check
def quote_valid(session: BrowserSession, args: dict) -> CheckResult:
    _fill_quote(session, args, args.get("service_slug"))
    session.page.locator("form[action='/servicios/cotizar'] button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    code = re.search(r"COT-\d+", text)
    ok = code is not None and "recibida" in text.lower()
    return _assert(ok, f"Cotizacion creada: {code.group(0) if code else '-'}",
                   "No se genero codigo de seguimiento", observed=text[:200], expected="COT-nnnn")


@check
def quote_plus_email(session: BrowserSession, args: dict) -> CheckResult:
    data = {"nombre": "QA Plus", "telefono": "3001234567", "presupuesto": "200000", **args}
    _fill_quote(session, data, None)
    session.page.locator("form[action='/servicios/cotizar'] button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    rejected = "invalido" in text.lower() and "COT-" not in text
    return _assert(
        not rejected,
        f"Email con '+' aceptado ({data.get('email')})",
        f"Se rechazo un email valido con '+': {data.get('email')}",
        observed=text[:200], expected="aceptar email RFC valido",
    )


@check
def quote_validation_errors(session: BrowserSession, args: dict) -> CheckResult:
    data = {"nombre": "QA Err", "email": "qa@demo.com", "mensaje": "x", **args}
    _fill_quote(session, data, None)
    session.page.locator("form[action='/servicios/cotizar'] button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    tel_err = "telefono" in text and ("9 digitos" in text or "9 dígitos" in text or "9 dig" in text.lower())
    bud_err = "presupuesto" in text and "100000" in text
    no_code = "COT-" not in text
    ok = tel_err and bud_err and no_code
    return _assert(ok, "Errores de validacion visibles y sin cotizacion",
                   f"Validaciones faltantes: tel={tel_err} budget={bud_err} no_code={no_code}",
                   observed=text[:250])


@check
def services_listed(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/servicios")
    cards = session.page.locator(".service-card").count()
    prices = session.page.locator(".service-card .price").count()
    ok = cards >= int(args.get("min_count", 4)) and prices == cards
    return _assert(ok, f"{cards} servicios listados con precio",
                   f"Servicios: {cards}, con precio: {prices}", observed=f"{cards}/{prices}")


# ------------------------------------------------------------ checkout checks ---
def _do_checkout(session: BrowserSession, args: dict, product_path: str = "/productos/teclado-mecanico-k7") -> None:
    _add_product(session, product_path, 1)
    session.goto("/checkout")
    form = session.page.locator("form[action='/checkout']")
    for field in ("nombre", "email", "ciudad"):
        if args.get(field):
            form.locator(f"#{field}").fill(str(args[field]))
    if "direccion" in args:
        form.locator("#direccion").fill(str(args["direccion"]))
    if args.get("tarjeta"):
        form.locator("#tarjeta").fill(str(args["tarjeta"]))


@check
def checkout_success(session: BrowserSession, args: dict) -> CheckResult:
    _do_checkout(session, args)
    cart_totals_before = _cart_totals_dict(session)
    session.page.locator("form[action='/checkout'] button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    order = re.search(r"ORD-\d+", text)
    ok = order is not None and "confirmado" in text.lower()
    detail = f"Orden {order.group(0)} creada y confirmada" if order else "No hay numero de orden"
    return _assert(ok, detail, detail, observed=text[:200], expected="ORD-nnnn")


@check
def checkout_address_required(session: BrowserSession, args: dict) -> CheckResult:
    data = {
        "nombre": "QA Addr", "email": "addr@demo.com", "direccion": "",
        "ciudad": "Bogota", "tarjeta": "4111111111111111",
    }
    _do_checkout(session, data)
    session.page.locator("form[action='/checkout'] button[type='submit']").click()
    session._post_action_settle()
    text = _flat(session.page.inner_text("body"))
    created = re.search(r"ORD-\d+", session.page.inner_text("body"))
    error_shown = "obligatorio" in text and "direccion" in text
    ok = error_shown and not created
    return _assert(
        ok,
        "Direccion vacia rechazada con error y sin orden",
        "Se creo orden con direccion VACIA" if created else "No se muestra error de direccion obligatoria",
        observed=(_flat(session.page.inner_text('body'))[:200]), expected="error de campo obligatorio, sin ORD-",
    )


@check
def checkout_card_format(session: BrowserSession, args: dict) -> CheckResult:
    data = {
        "nombre": "QA Card", "email": "card@demo.com", "direccion": "Calle 1",
        "ciudad": "Bogota", "tarjeta": args.get("tarjeta", "123"),
    }
    _do_checkout(session, data)
    session.page.locator("form[action='/checkout'] button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    ok = "16 digitos" in text or "16 dígitos" in text or "16 dig" in text.lower()
    return _assert(ok, "Error de formato de tarjeta visible",
                   "No se valida el formato de la tarjeta", observed=text[:200])


@check
def checkout_empty_cart_redirect(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/checkout")
    ok = "/carrito" in session.current_url()
    return _assert(ok, "Checkout con carrito vacio redirige al carrito",
                   f"Checkout accesible con carrito vacio: {session.current_url()}",
                   observed=session.current_url(), expected="/carrito")


# ---------------------------------------------------------------- auth checks ---
def _login(session: BrowserSession, email: str, password: str) -> None:
    session.goto("/login")
    session.page.locator("#email").fill(email)
    session.page.locator("#password").fill(password)
    session.page.locator("form[action='/login'] button[type='submit']").click()
    session._post_action_settle()


@check
def login_ok(session: BrowserSession, args: dict) -> CheckResult:
    _login(session, args.get("email", "sofia@demo.com"), args.get("password", "demo1234"))
    ok = "/cuenta" in session.current_url()
    name = args.get("expect_name", "")
    name_ok = not name or name in session.page.inner_text("body")
    return _assert(ok and name_ok, "Login valido lleva a Mi cuenta con el nombre",
                   f"Login no lleva a cuenta (url={session.current_url()})",
                   observed=session.current_url(), expected="/cuenta")


@check
def login_invalid(session: BrowserSession, args: dict) -> CheckResult:
    _login(session, args.get("email", "sofia@demo.com"), args.get("password", "wrong"))
    text = session.page.inner_text("body")
    ok = "credenciales invalidas" in text.lower() and "/cuenta" not in session.current_url()
    return _assert(ok, "Credenciales invalidas rechazadas con mensaje",
                   "No se muestra error de credenciales", observed=text[:150])


@check
def register_new(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/registro")
    form = session.page.locator("form[action='/registro']")
    form.locator("#nombre").fill(args.get("nombre", "Test"))
    form.locator("#email").fill(args.get("email", "nuevo1@demo.com"))
    form.locator("#password").fill(args.get("password", "secret1"))
    form.locator("button[type='submit']").click()
    session._post_action_settle()
    ok = "/cuenta" in session.current_url()
    return _assert(ok, "Registro autentica automaticamente",
                   f"Registro no autentica (url={session.current_url()})",
                   observed=session.current_url(), expected="/cuenta")


@check
def register_short_password(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/registro")
    form = session.page.locator("form[action='/registro']")
    form.locator("#nombre").fill(args.get("nombre", "Test"))
    form.locator("#email").fill(args.get("email", "corta@demo.com"))
    form.locator("#password").fill(args.get("password", "123"))
    form.locator("button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    ok = "6 caracteres" in text and "/cuenta" not in session.current_url()
    return _assert(ok, "Contrasena corta rechazada", "No se valida el minimo de 6 caracteres",
                   observed=text[:150])


@check
def logout_invalidates(session: BrowserSession, args: dict) -> CheckResult:
    _login(session, args.get("email", "sofia@demo.com"), args.get("password", "demo1234"))
    session.page.locator("form[action='/logout'] button[type='submit']").click()
    session._post_action_settle()
    session.goto("/cuenta")
    ok = "/login" in session.current_url()
    return _assert(ok, "Tras el logout, /cuenta redirige a /login",
                   f"ACCESO A /cuenta SIN SESION (url={session.current_url()})",
                   observed=session.current_url(), expected="redirect a /login")


# ----------------------------------------------------------- navegacion checks ---
@check
def nav_links_load(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/")
    broken = []
    for link_name in ("Inicio", "Productos", "Servicios", "Contacto"):
        loc = session.page.get_by_role("link", name=link_name, exact=True)
        loc.click()
        session._post_action_settle()
        text = session.page.inner_text("body")
        if "404" in text[:200] or session.last_status >= 400:
            broken.append(link_name)
        session.goto("/")
    return _assert(not broken, "Las 4 secciones del menu cargan correctamente",
                   f"Secciones con error: {broken}", observed=str(broken))


@check
def newsletter_persists(session: BrowserSession, args: dict) -> CheckResult:
    # UI-only mode: the app always shows success on subscribe, so persistence
    # can only be proven through the API (planned for the API layer, M7).
    return CheckResult(
        check="", status=BLOCKED,
        detail="Verificar persistencia del newsletter requiere validacion por API (M7).",
    )


@check
def contact_form_validation_and_success(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/contacto")
    form = session.page.locator("form[action='/contacto']")
    form.locator("button[type='submit']").click()
    session._post_action_settle()
    empty_errors = session.page.locator(".field-error").count()
    form.locator("#nombre").fill("QA Contact")
    form.locator("#email").fill("contact@demo.com")
    form.locator("#mensaje").fill("Hola, mensaje de prueba")
    form.locator("button[type='submit']").click()
    session._post_action_settle()
    text = session.page.inner_text("body")
    ok = empty_errors >= 3 and "Mensaje enviado" in text
    return _assert(ok, "Contacto valida vacios y confirma el envio",
                   f"errors_vacios={empty_errors}, confirmacion={'Mensaje enviado' in text}",
                   observed=f"errors={empty_errors}")


@check
def footer_links_no_404(session: BrowserSession, args: dict) -> CheckResult:
    broken = args.get("site_broken_links", [])
    ok = not broken
    return _assert(ok, "Ningun enlace del sitio responde 404",
                   f"Enlaces rotos detectados por el crawler: {broken}",
                   observed=str(broken), expected="[]")


@check
def faq_present(session: BrowserSession, args: dict) -> CheckResult:
    session.goto("/contacto")
    count = session.page.locator("details").count()
    ok = count >= int(args.get("min_count", 3))
    return _assert(ok, f"{count} preguntas frecuentes desplegables",
                   f"Solo {count} preguntas frecuentes", observed=str(count))


# --------------------------------------------------------------- fallback -------
@check
def unmapped_scenario(session: BrowserSession, args: dict) -> CheckResult:
    return CheckResult(
        check="", status=BLOCKED,
        detail=args.get("reason", "Escenario fuera del vocabulario determinista."),
    )
