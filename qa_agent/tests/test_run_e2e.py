"""End-to-end activity test: execute_suite + report with evidence screenshots."""
from __future__ import annotations

from pathlib import Path

from qa_agent.config import agent_settings
from qa_agent.planner import build_cases, parse_feature
from qa_agent.temporal.activities import execute_suite, summarize
from qa_agent.tests.test_planner import FEATURES_DIR, MINI_SITEMAP


def test_plan_activity_writes_plan_md(base_url, tmp_path, monkeypatch):
    from qa_agent.temporal.activities import plan as plan_activity

    monkeypatch.setattr(agent_settings, "artifacts_dir", tmp_path)
    req = parse_feature(FEATURES_DIR / "carrito.feature")
    out = plan_activity({
        "requirement": req,
        "sitemap": MINI_SITEMAP,
        "run_id": "test-plan",
    })
    assert len(out) == 6
    plan_md = (tmp_path / "runs" / "test-plan" / "plan.md").read_text(encoding="utf-8")
    assert "Plan de pruebas" in plan_md
    assert "Cómo lo entendí" in plan_md
    assert "criterio-cart-02" in plan_md


def test_full_run_produces_evidence_and_summary(base_url, tmp_path, monkeypatch, set_active_bugs):
    monkeypatch.setattr(agent_settings, "artifacts_dir", tmp_path)
    set_active_bugs(set())

    req = parse_feature(FEATURES_DIR / "carrito.feature")
    cases = build_cases(req, MINI_SITEMAP)

    result = execute_suite({
        "run_id": "test-run",
        "base_url": base_url,
        "cases": [c.to_dict() for c in cases],
    })
    assert result["run_dir"] == str(tmp_path / "runs" / "test-run")
    case_results = result["cases"]
    assert len(case_results) == 6

    # evidence: one flat image per executed check, no duplicated cierre
    evidence = list((tmp_path / "runs" / "test-run" / "evidence").glob("*.png"))
    assert len(evidence) == 6
    assert all(p.parent == tmp_path / "runs" / "test-run" / "evidence" for p in evidence)
    assert not [p for p in evidence if "__cierre" in p.name]
    assert not any(c.get("closing_evidence") for c in case_results)

    statuses = {c["case_id"]: c["status"] for c in case_results}
    # clean app: the carrito feature must fully pass
    assert set(statuses.values()) == {"PASS"}, statuses

    summary = summarize({
        "run_id": "test-run",
        "base_url": base_url,
        "feature_path": str(FEATURES_DIR / "carrito.feature"),
        "results": result,
    })
    assert summary["status"] == "completed"
    # per-scenario rows for the console output
    rows = summary["scenarios"]
    assert len(rows) == 6
    assert all(r["status"] == "PASS" for r in rows)
    assert all(r["detail"] for r in rows)
    summary_md = Path(summary["summary_md"]).read_text(encoding="utf-8")
    assert "Reporte QA" in summary_md
    assert "PASS | 6" in summary_md
    assert "Cómo lo entendí" in summary_md        # interpretation layer
    assert (Path(summary["report_json"])).exists()


def test_full_run_with_bugs_reports_findings(base_url, tmp_path, monkeypatch, set_active_bugs):
    monkeypatch.setattr(agent_settings, "artifacts_dir", tmp_path)
    set_active_bugs({"BUG-02", "BUG-03"})

    req = parse_feature(FEATURES_DIR / "carrito.feature")
    cases = build_cases(req, MINI_SITEMAP)
    result = execute_suite({
        "run_id": "test-run-bugs",
        "base_url": base_url,
        "cases": [c.to_dict() for c in cases],
    })

    summary = summarize({
        "run_id": "test-run-bugs",
        "base_url": base_url,
        "feature_path": str(FEATURES_DIR / "carrito.feature"),
        "results": result,
    })
    findings = summary["findings"]
    case_ids = {f["case_id"] for f in findings}
    assert "criterio-cart-02" in case_ids   # descuento fantasma
    assert "criterio-cart-04" in case_ids   # cantidad 0 aceptada
    summary_md = Path(summary["summary_md"]).read_text(encoding="utf-8")
    assert "Hallazgos" in summary_md
