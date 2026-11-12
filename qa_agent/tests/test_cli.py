"""CLI-level behaviors: app reuse (no port conflict) + placeholder evidence."""
from __future__ import annotations

from qa_agent.models import TestCase
from qa_agent.temporal.activities import execute_suite, summarize
from qa_agent.tests.test_planner import FEATURES_DIR


def test_start_app_reuses_running_instance(base_url):
    """If TiendaDemo is already serving on the port, start_app must NOT spawn
    a second app (that used to fail with 'port already in use')."""
    from qa_agent.cli import start_app

    port = int(base_url.rsplit(":", 1)[1])
    proc = start_app("none", port=port)
    assert proc is None  # reused, nothing spawned


def test_blocked_check_gets_placeholder_not_blank(base_url, tmp_path, monkeypatch):
    """A check that never navigates (BLOCKED) must produce a readable
    placeholder card, not a white about:blank screenshot."""
    from qa_agent.config import agent_settings

    monkeypatch.setattr(agent_settings, "artifacts_dir", tmp_path)
    case = TestCase(
        case_id="criterio-x", scenario_id="criterio-x", name="Sin vocabulario",
        feature="X", checks=[{"check": "unmapped_scenario", "args": {"reason": "prueba"}}],
    )
    result = execute_suite({
        "run_id": "test-blocked",
        "base_url": base_url,
        "cases": [case.to_dict()],
    })
    evidence = list((tmp_path / "runs" / "test-blocked" / "evidence").glob("*.png"))
    assert len(evidence) == 1
    assert evidence[0].stat().st_size > 5_000  # real card, not a blank page

    summary = summarize({
        "run_id": "test-blocked",
        "base_url": base_url,
        "feature_path": str(FEATURES_DIR / "navegacion.feature"),
        "results": result,
    })
    assert summary["scenarios"][0]["status"] == "BLOCKED"
    assert "prueba" in summary["scenarios"][0]["detail"]
