# Durable Job State Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first durable orchestration slice: Postgres-backed webhook event, job, and job-run state with read-only status APIs.

**Architecture:** Introduce a small async SQLAlchemy persistence layer behind focused repository helpers. The web runtime can keep its current background execution path for now, but new webhook/job state primitives will be ready for the Redis queue and worker split.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy asyncio, asyncpg for production Postgres, aiosqlite for tests, pytest.

---

## Files

- Create: `agent/storage/__init__.py` - storage package exports.
- Create: `agent/storage/database.py` - database URL config, async engine/session factory, init helper.
- Create: `agent/storage/models.py` - SQLAlchemy models/enums for webhook events, jobs, job runs, integration runs.
- Create: `agent/storage/jobs.py` - job repository helpers used by web and future workers.
- Create: `agent/storage/webhooks.py` - webhook dedupe repository helpers.
- Create: `agent/storage/schemas.py` - JSON-safe serializers for API responses.
- Modify: `agent/webapp.py` - add `/oss/jobs` and `/oss/jobs/{job_id}` endpoints.
- Modify: `pyproject.toml` and `uv.lock` - add SQLAlchemy/asyncpg runtime deps and aiosqlite dev dep.
- Test: `tests/test_durable_job_state.py` - repository tests with sqlite.
- Test: `tests/test_oss_job_api.py` - FastAPI status endpoint tests.

## Task 1: Dependencies

- [x] Add runtime dependencies:
  - `sqlalchemy[asyncio]>=2.0.0`
  - `asyncpg>=0.30.0`
- [x] Add dev dependency:
  - `aiosqlite>=0.20.0`
- [x] Run `uv lock`.
- [x] Run `uv run python -c "import sqlalchemy, asyncpg, aiosqlite"`.

## Task 2: Storage Models

- [x] Write failing tests in `tests/test_durable_job_state.py`:
  - Create a webhook event.
  - Duplicate provider event id returns the existing event.
  - Create a job and fetch it by id.
  - Update job status timestamps.
  - Create a job run and attach branch/PR metadata.
- [x] Run `uv run pytest tests/test_durable_job_state.py -q`; expect import/module failures.
- [x] Implement `agent/storage/database.py` with:
  - `get_database_url()`
  - `create_async_engine_from_url(url)`
  - `async_sessionmaker`
  - `init_models(engine)`
- [x] Implement `agent/storage/models.py` using SQLAlchemy declarative models.
- [x] Implement repository helpers in `jobs.py` and `webhooks.py`.
- [x] Re-run durable job state tests until green.

## Task 3: Status API

- [x] Write failing tests in `tests/test_oss_job_api.py`:
  - `GET /oss/jobs` returns serialized job records.
  - `GET /oss/jobs/{id}` returns one job with runs.
  - Unknown job returns 404.
- [x] Implement serializers in `agent/storage/schemas.py`.
- [x] Add endpoints in `agent/webapp.py`.
- [x] Re-run API tests until green.

## Task 4: Verification

- [x] Run focused tests:
  - `uv run pytest tests/test_durable_job_state.py tests/test_oss_job_api.py -q`
- [x] Run existing OSS tests:
  - `uv run pytest tests/test_oss_runtime.py tests/test_cli_agent_backend.py tests/test_cli_worktree.py -q`
- [x] Run lint/format:
  - `uv run ruff format . --diff`
  - `uv run ruff check .`
- [x] Run full test suite if focused tests and lint are clean:
  - `uv run pytest -q`

## Task 5: Commit and PR

- [ ] Commit with:
  - `feat: add durable job state storage`
- [ ] Push branch `feature/durable-job-state`.
- [ ] Open PR against `i-am-uranium/open-swe:main`.
- [ ] Include test results in the PR body.
