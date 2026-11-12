"""Run report generation: evidence screenshots + summary.md + report.json."""
from __future__ import annotations

from pathlib import Path

from qa_agent.models import CaseResult, FAIL, PASS, now_iso


def write_report(
    run_dir: Path,
    *,
    run_id: str,
    feature_path: str,
    base_url: str,
    results: list[CaseResult],
) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    totals = _totals(results)
    findings = _findings(results)

    report = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "feature": feature_path,
        "base_url": base_url,
        "totals": totals,
        "cases": [r.to_dict() for r in results],
        "findings": findings,
        "scenarios": scenarios_list(results),
    }
    (run_dir / "report.json").write_text(
        __import__("json").dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "summary.md").write_text(
        _summary_md(run_id, feature_path, base_url, results, totals, findings),
        encoding="utf-8",
    )
    return report


def _totals(results: list[CaseResult]) -> dict:
    n = len(results)
    return {
        "cases": n,
        "pass": sum(1 for r in results if r.status == "PASS"),
        "fail": sum(1 for r in results if r.status == "FAIL"),
        "blocked": sum(1 for r in results if r.status == "BLOCKED"),
        "pass_rate": f"{(sum(1 for r in results if r.status == 'PASS') / n * 100):.0f}%" if n else "-",
    }


def _findings(results: list[CaseResult]) -> list[dict]:
    findings = []
    for case in results:
        if case.status != FAIL:
            continue
        fails = [r for r in case.results if r.status == FAIL]
        for f in fails:
            findings.append({
                "case_id": case.case_id,
                "scenario": case.name,
                "check": f.check,
                "detail": f.detail,
                "observed": f.observed,
                "expected": f.expected,
                "evidence": f.evidence,
            })
    return findings


def scenarios_list(results: list[CaseResult]) -> list[dict]:
    """Compact per-criterion rows for the console output."""
    rows = []
    for case in results:
        bad = [r for r in case.results if r.status != PASS]
        detail = "; ".join(f"{r.check}: {r.detail}" for r in bad) if bad else (
            f"{len(case.results)} check(s) OK" if case.results else "sin resultados"
        )
        evidence = [ev for r in case.results for ev in r.evidence]
        rows.append({
            "case_id": case.case_id,
            "name": case.name,
            "status": case.status,
            "detail": detail,
            "evidence": evidence,
        })
    return rows


def _summary_md(
    run_id: str, feature_path: str, base_url: str,
    results: list[CaseResult], totals: dict, findings: list[dict],
) -> str:
    lines: list[str] = []
    lines.append(f"# Reporte QA — {run_id}\n")
    lines.append(f"- **Fecha:** {now_iso()}")
    lines.append(f"- **App auditada:** {base_url}")
    lines.append(f"- **Criterios:** `{feature_path}`")
    lines.append(f"- **Modo del agente:** heuristico (sin LLM, 0 tokens)\n")

    lines.append("## Resumen\n")
    lines.append("| Métrica | Valor |")
    lines.append("|---|---|")
    lines.append(f"| Escenarios ejecutados | {totals['cases']} |")
    lines.append(f"| ✅ PASS | {totals['pass']} |")
    lines.append(f"| ❌ FAIL | {totals['fail']} |")
    lines.append(f"| ⏸️ BLOCKED | {totals['blocked']} |")
    lines.append(f"| Tasa de aprobación | {totals['pass_rate']} |\n")

    lines.append("## Detalle por escenario\n")
    for case in results:
        icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⏸️"}.get(case.status, "?")
        lines.append(f"### {icon} {case.case_id} — {case.name}")
        if case.error:
            lines.append(f"- Error de ejecución: `{case.error}`")
        if case.interpretation:
            from qa_agent.interpretation import Interpretation, render_markdown

            interp = Interpretation.from_dict(case.interpretation)
            for line in render_markdown(interp).splitlines():
                lines.append(f"> {line}" if line else ">")
            lines.append("")
        for res in case.results:
            ricon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⏸️"}.get(res.status, "?")
            lines.append(f"- {ricon} **{res.status}** — {res.detail}")
            if res.observed:
                lines.append(f"  - Observado: `{res.observed}`")
            if res.expected:
                lines.append(f"  - Esperado: `{res.expected}`")
            for ev in res.evidence:
                lines.append(f"  - 📸 Evidencia: [`{Path(ev).name}`]({ev})")
        lines.append("")

    if findings:
        lines.append("## 🐛 Hallazgos (posibles bugs)\n")
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. **{f['case_id']}** — {f['scenario']}")
            lines.append(f"   - {f['detail']}")
            if f["observed"]:
                lines.append(f"   - Observado: `{f['observed']}`")
            if f["expected"]:
                lines.append(f"   - Esperado: `{f['expected']}`")
            for ev in f["evidence"]:
                lines.append(f"   - 📸 [{Path(ev).name}]({ev})")
        lines.append("")
    else:
        lines.append("## 🐛 Hallazgos\n")
        lines.append("Sin hallazgos: todos los criterios verificados pasaron.\n")

    lines.append("---")
    lines.append("*Generado automáticamente por el agente QA del Laboratorio (modo heurístico).*")
    return "\n".join(lines)
