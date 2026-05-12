"""Durable worker entrypoint for queued Open SWE jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket

from agent import webapp
from agent.job_queue import QueuedJob, create_job_queue
from agent.storage.database import iter_session
from agent.storage.jobs import (
    create_job_run,
    get_job,
    update_job_run_status,
    update_job_status,
)

logger = logging.getLogger(__name__)

WORKER_ID_ENV = "OPEN_SWE_WORKER_ID"
WORKER_POLL_TIMEOUT_MS_ENV = "OPEN_SWE_WORKER_POLL_TIMEOUT_MS"


def get_worker_id() -> str:
    return os.environ.get(WORKER_ID_ENV, "").strip() or socket.gethostname()


def get_worker_poll_timeout_ms() -> int:
    raw_value = os.environ.get(WORKER_POLL_TIMEOUT_MS_ENV, "5000").strip()
    try:
        return max(100, int(raw_value))
    except ValueError:
        return 5000


async def process_durable_job(job_id: int, *, worker_id: str | None = None) -> None:
    worker_id = worker_id or get_worker_id()
    run_id: int | None = None

    async for session in iter_session():
        job = await get_job(session, job_id)
        if job is None:
            logger.warning("Durable job %s not found", job_id)
            return
        await update_job_status(session, job.id, "running")
        run = await create_job_run(session, job_id=job.id, worker_id=worker_id, status="running")
        run_id = run.id
        payload_json = job.payload_json or "{}"
        break

    try:
        payload = json.loads(payload_json)
        await _process_payload(payload)
    except Exception as exc:
        logger.exception("Durable job %s failed", job_id)
        async for session in iter_session():
            await update_job_status(session, job_id, "failed", error_summary=str(exc))
            if run_id is not None:
                await update_job_run_status(session, run_id, "failed")
            break
        raise

    async for session in iter_session():
        await update_job_status(session, job_id, "succeeded")
        if run_id is not None:
            await update_job_run_status(session, run_id, "succeeded")
        break


async def _process_payload(payload: dict) -> None:
    kind = payload.get("kind")
    if kind == "linear_issue":
        issue = payload.get("issue")
        repo_config = payload.get("repo_config")
        if not isinstance(issue, dict) or not isinstance(repo_config, dict):
            raise ValueError("Linear issue job payload must include issue and repo_config")
        await webapp.process_linear_issue(issue, repo_config)
        return

    raise ValueError(f"Unsupported durable job kind: {kind}")


async def run_worker_loop() -> None:
    queue = create_job_queue()
    worker_id = get_worker_id()
    block_ms = get_worker_poll_timeout_ms()
    logger.info("Starting Open SWE durable worker %s", worker_id)

    while True:
        queued_job = await queue.dequeue_job(consumer_name=worker_id, block_ms=block_ms)
        if queued_job is None:
            continue
        await _process_queued_job(queue, queued_job, worker_id=worker_id)


async def _process_queued_job(queue, queued_job: QueuedJob, *, worker_id: str) -> None:
    try:
        await process_durable_job(queued_job.job_id, worker_id=worker_id)
    finally:
        await queue.ack(queued_job.message_id)


def main() -> None:
    logging.basicConfig(level=os.environ.get("OPEN_SWE_LOG_LEVEL", "INFO"))
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
