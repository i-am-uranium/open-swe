BEGIN;

SET search_path TO open_swe;

ALTER TABLE jobs
    ADD COLUMN IF NOT EXISTS repo_plan_json TEXT,
    ADD COLUMN IF NOT EXISTS coordination_status VARCHAR(32),
    ADD COLUMN IF NOT EXISTS linear_issue_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS linear_issue_identifier VARCHAR(64);

ALTER TABLE job_runs
    ADD COLUMN IF NOT EXISTS repo_owner VARCHAR(255),
    ADD COLUMN IF NOT EXISTS repo_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS execution_order INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS depends_on_run_ids TEXT,
    ADD COLUMN IF NOT EXISTS summary TEXT,
    ADD COLUMN IF NOT EXISTS error_summary TEXT;

CREATE INDEX IF NOT EXISTS ix_job_runs_repo_status
    ON job_runs (repo_owner, repo_name, status);

CREATE INDEX IF NOT EXISTS ix_job_runs_job_execution_order
    ON job_runs (job_id, execution_order);

COMMIT;
