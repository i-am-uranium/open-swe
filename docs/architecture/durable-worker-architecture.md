# Durable Worker Architecture TODO

## Current State

The self-hosted OSS runtime has proven the end-to-end path:

- Linear mention is accepted.
- GitHub App authentication works.
- Codex CLI runs inside the Kubernetes pod.
- GitHub Packages authentication works for private `@clinikk/*` npm packages.
- Branch push and PR creation work.
- Per-run worktree isolation is available for CLI backends.

The remaining production limit is orchestration. The current runtime is still
single-process and in-memory, so FastAPI background tasks are not enough for
durable multi-job execution.

## Target Architecture

Split Open SWE into web and worker responsibilities:

```text
open-swe-web
  - receive Linear/GitHub/Slack webhooks
  - validate signatures and repo allowlist
  - dedupe webhook events
  - create durable job rows in Postgres
  - enqueue job ids into Redis
  - return 200 quickly

open-swe-worker
  - consume Redis jobs
  - mark jobs running/succeeded/failed/blocked in Postgres
  - create per-run worktrees
  - run Codex or Claude
  - push branches and open/update PRs
  - notify Linear/Slack/GitHub
```

Use Postgres as the source of truth and Redis for queueing, leases, retries,
short-lived locks, and rate limiting. Keep the PV for cached repositories,
per-run worktrees, and optional raw logs.

## Initial Data Model

### `webhook_events`

- `id`
- `provider`: `linear`, `github`, `slack`
- `provider_event_id`
- `payload_hash`
- `status`: `accepted`, `ignored`, `duplicate`, `failed`
- `received_at`
- `processed_at`

### `jobs`

- `id`
- `source`: `linear`, `github`, `slack`, `manual`
- `source_id`
- `repo_owner`
- `repo_name`
- `target_pr_number`
- `target_branch`
- `base_sha`
- `head_sha_at_start`
- `task_text`
- `status`: `queued`, `running`, `succeeded`, `failed`, `blocked`, `cancelled`
- `priority`
- `created_by`
- `created_at`
- `started_at`
- `finished_at`
- `error_summary`

### `job_runs`

- `id`
- `job_id`
- `worker_id`
- `worktree_path`
- `branch_name`
- `commit_sha`
- `pr_url`
- `diff_base_sha`
- `diff_head_sha`
- `patch_path`
- `status`
- `started_at`
- `finished_at`
- `log_path`

### `integration_runs`

Reserved for patch-stack/stacked-branch mode.

- `id`
- `target_pr_number`
- `integration_branch`
- `status`
- `applied_job_run_ids`
- `conflict_job_run_ids`
- `created_at`
- `finished_at`

## Concurrency Policy

Start conservative:

```text
OPEN_SWE_WORKER_CONCURRENCY=2
OPEN_SWE_MAX_GLOBAL_RUNNING=2
OPEN_SWE_MAX_REPO_RUNNING=1
OPEN_SWE_MAX_PR_RUNNING=1
PR_CONCURRENCY_MODE=serial
```

This means unrelated repos can run in parallel, while the same repo/PR is
serialized until patch-stack mode is implemented.

## Patch-Stack Direction

Design for patch-stack from day one, but do not make it the first production
execution mode.

Initial production mode:

```text
PR_CONCURRENCY_MODE=serial
```

Future mode:

```text
PR_CONCURRENCY_MODE=stacked
```

In stacked mode, each worker pushes a unique branch for its job. A coordinator
creates or updates an integration branch by cherry-picking/rebasing completed
job branches onto the target PR/base. Conflicting job runs are marked blocked
and reported back to Linear/GitHub.

## Implementation TODO

### Phase 1: Durable Job State

- [ ] Add database configuration for Postgres.
- [ ] Add migrations for `webhook_events`, `jobs`, and `job_runs`.
- [ ] Add repository/data-access helpers for job creation and status updates.
- [ ] Add webhook dedupe using provider event id and payload hash.
- [ ] Add `/oss/jobs` and `/oss/jobs/{id}` read-only status endpoints.

### Phase 2: Redis Queue

- [ ] Add Redis configuration.
- [ ] Add a small queue abstraction around enqueue, claim, retry, and ack.
- [ ] Store only job ids in Redis; keep job payload in Postgres.
- [ ] Add retry/backoff policy for transient failures.
- [ ] Add dead-letter status for exhausted retries.

### Phase 3: Worker Process

- [ ] Add `python -m agent.worker`.
- [ ] Move Codex/Claude execution out of FastAPI background tasks.
- [ ] Worker claims a job, updates Postgres, prepares worktree, runs CLI agent, and writes result.
- [ ] Persist branch name, commit sha, PR url, status, and log path in `job_runs`.
- [ ] Ensure worker can recover safely after pod restart.

### Phase 4: Concurrency Controls

- [ ] Add global concurrency limit.
- [ ] Add repo-level concurrency lock.
- [ ] Add PR-level concurrency lock.
- [ ] Start with same-PR serialization.
- [ ] Record skipped/delayed lock attempts in job status history.

### Phase 5: Kubernetes Split

- [ ] Split deployment into `open-swe-web` and `open-swe-worker`.
- [ ] Keep web replicas stateless.
- [ ] Scale worker replicas independently.
- [ ] Mount PV to workers for repo cache and worktrees.
- [ ] Add worker health/readiness checks.
- [ ] Add resource profiles for Codex-heavy workers.

### Phase 6: Patch-Stack Coordinator

- [ ] Add `integration_runs` persistence.
- [ ] Store per-job branch/diff metadata from the first worker implementation.
- [ ] Add coordinator process or queue type.
- [ ] Implement integration branch creation/update.
- [ ] Mark conflicted job runs blocked with actionable comments.
- [ ] Allow `PR_CONCURRENCY_MODE=stacked` after serial mode is stable.

## Deployment Notes

Postgres and Redis should be externally managed or deployed as standard cluster
services, not embedded in the Open SWE web pod. Secrets should include database
URL, Redis URL, GitHub App credentials, Linear API key, Slack credentials,
OpenAI/Claude auth, and npm package token.

The PV should remain worker-owned execution state:

```text
/workspace/open-swe/
  repos/
  worktrees/
  logs/
```

Web pods should not depend on the PV.
