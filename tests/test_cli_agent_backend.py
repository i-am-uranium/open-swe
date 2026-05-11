from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


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
    assert "--ask-for-approval never" in command
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
