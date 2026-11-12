"""CLI: run the deterministic crawler and save the site map.

Usage:
  python -m qa_agent.cli crawl [--base-url URL] [--bug-profile none|default]
                               [--start-app] [--headless/--headed] [--out PATH]

--start-app boots TiendaDemo (uvicorn) as a subprocess and stops it afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from qa_agent.browser.crawler import crawl
from qa_agent.browser.models import SiteMap
from qa_agent.config import agent_settings


def wait_for_health(base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _app_healthy(base: str) -> bool:
    try:
        import httpx
        r = httpx.get(base + "/health", timeout=2.0)
        return r.status_code == 200 and "TiendaDemo" in r.text
    except Exception:
        return False


def start_app(bug_profile: str, port: int = 8000) -> subprocess.Popen | None:
    """Start TiendaDemo; REUSE an already-running instance on the same port.

    A reused app is aligned to the requested bug profile via the lab API, so
    `--start-app` never fails with 'port already in use' and never kills an
    app the user started manually.
    """
    base = f"http://127.0.0.1:{port}"
    if _app_healthy(base):
        print(f"[app] Reutilizando la app ya levantada en {base}")
        _align_bug_profile(base, bug_profile)
        return None
    env = os.environ.copy()
    env["BUG_PROFILE"] = bug_profile
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
        ],
        cwd=str(agent_settings.app_dir),
        env=env,
    )
    if not wait_for_health(base):
        proc.terminate()
        raise RuntimeError("La app no levanto a tiempo (/health no respondio).")
    return proc


def _align_bug_profile(base: str, bug_profile: str) -> None:
    try:
        import httpx
        current = httpx.get(f"{base}/api/v1/lab/bugs", timeout=2.0).json().get("profile")
        if current != bug_profile:
            httpx.post(f"{base}/api/v1/lab/profile/{bug_profile}", timeout=2.0)
            print(f"[app] Perfil de bugs alineado a '{bug_profile}' (antes: '{current}').")
        else:
            print(f"[app] Perfil de bugs de la app activa: '{current}' (coincide).")
    except Exception:
        print("[app] No se pudo verificar el perfil de bugs de la app activa.")


def save_sitemap(sitemap: SiteMap, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "site_map.json"
    path.write_text(sitemap.model_dump_json(indent=2), encoding="utf-8")
    return path


def cmd_crawl(args: argparse.Namespace) -> int:
    proc = None
    if args.start_app:
        print(f"[app] Levantando TiendaDemo (BUG_PROFILE={args.bug_profile})...")
        proc = start_app(args.bug_profile, port=args.port)

    try:
        base_url = f"http://127.0.0.1:{args.port}" if args.start_app else args.base_url
        print(f"[crawl] Descubriendo {base_url} (sin rutas previas)...")
        sitemap = crawl(
            base_url,
            bug_profile=args.bug_profile,
            headless=not args.headed,
            verbose=True,
        )
        out_dir = Path(args.out) if args.out else agent_settings.artifacts_dir / "crawl"
        path = save_sitemap(sitemap, out_dir)

        print("\n== Resultado ==")
        print(f"Paginas visitadas : {sitemap.stats['pages_visited']}")
        print(f"Links rotos       : {sitemap.stats['broken_links']}")
        for link in sitemap.broken_links:
            print(f"  BROKEN {link.href} ({link.status}) desde '{link.text}' "
                  f"[aparece en {len(link.found_on)} pagina(s)]")
        print(f"Rutas excluidas   : {len(set(sitemap.excluded))} unicas (api/lab/static)")
        print(f"Profundidad max   : {sitemap.stats['max_depth_reached']}")
        print(f"Site map          : {path}")
        return 0
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


# ------------------------------------------------------------- qa run (M3) ---
def cmd_run(args: argparse.Namespace) -> int:
    import asyncio
    from datetime import datetime, timezone

    from temporalio.client import Client

    from qa_agent.temporal.worker import TASK_QUEUE
    from qa_agent.temporal.workflows import QARunWorkflow

    async def _run() -> dict:
        client = await Client.connect(args.temporal_host)
        run_id = f"qa-run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        handle = await client.start_workflow(
            QARunWorkflow.run,
            {
                "run_id": run_id,
                "feature_path": str(Path(args.feature).resolve()),
                "base_url": args.base_url,
                "auto_approve": not args.wait_approval,
                "max_depth": args.max_depth,
                "headless": not args.headed,
            },
            id=run_id,
            task_queue=TASK_QUEUE,
        )
        if args.no_wait:
            print(f"[run] workflow iniciado: {run_id} (no-wait)")
            return {"run_id": run_id}

        print(f"[run] workflow: {run_id}")
        last_phase = ""
        last_live_sig = None
        approved = False
        progress_path = Path(agent_settings.artifacts_dir) / "runs" / run_id / "progress.json"
        while True:
            info = await handle.describe()
            if info.status.name in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
                result = await handle.result()
                return result
            try:
                progress = await handle.query(QARunWorkflow.progress)
                if progress and progress.get("phase") != last_phase:
                    print(f"  [{progress['phase']}] {progress.get('detail', '')}")
                    last_phase = progress.get("phase", "")
            except Exception:
                pass

            # live per-criterion lines from the executor's progress.json
            if progress_path.exists():
                try:
                    live = json.loads(progress_path.read_text(encoding="utf-8"))
                except Exception:
                    live = None
                if live:
                    sig = (live.get("done"), live.get("status"))
                    if sig != last_live_sig:
                        if live.get("status") == "running":
                            print(f"  ▶ {live['current']} ({live['done'] + 1}/{live['total']}) ...")
                        elif live.get("status") == "done":
                            icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⏸"}.get(
                                live.get("case_status"), "?")
                            print(f"  {icon} {live['current']} — {live.get('name', '')}")
                            if live.get("detail"):
                                print(f"     {live['detail']}")
                        last_live_sig = sig

            # HITL: prompt the human when the plan is ready (interactive TTY only)
            if (
                args.wait_approval
                and not approved
                and last_phase == "awaiting_approval"
                and sys.stdin.isatty()
            ):
                cases = await handle.query(QARunWorkflow.planned_cases)
                print("\n  == Plan de pruebas generado ==")
                for i, case in enumerate(cases, 1):
                    interp = (case.get("interpretation") or {}).get("understood_as", "")
                    print(f"   {i}. {case['case_id']} — {case['name']} "
                          f"({len(case['checks'])} check(s))")
                    if interp:
                        print(f"      ↳ {interp}")
                print("\n  (detalle completo en artifacts\\runs\\<run_id>\\plan.md)")
                answer = input("\n  ¿Aprobar ejecución? [S/n]: ").strip().lower()
                approved = answer != "n"
                await handle.signal(
                    QARunWorkflow.approve_plan, approved=approved)
                print("  [run] señal enviada al workflow\n")

            await asyncio.sleep(2)

    proc = None
    if args.start_app:
        print(f"[app] Levantando TiendaDemo (BUG_PROFILE={args.bug_profile})...")
        proc = start_app(args.bug_profile, port=args.port)
    try:
        result = asyncio.run(_run())
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    if result.get("status") == "completed":
        t = result["totals"]
        print("\n== Resultado del run ==")
        print(f"Escenarios : {t['cases']}  (PASS {t['pass']} / FAIL {t['fail']} / BLOCKED {t['blocked']})")
        icons = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "⏸"}
        for sc in result.get("scenarios", []):
            print(f"\n  {icons.get(sc['status'], '?')} {sc['status']:<8} {sc['case_id']} — {sc['name']}")
            print(f"           {sc['detail']}")
            for ev in sc.get("evidence", []):
                print(f"           📸 {ev}")
        print(f"\nResumen    : {result['summary_md']}")
        print(f"Reporte    : {result['report_json']}")
        findings = result.get("findings", [])
        if findings:
            print(f"\nHallazgos  : {len(findings)}")
            for f in findings:
                print(f"  - {f['case_id']}: {f['detail']}")
        return 0 if int(t["fail"]) == 0 else 1
    print(f"Run termino con estado: {result.get('status')}")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qa_agent", description="Laboratorio QA - agente")
    sub = parser.add_subparsers(dest="command", required=True)

    p_crawl = sub.add_parser("crawl", help="Descubre el sitio con el crawler determinista")
    p_crawl.add_argument("--base-url", default=None, help="URL base si no se usa --start-app")
    p_crawl.add_argument("--bug-profile", default="none", choices=["none", "default"])
    p_crawl.add_argument("--start-app", action="store_true", help="Levantar la app automaticamente")
    p_crawl.add_argument("--port", type=int, default=8000)
    p_crawl.add_argument("--headed", action="store_true", help="Navegador visible")
    p_crawl.add_argument("--out", default=None, help="Directorio de salida del site_map.json")
    p_crawl.set_defaults(func=cmd_crawl)

    p_run = sub.add_parser("run", help="Ejecuta un run QA completo via Temporal")
    p_run.add_argument("--feature", required=True, help="Ruta del .feature (criterios)")
    p_run.add_argument("--base-url", default=agent_settings.base_url)
    p_run.add_argument("--bug-profile", default="default", choices=["none", "default"])
    p_run.add_argument("--start-app", action="store_true", help="Levantar la app automaticamente")
    p_run.add_argument("--port", type=int, default=8000)
    p_run.add_argument("--temporal-host", default="localhost:7233")
    p_run.add_argument("--auto-approve", dest="wait_approval", action="store_false",
                       default=True, help="Auto-aprobar el plan (default si no se pasa)")
    p_run.add_argument("--wait-approval", action="store_true",
                       help="Esperar la senal approve_plan del revisor (HITL)")
    p_run.add_argument("--max-depth", type=int, default=2)
    p_run.add_argument("--headed", action="store_true",
                       help="Mostrar el navegador durante la validacion")
    p_run.add_argument("--no-wait", action="store_true", help="Solo iniciar el workflow")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
