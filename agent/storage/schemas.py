"""JSON serializers for durable orchestration state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Job, JobRun


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_job_run(run: JobRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "worker_id": run.worker_id,
        "repo_owner": run.repo_owner,
        "repo_name": run.repo_name,
        "execution_order": run.execution_order,
        "depends_on_run_ids": run.depends_on_run_ids,
        "worktree_path": run.worktree_path,
        "branch_name": run.branch_name,
        "commit_sha": run.commit_sha,
        "pr_url": run.pr_url,
        "diff_base_sha": run.diff_base_sha,
        "diff_head_sha": run.diff_head_sha,
        "patch_path": run.patch_path,
        "status": run.status,
        "started_at": _format_datetime(run.started_at),
        "finished_at": _format_datetime(run.finished_at),
        "log_path": run.log_path,
        "summary": run.summary,
        "error_summary": run.error_summary,
    }


def serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "source": job.source,
        "source_id": job.source_id,
        "repo_owner": job.repo_owner,
        "repo_name": job.repo_name,
        "target_pr_number": job.target_pr_number,
        "target_branch": job.target_branch,
        "base_sha": job.base_sha,
        "head_sha_at_start": job.head_sha_at_start,
        "task_text": job.task_text,
        "payload_json": job.payload_json,
        "repo_plan_json": job.repo_plan_json,
        "coordination_status": job.coordination_status,
        "linear_issue_id": job.linear_issue_id,
        "linear_issue_identifier": job.linear_issue_identifier,
        "status": job.status,
        "priority": job.priority,
        "created_by": job.created_by,
        "created_at": _format_datetime(job.created_at),
        "started_at": _format_datetime(job.started_at),
        "finished_at": _format_datetime(job.finished_at),
        "error_summary": job.error_summary,
        "runs": [serialize_job_run(run) for run in job.runs],
    }
