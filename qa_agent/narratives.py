"""Heuristic narratives: turn a compiled TestCase into an Interpretation.

Each check id gets a builder that explains, in human terms, what will be
done and verified. This is the zero-LLM interpreter; M4's LLM planner will
fill the exact same Interpretation contract.
"""
from __future__ import annotations

from qa_agent.interpretation import (
    InterpAssertion,
    InterpStep,
    Interpretation,
)
from qa_agent.models import TestCase

STEP_NO = 0


def _n(action: str, target: str, detail: str = "") -> InterpStep:
    global STEP_NO
    STEP_NO += 1
    return InterpStep(order=STEP_NO, action=action, target=target, detail=detail)


def _base(case: TestCase) -> Interpretation:
    return Interpretation(
        criterion_id=case.case_id,
        criterion_name=case.name,
        understood_as="",
        confidence=0.85,
    )


def _money(v) -> str:
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


# ------------------------------------------------------------- builders ------
def _cart_ops(case: TestCase, args: dict, qty: int, product: str) -> tuple[Interpretation, list]:
    """Shared narrative for add-to-cart + totals checks."""
    interp = _base(case)
    path = args.get("path")
    interp.understood_as = (
        f"Agrego {qty} unidad(es) de '{product}' al carrito y espero que los totales "
        "se calculen correctamente (subtotal = precio × cantidad, IVA 19% incluido)."
    )
    steps = [
        _n("goto", f"la ficha del producto '{product}'", path or "ruta resuelta por discovery"),
        _n("fill", "el campo de cantidad", f"valor {qty}"),
        _n("click", "'Agregar al carrito'", "→ /carrito"),
    ]
    return interp, steps


def build_interpretation(case: TestCase) -> Interpretation:
    global STEP_NO
    STEP_NO = 0
    spec = case.checks[0] if case.checks else {}
    check, args = spec.get("check", ""), spec.get("args", {})

    if check == "unmapped_scenario":
        interp = _base(case)
        interp.confidence = 0.10
        interp.understood_as = (
            "No pude interpretar este criterio con el vocabulario determinista."
        )
        interp.unknowns = [args.get("reason", "requiere planner con LLM (M4)")]
        return interp

    if check in ("add_product_verify_line", "cart_totals"):
        product, qty = args.get("product", "el producto"), int(args.get("qty", 1))
        interp, steps = _cart_ops(case, args, qty, product)
        if check == "add_product_verify_line":
            interp.understood_as = (
                f"Agrego {qty} unidad(es) de '{product}' y espero ver exactamente "
                "1 línea nueva en el carrito."
            )
            interp.assertion = InterpAssertion(
                what="líneas en el carrito", expected="1",
                origin="criterio: debe aparecer el producto agregado",
            )
        else:
            exp = {k.replace("expected_", ""): args[k]
                   for k in ("expected_subtotal", "expected_iva", "expected_total")
                   if args.get(k) is not None}
            interp.assertion = InterpAssertion(
                what="subtotal / IVA / total del carrito",
                expected=", ".join(f"{k}={v:.2f}" for k, v in exp.items()) or "según fórmula",
                origin="valores literales del criterio" if exp else "fórmula del sitio (precio × qty + IVA 19%)",
                formula="total = precio_unitario × cantidad × 1.19 (IVA leído del carrito)",
            )
        interp.steps = steps
        interp.assumptions = [
            "IVA 19% según la etiqueta del sitio",
            "el precio unitario se lee de la línea del carrito, no del catálogo",
        ]
        return interp

    if check == "cart_change_qty":
        product, qty = args.get("product", "el producto"), int(args.get("qty", 2))
        interp = _base(case)
        interp.understood_as = (
            f"Cambio la cantidad de '{product}' a {qty} y espero que subtotal y total "
            "se recalculen."
        )
        interp.steps = [
            _n("goto", f"la ficha de '{product}'"),
            _n("click", "'Agregar al carrito'", "→ /carrito"),
            _n("fill", "el campo cantidad de la línea", f"valor {qty}"),
            _n("click", "'Actualizar'"),
        ]
        interp.assertion = InterpAssertion(
            what="subtotal y total recalculados",
            expected="según fórmula", origin="fórmula del sitio (precio × qty + IVA 19%)",
        )
        return interp

    if check == "cart_qty_minimum":
        interp = _base(case)
        interp.understood_as = (
            "Pongo la cantidad de una línea en 0 y espero que el sistema la rechace "
            "o la ajuste a 1, sin totales inválidos."
        )
        interp.steps = [
            _n("goto", "'/productos/teclado-mecanico-k7'"),
            _n("click", "'Agregar al carrito'", "→ /carrito"),
            _n("fill", "el campo cantidad de la línea", "valor 0"),
            _n("click", "'Actualizar'"),
        ]
        interp.assertion = InterpAssertion(
            what="comportamiento con cantidad 0",
            expected="cantidad mínima 1 y total >= 0",
            origin="criterio: no debe aceptar cantidades inválidas",
        )
        return interp

    if check == "cart_remove_line":
        interp = _base(case)
        interp.understood_as = (
            "Agrego dos productos, elimino uno y espero que la línea desaparezca "
            "y los totales se recalculen."
        )
        interp.steps = [
            _n("goto", "'/productos/teclado-mecanico-k7'"),
            _n("click", "'Agregar al carrito'"),
            _n("goto", "'/productos/mouse-inalambrico-m2'"),
            _n("click", "'Agregar al carrito'", "→ /carrito"),
            _n("click", "'Eliminar' en la primera línea"),
        ]
        interp.assertion = InterpAssertion(
            what="líneas del carrito", expected="2 → 1",
            origin="criterio: el producto eliminado no debe aparecer",
        )
        return interp

    if check == "cart_empty_state":
        interp = _base(case)
        interp.understood_as = "Abro el carrito sin productos y espero el estado vacío."
        interp.steps = [_n("goto", "'/carrito'")]
        interp.assertion = InterpAssertion(
            what="mensaje de carrito vacío", expected="texto 'está vacío'",
            origin="criterio", formula="",
        )
        return interp

    if check == "search_covers_catalog":
        q, expected = args.get("q", ""), args.get("expected", [])
        interp = _base(case)
        interp.understood_as = (
            f"Busco '{q}' en el catálogo y espero que aparezcan TODOS los productos "
            "que coinciden, no solo los de la página visible."
        )
        interp.steps = [
            _n("goto", "'/productos'"),
            _n("fill", "el buscador", f"valor '{q}'"),
        ]
        interp.assertion = InterpAssertion(
            what="productos en el resultado", expected=" y ".join(expected),
            origin="criterio: la búsqueda debe cubrir todo el catálogo",
        )
        return interp

    if check == "sort_price_numeric":
        interp = _base(case)
        interp.understood_as = (
            "Ordeno el catálogo por precio y espero un orden numérico creciente "
            "(el más barato primero)."
        )
        interp.steps = [_n("goto", "'/productos'"), _n("select", "el orden", "precio")]
        interp.assertion = InterpAssertion(
            what="primer producto del listado",
            expected=f"precio {_money(args.get('first_price'))}" if args.get("first_price") else "el más barato",
            origin="criterio: el más barato debe ir primero" + " (valor literal del criterio)" if args.get("first_price") else "criterio: el más barato debe ir primero",
            formula="los precios de las tarjetas deben quedar en orden creciente",
        )
        return interp

    if check == "category_filter":
        cat = args.get("category", "")
        interp = _base(case)
        interp.understood_as = f"Filtro por categoría '{cat}' y espero ver solo esa categoría."
        interp.steps = [_n("goto", "'/productos'"), _n("select", "la categoría", cat)]
        interp.assertion = InterpAssertion(
            what="categorías visibles", expected=cat,
            origin="criterio", formula="todas las tarjetas deben tener la etiqueta elegida",
        )
        return interp

    if check == "last_page_has_content":
        interp = _base(case)
        interp.understood_as = (
            "Voy a la última página de la paginación y espero encontrar productos, "
            "no una página vacía."
        )
        interp.steps = [_n("goto", "'/productos'"), _n("click", "el último enlace de paginación")]
        interp.assertion = InterpAssertion(
            what="contenido de la última página", expected="al menos 1 producto",
            origin="criterio: la última página no debe estar vacía",
        )
        return interp

    if check == "search_no_results":
        interp = _base(case)
        interp.understood_as = (
            f"Busco algo que no existe ('{args.get('q', '')}') y espero el mensaje "
            "'Sin resultados'."
        )
        interp.steps = [_n("goto", "'/productos'"), _n("fill", "el buscador", f"valor '{args.get('q', '')}'")]
        interp.assertion = InterpAssertion(
            what="mensaje de ausencia de resultados", expected="'Sin resultados'",
            origin="criterio",
        )
        return interp

    if check == "product_detail":
        interp = _base(case)
        product, price = args.get("product", ""), args.get("price_str")
        interp.understood_as = (
            f"Abro el detalle de '{product}' y espero ver su nombre, precio "
            f"{_money(price) if price else ''} y el botón de compra."
        )
        interp.steps = [_n("goto", f"el detalle de '{product}'", args.get("path") or "")]
        interp.assertion = InterpAssertion(
            what="nombre, precio y botón en el detalle",
            expected=f"precio {_money(price)}" if price else "precio visible",
            origin="criterio: los datos de la ficha deben coincidir con lo prometido",
        )
        return interp

    if check in ("quote_valid", "quote_plus_email", "quote_validation_errors"):
        interp = _base(case)
        if check == "quote_valid":
            interp.understood_as = (
                f"Completo la cotización del servicio con datos válidos "
                f"(nombre {args.get('nombre')}, email {args.get('email')}, "
                f"teléfono {args.get('telefono')}, presupuesto {args.get('presupuesto')}) "
                "y espero un código de seguimiento."
            )
            interp.assertion = InterpAssertion(
                what="confirmación de cotización", expected="código COT-nnnn",
                origin="criterio: debe generarse un código de seguimiento",
            )
        elif check == "quote_plus_email":
            interp.understood_as = (
                f"Envío la cotización con el email '{args.get('email')}' (formato "
                "con '+'). Un email RFC válido no debe ser rechazado."
            )
            interp.assertion = InterpAssertion(
                what="aceptación del email con '+'", expected="cotización creada",
                origin="criterio: emails con '+' son válidos",
            )
            interp.assumptions = ["'usuario+tag@dominio' es una dirección válida según RFC 5322"]
        else:
            interp.understood_as = (
                f"Envío la cotización con teléfono '{args.get('telefono')}' y "
                f"presupuesto '{args.get('presupuesto')}' inválidos; espero errores "
                "de validación y que NO se cree la cotización."
            )
            interp.assertion = InterpAssertion(
                what="errores de validación visibles y sin código COT",
                expected="mensajes de teléfono y presupuesto",
                origin="criterio: los errores deben bloquear la creación",
            )
        interp.steps = [
            _n("goto", "'/servicios'", "con el servicio preseleccionado si aplica"),
            _n("fill", "el formulario de cotización"),
            _n("submit", "el formulario"),
        ]
        return interp

    if check == "services_listed":
        interp = _base(case)
        interp.understood_as = (
            f"Abro /servicios y espero al menos {args.get('min_count', 4)} servicios "
            "cada uno con su precio."
        )
        interp.steps = [_n("goto", "'/servicios'")]
        interp.assertion = InterpAssertion(
            what="tarjetas de servicio con precio",
            expected=f">= {args.get('min_count', 4)}",
            origin="criterio",
        )
        return interp

    if check in ("checkout_success", "checkout_address_required", "checkout_card_format"):
        interp = _base(case)
        interp.steps = [
            _n("goto", "la ficha de un producto"),
            _n("click", "'Agregar al carrito'"),
            _n("goto", "'/checkout'"),
            _n("fill", "el formulario de envío y pago"),
            _n("submit", "el checkout"),
        ]
        if check == "checkout_success":
            interp.understood_as = (
                "Completo el checkout con datos válidos y espero un número de orden "
                "y la confirmación."
            )
            interp.assertion = InterpAssertion(
                what="confirmación de la compra", expected="código ORD-nnnn",
                origin="criterio: debe confirmarse la orden",
            )
        elif check == "checkout_address_required":
            interp.understood_as = (
                "Intento confirmar el pedido con la dirección VACÍA; espero un error "
                "de campo obligatorio y que no se cree la orden."
            )
            interp.assertion = InterpAssertion(
                what="rechazo de dirección vacía", expected="error y sin ORD-",
                origin="criterio: la dirección es obligatoria",
            )
        else:
            interp.understood_as = (
                f"Intento pagar con la tarjeta '{args.get('tarjeta')}' (formato "
                "inválido); espero un error de formato."
            )
            interp.assertion = InterpAssertion(
                what="validación de formato de tarjeta", expected="error de 16 dígitos",
                origin="criterio",
            )
        return interp

    if check == "checkout_empty_cart_redirect":
        interp = _base(case)
        interp.understood_as = "Abro /checkout con el carrito vacío; espero ser redirigido al carrito."
        interp.steps = [_n("goto", "'/checkout'")]
        interp.assertion = InterpAssertion(
            what="redirección", expected="/carrito", origin="criterio",
        )
        return interp

    if check in ("login_ok", "login_invalid", "logout_invalidates"):
        interp = _base(case)
        if check == "login_ok":
            interp.understood_as = (
                f"Inicio sesión con '{args.get('email')}' y espero entrar a Mi cuenta "
                "viendo mi nombre."
            )
            interp.assertion = InterpAssertion(
                what="pantalla tras el login", expected="/cuenta con el nombre",
                origin="criterio", formula="",
            )
            interp.steps = [
                _n("goto", "'/login'"), _n("fill", "email y contraseña"),
                _n("submit", "el formulario"),
            ]
        elif check == "login_invalid":
            interp.understood_as = (
                f"Intento entrar con contraseña incorrecta para '{args.get('email')}'; "
                "espero un mensaje de credenciales inválidas."
            )
            interp.assertion = InterpAssertion(
                what="rechazo de credenciales", expected="mensaje de error y sin sesión",
                origin="criterio", formula="",
            )
            interp.steps = [
                _n("goto", "'/login'"), _n("fill", "email y contraseña (errónea)"),
                _n("submit", "el formulario"),
            ]
        else:
            interp.understood_as = (
                "Cierro sesión y luego intento abrir /cuenta directamente; espero ser "
                "redirigido a /login."
            )
            interp.assertion = InterpAssertion(
                what="sesión invalidada tras logout", expected="redirect a /login",
                origin="criterio", formula="",
            )
            interp.steps = [
                _n("goto", "'/login'"), _n("fill", "credenciales válidas"),
                _n("submit", "el login"),
                _n("click", "'Cerrar sesión'"),
                _n("goto", "'/cuenta'"),
            ]
        return interp

    if check in ("register_new", "register_short_password"):
        interp = _base(case)
        if check == "register_new":
            interp.understood_as = (
                f"Registro la cuenta '{args.get('email')}' y espero quedar autenticado "
                "automáticamente en Mi cuenta."
            )
            interp.assertion = InterpAssertion(
                what="estado tras el registro", expected="/cuenta", origin="criterio",
            )
        else:
            interp.understood_as = (
                f"Intento registrar '{args.get('email')}' con contraseña "
                f"'{args.get('password')}' (muy corta); espero un error de mínimo 6 "
                "caracteres."
            )
            interp.assertion = InterpAssertion(
                what="validación de contraseña corta", expected="error y sin sesión",
                origin="criterio",
            )
        interp.steps = [
            _n("goto", "'/registro'"), _n("fill", "nombre, email y contraseña"),
            _n("submit", "el formulario"),
        ]
        return interp

    if check == "nav_links_load":
        interp = _base(case)
        interp.understood_as = (
            "Recorro las 4 secciones del menú (Inicio, Productos, Servicios, Contacto) "
            "y espero que todas carguen sin error."
        )
        interp.steps = [
            _n("goto", "'/'"),
            _n("click", "cada enlace del menú", "Inicio · Productos · Servicios · Contacto"),
        ]
        interp.assertion = InterpAssertion(
            what="carga de cada sección", expected="sin 404 ni error",
            origin="criterio",
        )
        return interp

    if check == "newsletter_persists":
        interp = _base(case)
        interp.understood_as = (
            f"Me suscribo con '{args.get('email')}' y verifico que el correo queda "
            "registrado de verdad (persistencia)."
        )
        interp.steps = [_n("goto", "el pie de página"), _n("fill", "el campo de newsletter")]
        interp.unknowns = [
            "la persistencia no es observable desde la UI (el sitio siempre confirma); "
            "se necesita la capa API (M7) para verificarlo"
        ]
        interp.confidence = 0.40
        return interp

    if check == "contact_form_validation_and_success":
        interp = _base(case)
        interp.understood_as = (
            "Envío el formulario de contacto vacío (espero errores de campos "
            "obligatorios) y luego completo con datos válidos (espero confirmación)."
        )
        interp.steps = [
            _n("goto", "'/contacto'"),
            _n("submit", "el formulario vacío"),
            _n("fill", "nombre, email y mensaje"),
            _n("submit", "el formulario"),
        ]
        interp.assertion = InterpAssertion(
            what="validación + confirmación", expected="errores vacíos y 'Mensaje enviado'",
            origin="criterio",
        )
        return interp

    if check == "footer_links_no_404":
        interp = _base(case)
        interp.understood_as = (
            "Verifico que ningún enlace del sitio (mapa descubierto por el crawler) "
            "responda 404."
        )
        interp.steps = [_n("assert", "todos los enlaces descubiertos", "usando el site map del crawler")]
        interp.assertion = InterpAssertion(
            what="enlaces rotos", expected="[]",
            origin="crawler de discovery (el agente los encontró solo)",
        )
        return interp

    if check == "faq_present":
        interp = _base(case)
        interp.understood_as = (
            f"Abro /contacto y espero al menos {args.get('min_count', 3)} preguntas "
            "frecuentes desplegables."
        )
        interp.steps = [_n("goto", "'/contacto'")]
        interp.assertion = InterpAssertion(
            what="elementos <details> de FAQ", expected=f">= {args.get('min_count', 3)}",
            origin="criterio",
        )
        return interp

    # fallback: check existe pero sin narrativa
    interp = _base(case)
    interp.understood_as = f"Ejecuto el check determinista '{check}'."
    interp.unknowns = ["sin narrativa específica para este check"]
    interp.confidence = 0.50
    return interp
