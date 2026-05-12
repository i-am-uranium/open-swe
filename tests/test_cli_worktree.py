from __future__ import annotations

import pytest
from deepagents.backends.protocol import ExecuteResponse


class _FakeSandboxBackend:
    def __init__(self, *, exit_code: int = 0, output: str = "") -> None:
        self.exit_code = exit_code
        self.output = output
        self.commands: list[str] = []

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del timeout
        self.commands.append(command)
        return ExecuteResponse(output=self.output, exit_code=self.exit_code, truncated=False)


def test_prepare_cli_worktree_uses_unique_path_and_pr_base_ref() -> None:
    from agent.utils.worktree import prepare_cli_worktree

    backend = _FakeSandboxBackend()

    first = prepare_cli_worktree(
        backend,
        base_work_dir="/workspace/open-swe/work",
        repo_config={"owner": "clinikk", "name": "subscription-service"},
        run_id="run-one",
        task_text="Please revise https://github.com/clinikk/subscription-service/pull/119",
    )
    second = prepare_cli_worktree(
        backend,
        base_work_dir="/workspace/open-swe/work",
        repo_config={"owner": "clinikk", "name": "subscription-service"},
        run_id="run-two",
        task_text="Please revise https://github.com/clinikk/subscription-service/pull/119",
    )

    assert first.path == "/workspace/open-swe/work/worktrees/run-one/subscription-service"
    assert second.path == "/workspace/open-swe/work/worktrees/run-two/subscription-service"
    assert first.path != second.path
    assert first.branch == "open-swe/subscription-service-run-one"
    assert second.branch == "open-swe/subscription-service-run-two"

    first_command = backend.commands[0]
    second_command = backend.commands[1]
    assert "gh repo clone" not in first_command
    assert "clone_url=https://github.com/clinikk/subscription-service.git" in first_command
    assert (
        'git -c "http.https://github.com/.extraheader=$git_auth_header" '
        'clone "$clone_url" "$source_dir"'
    ) in first_command
    assert "OPEN_SWE_GITHUB_TOKEN or GH_TOKEN is required" in first_command
    assert "+pull/119/head:refs/remotes/origin/pr-119" in first_command
    assert "refs/remotes/origin/pr-119" in first_command
    assert "/workspace/open-swe/work/repos/clinikk__subscription-service" in first_command
    assert "/workspace/open-swe/work/worktrees/run-one/subscription-service" in first_command
    assert "/workspace/open-swe/work/worktrees/run-two/subscription-service" in second_command


def test_prepare_cli_worktree_supports_owner_repo_pr_shorthand() -> None:
    from agent.utils.worktree import prepare_cli_worktree

    backend = _FakeSandboxBackend()

    prepare_cli_worktree(
        backend,
        base_work_dir="/workspace/open-swe/work",
        repo_config={"owner": "clinikk", "name": "subscription-service"},
        run_id="run-one",
        task_text="In clinikk/subscription-service#119, fix tests",
    )

    assert "+pull/119/head:refs/remotes/origin/pr-119" in backend.commands[0]


def test_prepare_cli_worktree_raises_when_setup_fails() -> None:
    from agent.utils.worktree import prepare_cli_worktree

    backend = _FakeSandboxBackend(exit_code=1, output="clone failed")

    with pytest.raises(RuntimeError, match="Failed to prepare CLI worktree"):
        prepare_cli_worktree(
            backend,
            base_work_dir="/workspace/open-swe/work",
            repo_config={"owner": "clinikk", "name": "subscription-service"},
            run_id="run-one",
            task_text="Fix the issue",
        )
