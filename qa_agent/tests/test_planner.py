"""Planner tests: Gherkin parsing + heuristic compilation (zero LLM)."""
from __future__ import annotations

from pathlib import Path

from qa_agent.planner import build_cases, parse_feature

FEATURES_DIR = Path(__file__).resolve().parents[2] / "requirements"

MINI_SITEMAP = {
    "base_url": "http://x",
    "pages": [
        {"url": "http://x/productos/teclado-mecanico-k7", "h1": "Teclado Mecanico K7",
         "title": "Teclado Mecanico K7 — TiendaDemo", "status": 200, "links": []},
        {"url": "http://x/productos/mouse-inalambrico-m2", "h1": "Mouse Inalambrico M2",
         "title": "Mouse Inalambrico M2 — TiendaDemo", "status": 200, "links": []},
        {"url": "http://x/servicios", "h1": "Servicios tecnicos", "title": "Servicios",
         "status": 200, "links": [{"href": "/servicios?servicio=soporte-remoto", "text": "Cotizar"}]},
    ],
    "broken_links": [],
}


def test_parse_carrito_feature():
    req = parse_feature(FEATURES_DIR / "carrito.feature")
    ids = [s["id"] for s in req["scenarios"]]
    assert ids == [f"criterio-cart-{i:02d}" for i in range(1, 7)]
    cart02 = next(s for s in req["scenarios"] if s["id"] == "criterio-cart-02")
    assert any("164184.30" in step for step in cart02["steps"])


def test_parse_tables_included():
    req = parse_feature(FEATURES_DIR / "checkout.feature")
    chk01 = next(s for s in req["scenarios"] if s["id"] == "criterio-chk-01")
    joined = "\n".join(chk01["steps"])
    assert "4111111111111111" in joined
    assert "Calle 10 #25-30" in joined


def test_build_cases_maps_known_vocabulary():
    req = parse_feature(FEATURES_DIR / "carrito.feature")
    cases = build_cases(req, MINI_SITEMAP)
    by_id = {c.case_id: c for c in cases}

    cart02 = by_id["criterio-cart-02"]
    assert cart02.checks[0]["check"] == "cart_totals"
    assert cart02.checks[0]["args"]["qty"] == 3
    assert cart02.checks[0]["args"]["expected_total"] == 164184.30
    assert cart02.checks[0]["args"]["path"] == "/productos/teclado-mecanico-k7"

    cart03 = by_id["criterio-cart-03"]
    assert cart03.checks[0]["args"]["path"] == "/productos/mouse-inalambrico-m2"
    assert cart03.checks[0]["args"]["expected_total"] == 69002.20


def test_build_cases_resolves_service_slug():
    req = parse_feature(FEATURES_DIR / "servicios.feature")
    cases = build_cases(req, MINI_SITEMAP)
    quote = next(c for c in cases if c.case_id == "criterio-serv-01")
    assert quote.checks[0]["args"]["service_slug"] == "soporte-remoto"


def test_unknown_scenario_maps_to_unmapped():
    req = parse_feature(FEATURES_DIR / "navegacion.feature")
    req["scenarios"].append({
        "id": "criterio-futuro-99", "name": "Criterio nuevo sin vocabulario",
        "feature": "X", "tags": [], "steps": ["Cuando algo nuevo"],
    })
    cases = build_cases(req, MINI_SITEMAP)
    future = next(c for c in cases if c.case_id == "criterio-futuro-99")
    assert future.checks[0]["check"] == "unmapped_scenario"


def test_all_feature_files_parse():
    total = 0
    for feature in sorted(FEATURES_DIR.glob("*.feature")):
        req = parse_feature(feature)
        total += len(req["scenarios"])
    assert total == 30
