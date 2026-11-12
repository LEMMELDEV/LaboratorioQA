"""Pacing + interpretation tests."""
from __future__ import annotations

import os
import time

from qa_agent.browser.pacing import human_pause, pacing_enabled
from qa_agent.interpretation import Interpretation
from qa_agent.narratives import build_interpretation
from qa_agent.planner import build_cases, parse_feature
from qa_agent.tests.test_planner import FEATURES_DIR, MINI_SITEMAP


# ------------------------------------------------------------------ pacing ---
def test_pacing_on_and_timing():
    os.environ["AGENT_PACING"] = "on"
    os.environ["AGENT_STEP_DELAY_MS"] = "80"
    os.environ["AGENT_JITTER_MS"] = "20"
    try:
        assert pacing_enabled()
        start = time.monotonic()
        human_pause("action")
        elapsed = time.monotonic() - start
        # base 80ms + jitter 0..20ms
        assert 0.07 <= elapsed < 0.30, elapsed

        # navigate preset: step_delay * 1.5 + jitter
        start = time.monotonic()
        human_pause("navigate")
        elapsed = time.monotonic() - start
        assert 0.11 <= elapsed < 0.40, elapsed

        # review preset uses its own (longer) base
        os.environ["AGENT_REVIEW_DELAY_MS"] = "120"
        start = time.monotonic()
        human_pause("review")
        elapsed = time.monotonic() - start
        assert 0.11 <= elapsed < 0.40, elapsed
    finally:
        os.environ["AGENT_PACING"] = "off"
        os.environ.pop("AGENT_STEP_DELAY_MS", None)
        os.environ.pop("AGENT_JITTER_MS", None)
        os.environ.pop("AGENT_REVIEW_DELAY_MS", None)
    assert not pacing_enabled()


def test_pacing_defaults_are_natural():
    from qa_agent.browser.pacing import configured_delays

    os.environ["AGENT_PACING"] = "on"
    try:
        delays = configured_delays()
        assert delays["step_delay_ms"] == 800
        assert delays["jitter_ms"] == 400
        assert delays["review_delay_ms"] == 2000
    finally:
        os.environ["AGENT_PACING"] = "off"


# --------------------------------------------------------- interpretation ----
def test_interpretation_contract_for_mapped_scenario():
    req = parse_feature(FEATURES_DIR / "carrito.feature")
    cases = build_cases(req, MINI_SITEMAP)
    cart02 = next(c for c in cases if c.case_id == "criterio-cart-02")
    interp = Interpretation.from_dict(cart02.interpretation)

    assert cart02.interpretation is not None
    assert "Teclado" in interp.understood_as and "3 unidad" in interp.understood_as
    assert len(interp.steps) >= 3
    assert interp.assertion is not None
    assert "164184.30" in interp.assertion.expected
    assert "criterio" in interp.assertion.origin
    assert interp.assumptions          # IVA 19%, etc.
    assert interp.confidence > 0.5
    # every step is renderable with an ordered number
    assert [s.order for s in interp.steps] == list(range(1, len(interp.steps) + 1))


def test_interpretation_for_unmapped_scenario_is_honest():
    req = parse_feature(FEATURES_DIR / "navegacion.feature")
    req["scenarios"].append({
        "id": "criterio-futuro-99", "name": "Algo nuevo",
        "feature": "X", "tags": [], "steps": ["Cuando algo raro"],
    })
    cases = build_cases(req, MINI_SITEMAP)
    future = next(c for c in cases if c.case_id == "criterio-futuro-99")
    interp = Interpretation.from_dict(future.interpretation)
    assert interp.confidence <= 0.3
    assert interp.unknowns                       # dice qué falta, no inventa


def test_all_checks_have_narratives():
    """Every mapped check in the repo features must produce a narrative."""
    for name in ("carrito", "productos", "servicios", "checkout", "auth", "navegacion"):
        req = parse_feature(FEATURES_DIR / f"{name}.feature")
        cases = build_cases(req, MINI_SITEMAP)
        for case in cases:
            assert case.interpretation, f"{case.case_id} sin interpretacion"
            interp = Interpretation.from_dict(case.interpretation)
            assert interp.understood_as, f"{case.case_id} sin understood_as"
