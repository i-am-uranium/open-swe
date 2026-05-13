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

    async for session in iter_session():
        job = await get_job(session, job_id)
        if job is None:
            logger.warning("Durable job %s not found", job_id)
            return
        await update_job_status(session, job.id, "running")
        payload_json = job.payload_json or "{}"
        break

    failed_runs: list[str] = []
    try:
        payload = json.loads(payload_json)
        failed_runs = await _process_payload(job_id, payload, worker_id=worker_id)
    except Exception as exc:
        logger.exception("Durable job %s failed", job_id)
        async for session in iter_session():
            await update_job_status(session, job_id, "failed", error_summary=str(exc))
            break
        raise

    async for session in iter_session():
        if failed_runs:
            await update_job_status(
                session,
                job_id,
                "failed",
                error_summary=f"{len(failed_runs)} repo run(s) failed: {', '.join(failed_runs)}",
            )
        else:
            await update_job_status(session, job_id, "succeeded")
        break


async def _process_payload(
    job_id: int,
    payload: dict,
    *,
    worker_id: str,
) -> list[str]:
    kind = payload.get("kind")
    if kind == "linear_issue":
        issue = payload.get("issue")
        repo_configs = payload.get("repo_configs")
        repo_plan = payload.get("repo_plan")
        if not isinstance(issue, dict):
            raise ValueError("Linear issue job payload must include issue")
        if not isinstance(repo_configs, list):
            repo_config = payload.get("repo_config")
            repo_configs = [repo_config] if isinstance(repo_config, dict) else []
        if not repo_configs:
            raise ValueError("Linear issue job payload must include at least one repo")
        return await _process_linear_issue_repos(
            job_id,
            issue,
            repo_configs,
            repo_plan if isinstance(repo_plan, dict) else {},
            worker_id=worker_id,
        )

    raise ValueError(f"Unsupported durable job kind: {kind}")


async def _process_linear_issue_repos(
    job_id: int,
    issue: dict,
    repo_configs: list,
    repo_plan: dict,
    *,
    worker_id: str,
) -> list[str]:
    failed_runs: list[str] = []
    valid_repo_configs = [repo for repo in repo_configs if isinstance(repo, dict)]
    is_multi_repo = len(valid_repo_configs) > 1

    for index, repo_config in enumerate(valid_repo_configs):
        repo_owner = str(repo_config.get("owner") or "")
        repo_name = str(repo_config.get("name") or "")
        repo_label = f"{repo_owner}/{repo_name}"
        async for session in iter_session():
            run = await create_job_run(
                session,
                job_id=job_id,
                worker_id=worker_id,
                repo_owner=repo_owner,
                repo_name=repo_name,
                execution_order=index,
                status="running",
            )
            run_id = run.id
            break

        issue_for_repo = dict(issue)
        if is_multi_repo:
            issue_for_repo.update(
                {
                    "multi_repo": True,
                    "repo_index": index,
                    "repo_count": len(valid_repo_configs),
                    "repo_plan": repo_plan,
                }
            )

        try:
            await webapp.process_linear_issue(issue_for_repo, repo_config)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Durable repo run %s for job %s failed", repo_label, job_id)
            failed_runs.append(repo_label)
            async for session in iter_session():
                await update_job_run_status(
                    session,
                    run_id,
                    "failed",
                    error_summary=str(exc),
                )
                break
        else:
            async for session in iter_session():
                await update_job_run_status(session, run_id, "succeeded")
                break

    return failed_runs


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
