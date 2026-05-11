from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_github_app_auth_mode_does_not_require_langsmith(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.utils import auth

    async def fake_installation_token() -> tuple[str, str]:
        return "ghs_installation", "2026-05-11T08:00:00Z"

    persisted: dict[str, str | None] = {}

    async def fake_persist(thread_id: str, token: str, expires_at: str | None = None) -> str:
        persisted["thread_id"] = thread_id
        persisted["token"] = token
        persisted["expires_at"] = expires_at
        return "encrypted-token"

    monkeypatch.setenv("OPEN_SWE_GITHUB_AUTH_MODE", "github_app")
    monkeypatch.delenv("LANGSMITH_API_KEY_PROD", raising=False)
    monkeypatch.setattr(auth, "get_github_app_installation_token_with_expiry", fake_installation_token)
    monkeypatch.setattr(auth, "persist_encrypted_github_token", fake_persist)

    token, encrypted, expires_at = await auth.resolve_github_token(
        {"configurable": {"source": "linear"}, "metadata": {}},
        "thread-1",
    )

    assert token == "ghs_installation"
    assert encrypted == "encrypted-token"
    assert expires_at == "2026-05-11T08:00:00Z"
    assert persisted == {
        "thread_id": "thread-1",
        "token": "ghs_installation",
        "expires_at": "2026-05-11T08:00:00Z",
    }


def test_prompt_uses_real_github_token_env_for_non_langsmith_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.prompt import construct_system_prompt

    monkeypatch.setenv("SANDBOX_TYPE", "local")

    prompt = construct_system_prompt(working_dir="/workspace")

    assert 'GH_TOKEN="$OPEN_SWE_GITHUB_TOKEN" gh' in prompt
    assert "GH_TOKEN=dummy gh" not in prompt


def test_prompt_uses_dummy_github_token_for_langsmith_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.prompt import construct_system_prompt

    monkeypatch.setenv("SANDBOX_TYPE", "langsmith")

    prompt = construct_system_prompt(working_dir="/workspace")

    assert "GH_TOKEN=dummy gh" in prompt
