from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from deepagents.backends.protocol import ExecuteResponse


def test_codex_cli_command_reads_prompt_from_stdin() -> None:
    from agent.cli_agent_backend import build_cli_agent_command

    command = build_cli_agent_command(
        backend_name="codex_cli",
        prompt="Fix the bug",
        work_dir="/workspace/repo",
    )

    assert "printf %s" in command
    assert "codex exec" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--sandbox danger-full-access" in command
    assert "--cd /workspace/repo" in command
    assert command.endswith(" -")


def test_claude_code_command_uses_non_interactive_print_mode() -> None:
    from agent.cli_agent_backend import build_cli_agent_command

    command = build_cli_agent_command(
        backend_name="claude_code",
        prompt="Fix the bug",
        work_dir="/workspace/repo",
    )

    assert "printf %s" in command
    assert "claude -p" in command
    assert "--output-format stream-json" in command
    assert "--permission-mode bypassPermissions" in command
    assert "--max-turns 100" in command
    assert command.startswith("cd /workspace/repo &&")


def test_cli_agent_prompt_contains_repo_task_and_branch_policy() -> None:
    from agent.cli_agent_backend import build_cli_agent_prompt

    prompt = build_cli_agent_prompt(
        input_payload={"messages": [{"role": "user", "content": "Add retries to webhook sync"}]},
        config={"configurable": {"repo": {"owner": "acme", "name": "api"}}},
        work_dir="/workspace",
    )

    assert "acme/api" in prompt
    assert "Add retries to webhook sync" in prompt
    assert "Never push directly to main or master" in prompt
    assert "Open a pull request" in prompt


@pytest.mark.asyncio
async def test_oss_runtime_dispatches_cli_backend_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.oss_runtime import OSSRuntime

    cli_runner = AsyncMock(return_value={"exit_code": 0, "output": "created PR"})

    async def fail_get_agent(config: dict) -> object:
        raise AssertionError("LangChain agent should not be used for CLI backend")

    monkeypatch.setenv("OPEN_SWE_AGENT_BACKEND", "codex_cli")
    monkeypatch.setattr("agent.cli_agent_backend.run_cli_agent_backend", cli_runner)
    monkeypatch.setattr("agent.server.get_agent", fail_get_agent)

    runtime = OSSRuntime()
    run = await runtime.create_run(
        thread_id="thread-1",
        graph_id="agent",
        input_payload={"messages": [{"role": "user", "content": "fix webhook sync"}]},
        config={"configurable": {"repo": {"owner": "acme", "name": "api"}}},
    )

    assert run["status"] == "completed"
    assert run["result"] == {"exit_code": 0, "output": "created PR"}
    cli_runner.assert_awaited_once()
    cli_config = cli_runner.await_args.kwargs["config"]
    assert cli_config["configurable"]["run_id"] == run["run_id"]


@pytest.mark.asyncio
async def test_cli_backend_runs_inside_prepared_worktree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.cli_agent_backend import run_cli_agent_backend
    from agent.utils.worktree import WorktreeInfo

    captured: dict[str, object] = {}

    class FakeSandbox:
        def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
            captured["command"] = command
            captured["timeout"] = timeout
            return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    async def fake_prepare_worktree(
        sandbox_backend: object,
        *,
        base_work_dir: str,
        repo_config: dict[str, str],
        run_id: str,
        task_text: str,
    ) -> WorktreeInfo:
        captured["sandbox_backend"] = sandbox_backend
        captured["base_work_dir"] = base_work_dir
        captured["repo_config"] = repo_config
        captured["run_id"] = run_id
        captured["task_text"] = task_text
        return WorktreeInfo(
            path="/workspace/open-swe/work/worktrees/run-1/subscription-service",
            branch="open-swe/subscription-service-run-1",
            source_dir="/workspace/open-swe/work/repos/clinikk__subscription-service",
            pr_number=119,
        )

    fake_sandbox = FakeSandbox()
    monkeypatch.setenv("OPEN_SWE_AGENT_BACKEND", "codex_cli")
    monkeypatch.setattr(
        "agent.utils.auth.resolve_github_token",
        AsyncMock(return_value=("token", "encrypted", "expires")),
    )
    monkeypatch.setattr(
        "agent.server.ensure_sandbox_for_thread", AsyncMock(return_value=fake_sandbox)
    )
    monkeypatch.setattr("agent.server._configure_sandbox_github_auth", AsyncMock())
    monkeypatch.setattr(
        "agent.cli_agent_backend.aresolve_sandbox_work_dir",
        AsyncMock(return_value="/workspace/open-swe/work"),
    )
    monkeypatch.setattr(
        "agent.cli_agent_backend.aprepare_cli_worktree",
        fake_prepare_worktree,
        raising=False,
    )

    result = await run_cli_agent_backend(
        thread_id="thread-1",
        input_payload={
            "messages": [
                {
                    "role": "user",
                    "content": "Revise https://github.com/clinikk/subscription-service/pull/119",
                }
            ]
        },
        config={
            "configurable": {
                "run_id": "run-1",
                "repo": {"owner": "clinikk", "name": "subscription-service"},
            }
        },
    )

    assert result["exit_code"] == 0
    assert captured["base_work_dir"] == "/workspace/open-swe/work"
    assert captured["repo_config"] == {"owner": "clinikk", "name": "subscription-service"}
    assert captured["run_id"] == "run-1"
    assert "subscription-service/pull/119" in str(captured["task_text"])
    command = str(captured["command"])
    assert "--cd /workspace/open-swe/work/worktrees/run-1/subscription-service" in command
    assert "Branch prepared for this run: open-swe/subscription-service-run-1" in command
