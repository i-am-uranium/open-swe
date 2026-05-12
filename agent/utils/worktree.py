"""Per-run git worktree preparation for self-hosted CLI backends."""

from __future__ import annotations

import asyncio
import posixpath
import re
import shlex
from dataclasses import dataclass

from deepagents.backends.protocol import SandboxBackendProtocol


@dataclass(frozen=True)
class WorktreeInfo:
    path: str
    branch: str
    source_dir: str
    pr_number: int | None = None


def prepare_cli_worktree(
    sandbox_backend: SandboxBackendProtocol,
    *,
    base_work_dir: str,
    repo_config: dict[str, str],
    run_id: str,
    task_text: str,
) -> WorktreeInfo:
    owner = _required_repo_part(repo_config, "owner")
    repo = _required_repo_part(repo_config, "name")
    run_slug = _sanitize_path_segment(run_id)
    repo_slug = _sanitize_path_segment(repo)
    source_slug = f"{_sanitize_path_segment(owner)}__{repo_slug}"
    source_dir = posixpath.join(base_work_dir, "repos", source_slug)
    worktree_dir = posixpath.join(base_work_dir, "worktrees", run_slug, repo_slug)
    branch = f"open-swe/{repo_slug}-{_sanitize_branch_segment(run_id)}"
    pr_number = _extract_pr_number(task_text, owner=owner, repo=repo)

    command = _build_worktree_setup_command(
        owner=owner,
        repo=repo,
        source_dir=source_dir,
        worktree_dir=worktree_dir,
        branch=branch,
        pr_number=pr_number,
    )
    response = sandbox_backend.execute(command)
    if response.exit_code != 0:
        raise RuntimeError(f"Failed to prepare CLI worktree: {response.output}")

    return WorktreeInfo(
        path=worktree_dir,
        branch=branch,
        source_dir=source_dir,
        pr_number=pr_number,
    )


async def aprepare_cli_worktree(
    sandbox_backend: SandboxBackendProtocol,
    *,
    base_work_dir: str,
    repo_config: dict[str, str],
    run_id: str,
    task_text: str,
) -> WorktreeInfo:
    return await asyncio.to_thread(
        prepare_cli_worktree,
        sandbox_backend,
        base_work_dir=base_work_dir,
        repo_config=repo_config,
        run_id=run_id,
        task_text=task_text,
    )


def _required_repo_part(repo_config: dict[str, str], key: str) -> str:
    value = repo_config.get(key, "").strip()
    if not value:
        raise ValueError(f"repo.{key} is required for CLI worktree preparation")
    return value


def _extract_pr_number(task_text: str, *, owner: str, repo: str) -> int | None:
    escaped_owner = re.escape(owner)
    escaped_repo = re.escape(repo)
    patterns = (
        rf"github\.com/{escaped_owner}/{escaped_repo}/pull/(\d+)",
        rf"\b{escaped_owner}/{escaped_repo}#(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, task_text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _sanitize_path_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return sanitized or "run"


def _sanitize_branch_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-/")
    return sanitized[:64] or "run"


def _build_worktree_setup_command(
    *,
    owner: str,
    repo: str,
    source_dir: str,
    worktree_dir: str,
    branch: str,
    pr_number: int | None,
) -> str:
    quoted_clone_url = shlex.quote(f"https://github.com/{owner}/{repo}.git")
    quoted_source_dir = shlex.quote(source_dir)
    quoted_worktree_dir = shlex.quote(worktree_dir)
    quoted_branch = shlex.quote(branch)
    quoted_parent_source = shlex.quote(posixpath.dirname(source_dir))
    quoted_parent_worktree = shlex.quote(posixpath.dirname(worktree_dir))
    pr_fetch = ""
    base_ref = '"origin/${default_branch}"'
    if pr_number is not None:
        pr_ref = f"refs/remotes/origin/pr-{pr_number}"
        pr_fetch = (
            "\n"
            f'git -C "$source_dir" -c "http.https://github.com/.extraheader=$git_auth_header" '
            f"fetch origin +pull/{pr_number}/head:{shlex.quote(pr_ref)}\n"
        )
        base_ref = shlex.quote(pr_ref)

    return f"""set -euo pipefail
source_dir={quoted_source_dir}
worktree_dir={quoted_worktree_dir}
branch_name={quoted_branch}
clone_url={quoted_clone_url}
github_token="${{OPEN_SWE_GITHUB_TOKEN:-${{GH_TOKEN:-}}}}"
if [ -z "$github_token" ]; then
  echo "OPEN_SWE_GITHUB_TOKEN or GH_TOKEN is required for git authentication" >&2
  exit 1
fi
git_auth_header="AUTHORIZATION: bearer $github_token"
export GIT_TERMINAL_PROMPT=0
mkdir -p {quoted_parent_source} {quoted_parent_worktree}
if [ ! -d "$source_dir/.git" ]; then
  rm -rf "$source_dir"
  git -c "http.https://github.com/.extraheader=$git_auth_header" clone "$clone_url" "$source_dir"
else
  git -C "$source_dir" remote set-url origin "$clone_url"
fi
git -C "$source_dir" -c "http.https://github.com/.extraheader=$git_auth_header" fetch origin --prune
default_branch="$(git -C "$source_dir" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
if [ -z "$default_branch" ]; then
  default_branch="$(git -C "$source_dir" -c "http.https://github.com/.extraheader=$git_auth_header" remote show origin | awk '/HEAD branch/ {{print $NF; exit}}' || true)"
fi
if [ -z "$default_branch" ]; then
  default_branch="master"
fi{pr_fetch}
if [ ! -d "$worktree_dir/.git" ]; then
  mkdir -p "$(dirname "$worktree_dir")"
  git -C "$source_dir" worktree prune
  git -C "$source_dir" worktree add -B "$branch_name" "$worktree_dir" {base_ref}
fi
git -C "$worktree_dir" config user.name 'open-swe[bot]'
git -C "$worktree_dir" config user.email 'open-swe@users.noreply.github.com'
git -C "$worktree_dir" status --short --branch
"""
