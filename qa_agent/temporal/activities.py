"""Activities: all the I/O, LLM-free in heuristic mode."""
from __future__ import annotations

from pathlib import Path

from temporalio import activity

from qa_agent.browser.crawler import crawl
from qa_agent.browser.pacing import human_pause
from qa_agent.browser.session import BrowserSession
from qa_agent.checks import run_check
from qa_agent.config import agent_settings
from qa_agent.evidence import is_blank_page, placeholder_png
from qa_agent.models import BLOCKED, CaseResult, CheckResult, FAIL, PASS, TestCase, now_iso
from qa_agent.planner import build_cases, parse_feature
from qa_agent.reporting import write_report

import json


@activity.defn
def parse_requirement(feature_path: str) -> dict:
    return parse_feature(feature_path)


@activity.defn
def discover(params: dict) -> dict:
    sitemap = crawl(
        params["base_url"],
        max_depth=params.get("max_depth", agent_settings.max_depth),
        headless=params.get("headless", True),
    )
    return sitemap.model_dump(mode="json")


@activity.defn
def plan(params: dict) -> list[dict]:
    cases = build_cases(params["requirement"], params["sitemap"])
    out = [c.to_dict() for c in cases]
    # plan.md: the human-readable plan the reviewer approves (HITL)
    run_id = params.get("run_id")
    if run_id:
        run_dir = agent_settings.artifacts_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "plan.md").write_text(_plan_md(run_id, cases), encoding="utf-8")
    return out


def _plan_md(run_id: str, cases) -> str:
    from qa_agent.interpretation import Interpretation, render_markdown

    lines = [
        f"# Plan de pruebas — {run_id}",
        "",
        "Interpretación de cada criterio de aceptación, generada ANTES de ejecutar.",
        "Revisa cómo entendió el agente cada criterio y aprueba o rechaza.",
        "",
    ]
    for case in cases:
        interp = Interpretation.from_dict(case.interpretation) if case.interpretation else None
        lines.append(f"## {case.case_id} — {case.name}")
        if interp:
            lines.append(render_markdown(interp))
        else:
            lines.append("*Sin interpretación.*")
        lines.append("")
    return "\n".join(lines)


def _heartbeat(payload: dict) -> None:
    """Heartbeat only when running inside a real Temporal activity."""
    if activity.in_activity():
        activity.heartbeat(payload)


def _case_detail(case_results: list[CheckResult], status: str) -> str:
    """Short execution description for console/live output."""
    if not case_results:
        return "sin resultados"
    bad = [r for r in case_results if r.status != PASS]
    if bad:
        return "; ".join(f"{r.check}: {r.detail}" for r in bad)
    return f"{len(case_results)} check(s) OK"


@activity.defn
def execute_suite(params: dict) -> dict:
    """Run every case sequentially; one browser session per case (isolation).

    Writes progress.json after each state change so the CLI can show live
    per-criterion lines. Heartbeats after each case for Temporal monitoring.
    """
    run_id = params["run_id"]
    base_url = params["base_url"]
    run_dir = agent_settings.artifacts_dir / "runs" / run_id
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    progress_path = run_dir / "progress.json"

    def _progress(done: int, current: str, status: str, **extra) -> None:
        payload = {
            "run_id": run_id, "done": done, "total": len(cases),
            "current": current, "status": status,
            "updated_at": now_iso(), **extra,
        }
        progress_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    cases = [TestCase.from_dict(c) for c in params["cases"]]
    headless = params.get("headless", True)
    results: list[CaseResult] = []

    for i, case in enumerate(cases, start=1):
        _heartbeat({
            "phase": "execute_suite", "case": case.case_id,
            "done": i - 1, "total": len(cases),
        })
        _progress(i - 1, case.case_id, "running", name=case.name)
        case_results: list[CheckResult] = []
        try:
            with BrowserSession(base_url=base_url, headless=headless) as session:
                for spec in case.checks:
                    check_id = spec["check"]
                    args = spec.get("args", {})
                    result = run_check(check_id, session, args)
                    # evidence screenshot for every check (pass or fail).
                    # Flat layout: evidence/<case_id>__<check>.png
                    rel = ""
                    try:
                        if is_blank_page(session):
                            # check never opened a screen (BLOCKED): readable card
                            card = evidence_dir / f"{case.case_id}__{check_id}.png"
                            if placeholder_png(card, f"{case.case_id} — {case.name}",
                                               f"{check_id}: {result.status} — {result.detail[:90]}"):
                                rel = str(card.relative_to(run_dir))
                        else:
                            path = session.screenshot(
                                f"{case.case_id}__{check_id}", artifacts_dir=evidence_dir)
                            rel = str(path.relative_to(run_dir))
                    except Exception:
                        pass
                    result.check = check_id
                    result.evidence = [rel] if rel else []
                    case_results.append(result)

                # --- criterion close: time to look at the final state ---
                if case.checks:
                    human_pause("review")
        except Exception as exc:
            case_results.append(CheckResult(
                check="session", status=FAIL,
                detail=f"No se pudo abrir la sesion de navegador: {exc}",
            ))

        status = PASS if all(r.status == PASS for r in case_results) and case_results else (
            BLOCKED if all(r.status == BLOCKED for r in case_results) else FAIL
        )
        detail = _case_detail(case_results, status)
        results.append(CaseResult(
            case_id=case.case_id, scenario_id=case.scenario_id, name=case.name,
            feature=case.feature, status=status,
            results=case_results,
            interpretation=case.interpretation,
        ).to_dict())
        _progress(i, case.case_id, "done", name=case.name,
                  case_status=status, detail=detail)

    _heartbeat({"phase": "execute_suite", "done": len(cases), "total": len(cases)})
    return {
        "run_id": run_id,
        "base_url": base_url,
        "started_at": now_iso(),
        "run_dir": str(run_dir),
        "cases": results,
    }


@activity.defn
def summarize(params: dict) -> dict:
    from qa_agent.models import CaseResult as CR

    results_payload = params["results"]
    results = [CR.from_dict(r) for r in results_payload["cases"]]
    run_dir = Path(results_payload.get("run_dir", ""))
    report = write_report(
        run_dir,
        run_id=params["run_id"],
        feature_path=params["feature_path"],
        base_url=params["base_url"],
        results=results,
    )
    totals = report["totals"]
    return {
        "status": "completed",
        "run_id": params["run_id"],
        "run_dir": str(run_dir),
        "summary_md": str(run_dir / "summary.md"),
        "report_json": str(run_dir / "report.json"),
        "totals": totals,
        "findings": report["findings"],
        "scenarios": report["scenarios"],
    }
