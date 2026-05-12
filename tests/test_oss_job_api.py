from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient


def test_oss_jobs_requires_durable_storage_config(monkeypatch) -> None:
    from agent import webapp

    monkeypatch.delenv("OPEN_SWE_DATABASE_URL", raising=False)

    client = TestClient(webapp.app)
    response = client.get("/oss/jobs")

    assert response.status_code == 503
    assert response.json()["detail"] == "Durable job storage is not configured"


def test_oss_jobs_lists_durable_jobs(monkeypatch, tmp_path) -> None:
    from agent import webapp

    database_url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
    monkeypatch.setenv("OPEN_SWE_DATABASE_URL", database_url)

    job_id = asyncio.run(_seed_jobs(database_url))

    client = TestClient(webapp.app)
    response = client.get("/oss/jobs")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["repo_owner"] == "clinikk"
    assert jobs[0]["repo_name"] == "subscription-service"
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["runs"][0]["branch_name"] == "open-swe/subscription-service-run-1"


def test_oss_job_detail_returns_404_for_missing_job(monkeypatch, tmp_path) -> None:
    from agent import webapp

    database_url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
    monkeypatch.setenv("OPEN_SWE_DATABASE_URL", database_url)
    asyncio.run(_init_database(database_url))

    client = TestClient(webapp.app)
    response = client.get("/oss/jobs/404")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_oss_job_detail_returns_job_with_runs(monkeypatch, tmp_path) -> None:
    from agent import webapp

    database_url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
    monkeypatch.setenv("OPEN_SWE_DATABASE_URL", database_url)

    job_id = asyncio.run(_seed_jobs(database_url))

    client = TestClient(webapp.app)
    response = client.get(f"/oss/jobs/{job_id}")

    assert response.status_code == 200
    job = response.json()
    assert job["id"] == job_id
    assert job["target_pr_number"] == 119
    assert job["task_text"] == "Move Slack notification hook"
    assert job["runs"][0]["worktree_path"] == (
        "/workspace/open-swe/worktrees/run-1/subscription-service"
    )


async def _init_database(database_url: str) -> None:
    from agent.storage.database import create_async_engine_from_url, init_models

    engine = create_async_engine_from_url(database_url)
    await init_models(engine)
    await engine.dispose()


async def _seed_jobs(database_url: str) -> int:
    from agent.storage.database import create_async_engine_from_url, init_models, sessionmaker_for
    from agent.storage.jobs import create_job, create_job_run

    engine = create_async_engine_from_url(database_url)
    await init_models(engine)
    sessionmaker = sessionmaker_for(engine)
    async with sessionmaker() as session:
        job = await create_job(
            session,
            source="linear",
            source_id="CLI-1332/comment-1",
            repo_owner="clinikk",
            repo_name="subscription-service",
            task_text="Move Slack notification hook",
            target_pr_number=119,
            created_by="ravi@example.com",
        )
        await create_job_run(
            session,
            job_id=job.id,
            worker_id="worker-1",
            worktree_path="/workspace/open-swe/worktrees/run-1/subscription-service",
            branch_name="open-swe/subscription-service-run-1",
            status="running",
            pr_url="https://github.com/clinikk/subscription-service/pull/120",
        )
    await engine.dispose()
    return job.id
