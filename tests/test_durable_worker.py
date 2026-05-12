from __future__ import annotations

import asyncio
import json


def test_enqueue_linear_issue_job_persists_job_and_queues_id(monkeypatch, tmp_path) -> None:
    from agent import webapp

    database_url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
    monkeypatch.setenv("OPEN_SWE_DATABASE_URL", database_url)
    monkeypatch.setenv("OPEN_SWE_REDIS_URL", "redis://localhost:6379/0")

    asyncio.run(_init_database(database_url))

    enqueued_job_ids: list[int] = []

    class FakeQueue:
        async def enqueue_job(self, job_id: int) -> str:
            enqueued_job_ids.append(job_id)
            return "1-0"

    monkeypatch.setattr(webapp, "create_job_queue", lambda: FakeQueue())

    job = asyncio.run(
        webapp.enqueue_linear_issue_job(
            {
                "id": "issue-1",
                "title": "Move notification hook",
                "triggering_comment_id": "comment-1",
                "triggering_comment": "@openswe please do this",
            },
            {"owner": "clinikk", "name": "subscription-service"},
        )
    )

    assert enqueued_job_ids == [job.id]
    assert job.source == "linear"
    assert job.source_id == "issue-1/comment-1"
    assert job.repo_owner == "clinikk"
    assert job.repo_name == "subscription-service"

    payload = json.loads(job.payload_json or "{}")
    assert payload["kind"] == "linear_issue"
    assert payload["issue"]["id"] == "issue-1"
    assert payload["repo_config"] == {"owner": "clinikk", "name": "subscription-service"}


def test_worker_processes_linear_issue_job(monkeypatch, tmp_path) -> None:
    from agent import worker

    database_url = f"sqlite+aiosqlite:///{tmp_path}/jobs.db"
    monkeypatch.setenv("OPEN_SWE_DATABASE_URL", database_url)

    job_id = asyncio.run(_seed_linear_issue_job(database_url))
    processed: list[tuple[dict, dict]] = []

    async def fake_process_linear_issue(issue: dict, repo_config: dict) -> None:
        processed.append((issue, repo_config))

    monkeypatch.setattr(worker.webapp, "process_linear_issue", fake_process_linear_issue)

    asyncio.run(worker.process_durable_job(job_id, worker_id="worker-1"))

    assert processed == [
        (
            {"id": "issue-1", "title": "Move notification hook"},
            {"owner": "clinikk", "name": "subscription-service"},
        )
    ]

    job = asyncio.run(_load_job(database_url, job_id))
    assert job is not None
    assert job.status == "succeeded"
    assert len(job.runs) == 1
    assert job.runs[0].worker_id == "worker-1"
    assert job.runs[0].status == "succeeded"


async def _init_database(database_url: str) -> None:
    from agent.storage.database import create_async_engine_from_url, init_models

    engine = create_async_engine_from_url(database_url)
    await init_models(engine)
    await engine.dispose()


async def _seed_linear_issue_job(database_url: str) -> int:
    from agent.storage.database import create_async_engine_from_url, init_models, sessionmaker_for
    from agent.storage.jobs import create_job

    engine = create_async_engine_from_url(database_url)
    await init_models(engine)
    sessionmaker = sessionmaker_for(engine)
    async with sessionmaker() as session:
        job = await create_job(
            session,
            source="linear",
            source_id="issue-1/comment-1",
            repo_owner="clinikk",
            repo_name="subscription-service",
            task_text="Move notification hook",
            payload_json=json.dumps(
                {
                    "kind": "linear_issue",
                    "issue": {"id": "issue-1", "title": "Move notification hook"},
                    "repo_config": {"owner": "clinikk", "name": "subscription-service"},
                }
            ),
        )
    await engine.dispose()
    return job.id


async def _load_job(database_url: str, job_id: int):
    from agent.storage.database import create_async_engine_from_url, sessionmaker_for
    from agent.storage.jobs import get_job_with_runs

    engine = create_async_engine_from_url(database_url)
    sessionmaker = sessionmaker_for(engine)
    async with sessionmaker() as session:
        job = await get_job_with_runs(session, job_id)
    await engine.dispose()
    return job
