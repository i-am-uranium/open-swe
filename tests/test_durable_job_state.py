from __future__ import annotations

import pytest


@pytest.fixture
async def db_session():
    from agent.storage.database import create_async_engine_from_url, init_models, sessionmaker_for

    engine = create_async_engine_from_url("sqlite+aiosqlite:///:memory:")
    await init_models(engine)
    sessionmaker = sessionmaker_for(engine)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_webhook_event_dedupe_returns_existing_event(db_session) -> None:
    from agent.storage.webhooks import record_webhook_event

    first = await record_webhook_event(
        db_session,
        provider="linear",
        provider_event_id="evt-1",
        payload_hash="hash-1",
        status="accepted",
    )
    second = await record_webhook_event(
        db_session,
        provider="linear",
        provider_event_id="evt-1",
        payload_hash="hash-1",
        status="duplicate",
    )

    assert second.id == first.id
    assert second.status == "accepted"


@pytest.mark.asyncio
async def test_create_and_update_job_state(db_session) -> None:
    from agent.storage.jobs import create_job, get_job, update_job_status

    job = await create_job(
        db_session,
        source="linear",
        source_id="CLI-1332/comment-1",
        repo_owner="clinikk",
        repo_name="subscription-service",
        task_text="Move Slack notification hook",
        payload_json='{"kind": "linear_issue"}',
        created_by="ravi@example.com",
        target_pr_number=119,
        base_sha="base-sha",
        head_sha_at_start="head-sha",
    )

    assert job.status == "queued"
    assert job.target_pr_number == 119
    assert job.payload_json == '{"kind": "linear_issue"}'

    running = await update_job_status(db_session, job.id, "running")
    assert running.status == "running"
    assert running.started_at is not None
    assert running.finished_at is None

    failed = await update_job_status(db_session, job.id, "failed", error_summary="tests failed")
    assert failed.status == "failed"
    assert failed.finished_at is not None
    assert failed.error_summary == "tests failed"

    fetched = await get_job(db_session, job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.status == "failed"


@pytest.mark.asyncio
async def test_create_job_run_attaches_execution_metadata(db_session) -> None:
    from agent.storage.jobs import create_job, create_job_run, get_job_with_runs

    job = await create_job(
        db_session,
        source="linear",
        source_id="CLI-1332/comment-1",
        repo_owner="clinikk",
        repo_name="subscription-service",
        task_text="Move Slack notification hook",
    )
    run = await create_job_run(
        db_session,
        job_id=job.id,
        worker_id="worker-1",
        worktree_path="/workspace/open-swe/worktrees/run-1/subscription-service",
        branch_name="open-swe/subscription-service-run-1",
        status="running",
        commit_sha="commit-sha",
        pr_url="https://github.com/clinikk/subscription-service/pull/120",
        diff_base_sha="base-sha",
        diff_head_sha="head-sha",
        patch_path="/workspace/open-swe/logs/run-1.patch",
        log_path="/workspace/open-swe/logs/run-1.log",
    )

    assert run.job_id == job.id
    assert run.status == "running"

    fetched = await get_job_with_runs(db_session, job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert len(fetched.runs) == 1
    assert fetched.runs[0].branch_name == "open-swe/subscription-service-run-1"
