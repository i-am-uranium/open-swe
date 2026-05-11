"""Subscription-backed CLI agent execution for self-hosted OSS runtime."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import Any

from agent.utils.sandbox_paths import aresolve_sandbox_work_dir

CLI_AGENT_BACKENDS = {"codex_cli", "claude_code"}


def configured_agent_backend() -> str:
    return os.getenv("OPEN_SWE_AGENT_BACKEND", "langchain").strip().lower()


def using_cli_agent_backend() -> bool:
    return configured_agent_backend() in CLI_AGENT_BACKENDS


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, indent=2, sort_keys=True)


def _extract_task_text(input_payload: dict[str, Any]) -> str:
    messages = input_payload.get("messages") or []
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            parts.append(_message_content_to_text(message))
            continue
        role = message.get("role", "user")
        content = _message_content_to_text(message.get("content", ""))
        if content:
            parts.append(f"{role}: {content}")
    return "\n\n".join(parts).strip()


def build_cli_agent_prompt(
    *,
    input_payload: dict[str, Any],
    config: dict[str, Any],
    work_dir: str,
) -> str:
    configurable = dict(config.get("configurable") or {})
    repo = configurable.get("repo") or {}
    repo_slug = "unknown repository"
    if isinstance(repo, dict) and repo.get("owner") and repo.get("name"):
        repo_slug = f"{repo['owner']}/{repo['name']}"

    linear_issue = configurable.get("linear_issue") or {}
    linear_context = ""
    if isinstance(linear_issue, dict) and linear_issue:
        linear_context = "\n".join(
            f"- {key}: {value}" for key, value in sorted(linear_issue.items()) if value
        )

    task_text = _extract_task_text(input_payload) or "No task text was provided."
    return f"""You are running as the Open SWE autonomous coding agent.

Repository: {repo_slug}
Working directory: {work_dir}

Task:
{task_text}

Linear context:
{linear_context or "- none"}

Execution requirements:
- Inspect the repository and current task context before editing.
- Clone or fetch the repository if it is not already present in the working directory.
- Pull the latest default branch before creating a work branch.
- Never push directly to main or master.
- Never force push.
- Create a feature branch for the work.
- Make the smallest production-quality change that satisfies the task.
- Run the relevant tests or checks and include the results in your final response.
- Commit the change with a clear message.
- Push only the feature branch.
- Open a pull request, preferably draft if more human review is needed.
- Do not merge the pull request.
"""


def build_cli_agent_command(*, backend_name: str, prompt: str, work_dir: str) -> str:
    prompt_pipe = f"printf %s {shlex.quote(prompt)}"
    quoted_work_dir = shlex.quote(work_dir)

    if backend_name == "codex_cli":
        model = os.getenv("OPEN_SWE_CODEX_MODEL", "").strip()
        model_arg = f" --model {shlex.quote(model)}" if model else ""
        return (
            f"cd {quoted_work_dir} && {prompt_pipe} | "
            "codex exec "
            "--dangerously-bypass-approvals-and-sandbox "
            "--ask-for-approval never "
            "--sandbox danger-full-access"
            f"{model_arg} "
            f"--cd {quoted_work_dir} -"
        )

    if backend_name == "claude_code":
        model = os.getenv("OPEN_SWE_CLAUDE_MODEL", "").strip()
        model_arg = f" --model {shlex.quote(model)}" if model else ""
        max_turns = os.getenv("OPEN_SWE_CLI_MAX_TURNS", "100").strip() or "100"
        return (
            f"cd {quoted_work_dir} && {prompt_pipe} | "
            "claude -p "
            "--output-format stream-json "
            "--permission-mode bypassPermissions "
            f"--max-turns {shlex.quote(max_turns)}"
            f"{model_arg}"
        )

    raise ValueError(f"Unsupported CLI agent backend: {backend_name}")


async def run_cli_agent_backend(
    *,
    thread_id: str,
    input_payload: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Run a subscription-authenticated CLI agent inside the configured sandbox."""
    backend_name = configured_agent_backend()
    if backend_name not in CLI_AGENT_BACKENDS:
        raise ValueError(f"Not a CLI agent backend: {backend_name}")

    from agent import server
    from agent.utils.auth import resolve_github_token

    config.setdefault("metadata", {})
    github_token, new_encrypted, new_expires_at = await resolve_github_token(config, thread_id)
    config["metadata"]["github_token_encrypted"] = new_encrypted
    config["metadata"]["github_token_expires_at"] = new_expires_at

    sandbox_backend = await server.ensure_sandbox_for_thread(thread_id)
    await server._configure_sandbox_github_auth(sandbox_backend, github_token)  # noqa: SLF001
    del github_token

    work_dir = await aresolve_sandbox_work_dir(sandbox_backend)
    prompt = build_cli_agent_prompt(
        input_payload=input_payload,
        config=config,
        work_dir=work_dir,
    )
    command = build_cli_agent_command(
        backend_name=backend_name,
        prompt=prompt,
        work_dir=work_dir,
    )
    timeout = int(os.getenv("OPEN_SWE_CLI_TIMEOUT_SECONDS", "7200"))
    response = await asyncio.to_thread(sandbox_backend.execute, command, timeout=timeout)
    result = {
        "backend": backend_name,
        "exit_code": response.exit_code,
        "output": response.output,
    }
    if response.exit_code != 0:
        raise RuntimeError(f"{backend_name} failed with exit code {response.exit_code}: {response.output}")
    return result
