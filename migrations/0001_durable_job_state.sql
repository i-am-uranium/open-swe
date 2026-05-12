BEGIN;

CREATE SCHEMA IF NOT EXISTS open_swe;
SET search_path TO open_swe;

CREATE TABLE IF NOT EXISTS webhook_events (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT uq_webhook_provider_event UNIQUE (provider, provider_event_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(32) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    repo_owner VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    target_pr_number INTEGER,
    target_branch VARCHAR(255),
    base_sha VARCHAR(64),
    head_sha_at_start VARCHAR(64),
    task_text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    worker_id VARCHAR(255),
    worktree_path TEXT,
    branch_name VARCHAR(255),
    commit_sha VARCHAR(64),
    pr_url TEXT,
    diff_base_sha VARCHAR(64),
    diff_head_sha VARCHAR(64),
    patch_path TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    log_path TEXT
);

CREATE TABLE IF NOT EXISTS integration_runs (
    id BIGSERIAL PRIMARY KEY,
    target_pr_number INTEGER NOT NULL,
    integration_branch VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    applied_job_run_ids TEXT,
    conflict_job_run_ids TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_jobs_status_priority_id
    ON jobs (status, priority DESC, id);

CREATE INDEX IF NOT EXISTS ix_jobs_repo_status
    ON jobs (repo_owner, repo_name, status);

CREATE INDEX IF NOT EXISTS ix_job_runs_job_id
    ON job_runs (job_id);

CREATE INDEX IF NOT EXISTS ix_job_runs_status
    ON job_runs (status);

COMMIT;
