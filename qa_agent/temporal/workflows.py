"""QARunWorkflow: 100% deterministic orchestration.

RULE: no LLM, no I/O here. Everything lives in activities.
Phases: parse_requirement -> discover -> plan -> [HITL] -> execute_suite -> summarize
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

NO_RETRY = RetryPolicy(maximum_attempts=1)


@workflow.defn
class QARunWorkflow:
    def __init__(self) -> None:
        self._approved: bool | None = None
        self._cases: list[dict] = []
        self._progress: dict = {"phase": "created", "done": 0, "total": 0, "detail": ""}

    @workflow.run
    async def run(self, params: dict) -> dict:
        self._progress = {"phase": "parse", "done": 0, "total": 5, "detail": params.get("feature_path", "")}

        requirement = await workflow.execute_activity(
            "parse_requirement", params["feature_path"],
            start_to_close_timeout=timedelta(seconds=60), retry_policy=NO_RETRY,
        )
        self._progress = {"phase": "discover", "done": 1, "total": 5,
                          "detail": f"criterios: {len(requirement.get('scenarios', []))}"}

        sitemap = await workflow.execute_activity(
            "discover",
            {
                "base_url": params["base_url"],
                "max_depth": params.get("max_depth", 2),
                "headless": params.get("headless", True),
            },
            start_to_close_timeout=timedelta(minutes=15), retry_policy=NO_RETRY,
        )
        self._progress = {"phase": "plan", "done": 2, "total": 5,
                          "detail": f"paginas descubiertas: {sitemap.get('stats', {}).get('pages_visited', 0)}"}

        cases = await workflow.execute_activity(
            "plan",
            {
                "requirement": requirement,
                "sitemap": sitemap,
                "run_id": params.get("run_id", ""),
            },
            start_to_close_timeout=timedelta(seconds=60), retry_policy=NO_RETRY,
        )
        self._cases = cases
        self._progress = {"phase": "awaiting_approval", "done": 3, "total": 5,
                          "detail": f"casos: {len(cases)}"}

        if not params.get("auto_approve", True):
            await workflow.wait_condition(lambda: self._approved is not None)
            if not self._approved:
                return {
                    "status": "rejected",
                    "run_id": params.get("run_id", ""),
                    "message": "El plan de pruebas fue rechazado por el revisor.",
                }
            self._progress = {"phase": "execute", "done": 4, "total": 5, "detail": "aprobado por revisor"}
        else:
            self._progress = {"phase": "execute", "done": 4, "total": 5, "detail": "auto-aprobado"}

        results = await workflow.execute_activity(
            "execute_suite",
            {
                "run_id": params.get("run_id", "qa-run"),
                "base_url": params["base_url"],
                "cases": cases,
                "headless": params.get("headless", True),
            },
            start_to_close_timeout=timedelta(minutes=45),
            heartbeat_timeout=timedelta(seconds=60),
            retry_policy=NO_RETRY,
        )
        self._progress = {"phase": "summarize", "done": 4.5, "total": 5,
                          "detail": f"resultados: {len(results.get('cases', []))}"}

        summary = await workflow.execute_activity(
            "summarize",
            {
                "run_id": params.get("run_id", "qa-run"),
                "base_url": params["base_url"],
                "feature_path": params["feature_path"],
                "results": results,
            },
            start_to_close_timeout=timedelta(seconds=60), retry_policy=NO_RETRY,
        )
        self._progress = {"phase": "done", "done": 5, "total": 5,
                          "detail": summary.get("totals", {}).get("pass_rate", "")}
        return summary

    @workflow.signal
    def approve_plan(self, approved: bool = True) -> None:
        self._approved = approved

    @workflow.query
    def progress(self) -> dict:
        return self._progress

    @workflow.query
    def planned_cases(self) -> list[dict]:
        return self._cases
