"""Heuristic planner (zero-LLM mode).

Parses Gherkin criteria and compiles each scenario into a deterministic
TestCase whose checks belong to a controlled vocabulary (`qa_agent.checks`).

Scenarios outside the vocabulary are planned as BLOCKED "unmapped_scenario"
checks: they will need the LLM planner (M4) to be executed.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from gherkin.parser import Parser

from qa_agent.models import Scenario, TestCase
from qa_agent.narratives import build_interpretation


# ------------------------------------------------------------------ parse ---
def parse_feature(path: str | Path) -> dict:
    """Parse a .feature file (Gherkin, `# language: es`) into a requirement dict."""
    text = Path(path).read_text(encoding="utf-8")
    doc = Parser().parse(text)
    feature = doc["feature"]
    scenarios: list[dict] = []
    for child in feature.get("children", []):
        sc = child.get("scenario")
        if not sc:
            continue
        tags = [t["name"].lstrip("@") for t in sc.get("tags", [])]
        steps: list[str] = []
        for s in sc.get("steps", []):
            line = f"{s['keyword'].strip()} {s['text']}"
            arg = s.get("dataTable")
            if arg:
                for row in arg["rows"]:
                    cells = [c["value"] for c in row["cells"]]
                    line += "\n  | " + " | ".join(cells) + " |"
            steps.append(line)
        scenarios.append({
            "id": _criterion_id(tags, sc["name"]),
            "name": sc["name"],
            "feature": feature["name"],
            "tags": tags,
            "steps": steps,
        })
    return {
        "path": str(path),
        "feature": feature["name"],
        "scenarios": scenarios,
    }


def _criterion_id(tags: list[str], name: str) -> str:
    for t in tags:
        if t.startswith("criterio-"):
            return t
    # fallback: slugified scenario name
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return f"criterio-{slug}"


# ------------------------------------------------------------------ utils ---
def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode().lower().strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(text)).strip("-")


def _number_after(steps: list[str], *phrases: str) -> float | None:
    """Find the first number appearing right after any of the given phrases."""
    for step in steps:
        low = _norm(step)
        for phrase in phrases:
            p = _norm(phrase)
            if p in low:
                m = re.search(r"(\d[\d,]*\.?\d*)", low[low.index(p) + len(p):])
                if m:
                    return float(m.group(1).replace(",", ""))
    return None


def _find_product_slug(sitemap: dict, product_name: str) -> str | None:
    """Resolve a product name to its /productos/<slug> path via the site map."""
    from urllib.parse import urlsplit

    needle = _norm(product_name)
    for page in sitemap.get("pages", []):
        path = urlsplit(page["url"]).path
        if path.startswith("/productos/") and path != "/productos":
            h1 = _norm(page.get("h1", ""))
            title = _norm(page.get("title", ""))
            if needle and (needle in h1 or needle in title):
                return path
    return None


def _service_slug(sitemap: dict, service_name: str) -> str | None:
    for page in sitemap.get("pages", []):
        for link in page.get("links", []):
            href = link["href"]
            if href.startswith("/servicios?servicio="):
                slug = href.split("servicio=", 1)[1]
                if slug == slugify(service_name):
                    return slug
    return None


# ------------------------------------------------------------------ plan ----
def build_cases(requirement: dict, sitemap: dict) -> list[TestCase]:
    """Compile scenarios into deterministic TestCases (heuristic vocabulary)."""
    cases: list[TestCase] = []
    for sc_raw in requirement["scenarios"]:
        sc = Scenario(
            id=sc_raw["id"], name=sc_raw["name"], feature=sc_raw["feature"],
            tags=sc_raw.get("tags", []), steps=sc_raw.get("steps", []),
        )
        checks = _checks_for_scenario(sc, sitemap)
        case = TestCase(
            case_id=sc.id, scenario_id=sc.id, name=sc.name,
            feature=sc.feature, checks=checks,
        )
        # how the agent understood the criterion (shown at the HITL gate)
        case.interpretation = build_interpretation(case).to_dict()
        cases.append(case)
    return cases


def _checks_for_scenario(sc: Scenario, sitemap: dict) -> list[dict]:
    steps = sc.steps
    sid = sc.id

    # ---- carrito ----
    if sid == "criterio-cart-01":
        args = _product_args(sitemap, steps, default_product="Teclado Mecanico K7")
        return [{"check": "add_product_verify_line", "args": {**args, "qty": 1}}]

    if sid == "criterio-cart-02":
        args = _product_args(sitemap, steps, default_product="Teclado Mecanico K7")
        qty = _qty_from_steps(steps, default=3)
        return [{"check": "cart_totals", "args": {
            **args, "qty": qty,
            "expected_subtotal": _number_after(steps, "el subtotal debe ser"),
            "expected_iva": _number_after(steps, "el iva debe ser"),
            "expected_total": _number_after(steps, "el total debe ser"),
        }}]

    if sid == "criterio-cart-03":
        args = _product_args(sitemap, steps, default_product="Mouse Inalambrico M2")
        qty = _qty_from_steps(steps, default=2)
        return [{"check": "cart_change_qty", "args": {
            **args, "qty": qty,
            "expected_subtotal": _number_after(steps, "el subtotal debe ser"),
            "expected_total": _number_after(steps, "el total debe ser"),
        }}]

    if sid == "criterio-cart-04":
        return [{"check": "cart_qty_minimum", "args": {}}]
    if sid == "criterio-cart-05":
        return [{"check": "cart_remove_line", "args": {}}]
    if sid == "criterio-cart-06":
        return [{"check": "cart_empty_state", "args": {}}]

    # ---- productos ----
    if sid == "criterio-cat-01":
        return [{"check": "search_covers_catalog", "args": {
            "q": _quoted(steps, "busco") or "monitor",
            "expected": ["Monitor 24", "Monitor 27"],
        }}]
    if sid == "criterio-cat-02":
        return [{"check": "sort_price_numeric", "args": {
            "first_price": _number_after(steps, "el primer producto debe ser el mas barato"),
        }}]
    if sid == "criterio-cat-03":
        return [{"check": "category_filter", "args": {
            "category": _quoted(steps, "filtro la categoria") or "Audio",
        }}]
    if sid == "criterio-cat-04":
        return [{"check": "last_page_has_content", "args": {}}]
    if sid == "criterio-cat-05":
        return [{"check": "search_no_results", "args": {"q": "zzz-no-existe"}}]
    if sid == "criterio-cat-06":
        product = _quoted(steps, "el detalle del producto") or "Teclado Mecanico K7"
        slug_path = _find_product_slug(sitemap, product)
        return [{"check": "product_detail", "args": {
            "product": product, "path": slug_path,
            "price_str": _number_after(steps, "su precio"),
        }}]

    # ---- servicios ----
    if sid == "criterio-serv-01":
        service = _table_value(steps, "servicio") or "Soporte remoto"
        slug = _service_slug(sitemap, service)
        return [{"check": "quote_valid", "args": {
            "service_slug": slug,
            "nombre": _table_value(steps, "nombre") or "Luis Gomez",
            "email": _table_value(steps, "email") or "luis.gomez@dominio.com",
            "telefono": _table_value(steps, "telefono") or "3001234567",
            "presupuesto": _table_value(steps, "presupuesto") or "250000",
            "mensaje": _table_value(steps, "mensaje") or "",
        }}]
    if sid == "criterio-serv-02":
        return [{"check": "quote_plus_email", "args": {
            "email": _quoted(steps, "con el email") or "usuario+tag@dominio.com",
        }}]
    if sid == "criterio-serv-03":
        return [{"check": "quote_validation_errors", "args": {
            "telefono": _table_value(steps, "telefono") or "123",
            "presupuesto": _table_value(steps, "presupuesto") or "50000",
        }}]
    if sid == "criterio-serv-04":
        return [{"check": "services_listed", "args": {
            "min_count": _number_after(steps, "debo ver los") or 4,
        }}]

    # ---- checkout ----
    if sid == "criterio-chk-01":
        return [{"check": "checkout_success", "args": {
            "nombre": _table_value(steps, "nombre") or "Ana Torres",
            "email": _table_value(steps, "email") or "ana@demo.com",
            "direccion": _table_value(steps, "direccion") or "Calle 10 #25-30",
            "ciudad": _table_value(steps, "ciudad") or "Bogota",
            "tarjeta": _table_value(steps, "tarjeta") or "4111111111111111",
        }}]
    if sid == "criterio-chk-02":
        return [{"check": "checkout_address_required", "args": {}}]
    if sid == "criterio-chk-03":
        return [{"check": "checkout_card_format", "args": {
            "tarjeta": _table_value(steps, "tarjeta") or "123",
        }}]
    if sid == "criterio-chk-04":
        return [{"check": "checkout_empty_cart_redirect", "args": {}}]

    # ---- auth ----
    if sid == "criterio-auth-01":
        creds = _creds_from_steps(steps, "sofia@demo.com", "demo1234")
        return [{"check": "login_ok", "args": {**creds, "expect_name": "Sofia"}}]
    if sid == "criterio-auth-02":
        return [{"check": "login_invalid", "args": {"email": "sofia@demo.com", "password": "wrong"}}]
    if sid == "criterio-auth-03":
        return [{"check": "register_new", "args": {
            "nombre": "Test Runner", "email": "qa-runner+1@demo.com", "password": "secret1",
        }}]
    if sid == "criterio-auth-04":
        return [{"check": "register_short_password", "args": {
            "nombre": "Test", "email": "shortpw@demo.com", "password": "123",
        }}]
    if sid == "criterio-auth-05":
        return [{"check": "logout_invalidates", "args": {
            "email": "sofia@demo.com", "password": "demo1234",
        }}]

    # ---- navegacion ----
    if sid == "criterio-nav-01":
        return [{"check": "nav_links_load", "args": {}}]
    if sid == "criterio-nav-02":
        return [{"check": "newsletter_persists", "args": {
            "email": _quoted(steps, "con el email") or "nuevo@ejemplo.com",
        }}]
    if sid == "criterio-nav-03":
        return [{"check": "contact_form_validation_and_success", "args": {}}]
    if sid == "criterio-nav-04":
        return [{"check": "footer_links_no_404", "args": {"site_broken_links": _dedupe_broken(sitemap)}}]
    if sid == "criterio-nav-05":
        return [{"check": "faq_present", "args": {"min_count": 3}}]

    # ---- fuera del vocabulario heuristico ----
    return [{"check": "unmapped_scenario", "args": {
        "scenario_id": sid, "steps": steps,
        "reason": "Fuera del vocabulario determinista; requiere planner con LLM (M4).",
    }}]


def _dedupe_broken(sitemap: dict) -> list[dict]:
    seen: dict[str, dict] = {}
    for bl in sitemap.get("broken_links", []):
        if bl["href"] not in seen:
            seen[bl["href"]] = {"href": bl["href"], "status": bl.get("status")}
    return list(seen.values())


def _product_args(sitemap: dict, steps: list[str], default_product: str) -> dict:
    product = default_product
    for step in steps:
        m = re.search(r'producto\s+"([^"]+)"', step)
        if m:
            product = m.group(1)
            break
    slug_path = _find_product_slug(sitemap, product)
    return {"product": product, "path": slug_path}


def _qty_from_steps(steps: list[str], default: int) -> int:
    for step in steps:
        m = re.search(r"agregue\s+(\d+)\s+unidades", _norm(step)) or re.search(
            r"cambio la cantidad a (\d+)", _norm(step))
        if m:
            return int(m.group(1))
    return default


def _quoted(steps: list[str], after: str) -> str | None:
    for step in steps:
        if _norm(after) in _norm(step):
            m = re.search(r'"([^"]+)"', step)
            if m:
                return m.group(1)
    return None


def _table_value(steps: list[str], key: str) -> str | None:
    pattern = re.compile(rf"\|\s*{_norm(key)}\s*\|\s*([^|]+)\|", re.IGNORECASE)
    for step in steps:
        m = pattern.search(step)
        if m:
            return m.group(1).strip()
    # table rows live in the docstring-like block; search raw joined steps
    joined = "\n".join(steps)
    m = pattern.search(joined)
    return m.group(1).strip() if m else None


def _creds_from_steps(steps: list[str], d_email: str, d_password: str) -> dict:
    email, password = d_email, d_password
    for step in steps:
        m = re.search(r"([\w.+-]+@[\w.-]+)\s*/\s*(\S+)", step)
        if m:
            email, password = m.group(1), m.group(2)
    return {"email": email, "password": password}
