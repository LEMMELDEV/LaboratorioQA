"""Temporal worker: task queue 'qa-lab', one browser-bound activity at a time."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from qa_agent.temporal.activities import (
    discover,
    execute_suite,
    parse_requirement,
    plan,
    summarize,
)
from qa_agent.temporal.workflows import QARunWorkflow

TASK_QUEUE = "qa-lab"


async def run_worker(host: str = "localhost:7233") -> None:
    client = await Client.connect(host)
    # sync activities (Playwright) run on a dedicated single thread
    activity_executor = ThreadPoolExecutor(max_workers=1)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[QARunWorkflow],
        activities=[parse_requirement, discover, plan, execute_suite, summarize],
        activity_executor=activity_executor,
    )
    print(f"[worker] listo en '{TASK_QUEUE}' (host={host}). Ctrl+C para salir.")
    async with worker:
        await asyncio.Future()  # run until cancelled


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("\n[worker] detenido.")
