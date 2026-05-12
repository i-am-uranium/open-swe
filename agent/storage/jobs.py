"""Repository helpers for durable jobs and job runs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Job, JobRun, utc_now

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}


async def create_job(
    session: AsyncSession,
    *,
    source: str,
    source_id: str,
    repo_owner: str,
    repo_name: str,
    task_text: str,
    target_pr_number: int | None = None,
    target_branch: str | None = None,
    base_sha: str | None = None,
    head_sha_at_start: str | None = None,
    payload_json: str | None = None,
    priority: int = 0,
    created_by: str | None = None,
) -> Job:
    job = Job(
        source=source,
        source_id=source_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        target_pr_number=target_pr_number,
        target_branch=target_branch,
        base_sha=base_sha,
        head_sha_at_start=head_sha_at_start,
        task_text=task_text,
        payload_json=payload_json,
        priority=priority,
        created_by=created_by,
        status="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(session: AsyncSession, job_id: int) -> Job | None:
    return await session.get(Job, job_id)


async def get_job_with_runs(session: AsyncSession, job_id: int) -> Job | None:
    result = await session.execute(
        select(Job)
        .options(selectinload(Job.runs))
        .where(Job.id == job_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_jobs(session: AsyncSession, *, limit: int = 50) -> list[Job]:
    result = await session.execute(
        select(Job)
        .options(selectinload(Job.runs))
        .order_by(Job.id.desc())
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def update_job_status(
    session: AsyncSession,
    job_id: int,
    status: str,
    *,
    error_summary: str | None = None,
) -> Job:
    job = await get_job(session, job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    now = utc_now()
    job.status = status
    if status == "running" and job.started_at is None:
        job.started_at = now
    if status in TERMINAL_JOB_STATUSES:
        job.finished_at = now
    if error_summary is not None:
        job.error_summary = error_summary

    await session.commit()
    await session.refresh(job)
    return job


async def create_job_run(
    session: AsyncSession,
    *,
    job_id: int,
    status: str = "queued",
    worker_id: str | None = None,
    worktree_path: str | None = None,
    branch_name: str | None = None,
    commit_sha: str | None = None,
    pr_url: str | None = None,
    diff_base_sha: str | None = None,
    diff_head_sha: str | None = None,
    patch_path: str | None = None,
    log_path: str | None = None,
) -> JobRun:
    now = utc_now()
    run = JobRun(
        job_id=job_id,
        worker_id=worker_id,
        worktree_path=worktree_path,
        branch_name=branch_name,
        commit_sha=commit_sha,
        pr_url=pr_url,
        diff_base_sha=diff_base_sha,
        diff_head_sha=diff_head_sha,
        patch_path=patch_path,
        status=status,
        started_at=now if status == "running" else None,
        log_path=log_path,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def update_job_run_status(
    session: AsyncSession,
    run_id: int,
    status: str,
) -> JobRun:
    run = await session.get(JobRun, run_id)
    if run is None:
        raise ValueError(f"Job run not found: {run_id}")

    run.status = status
    if status in TERMINAL_JOB_STATUSES:
        run.finished_at = utc_now()

    await session.commit()
    await session.refresh(run)
    return run
