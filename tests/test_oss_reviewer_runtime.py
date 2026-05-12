from __future__ import annotations

import pytest

from agent.utils.slack import GitHubPrRef


@pytest.mark.asyncio
async def test_pr_review_command_uses_oss_runtime_without_langgraph_client(monkeypatch) -> None:
    from agent import webapp

    captured: dict[str, object] = {}

    class FakeThreads:
        async def create(self, thread_id: str, *, if_exists: str, metadata=None) -> dict:
            captured["created_thread_id"] = thread_id
            captured["if_exists"] = if_exists
            return {"thread_id": thread_id, "metadata": metadata or {}}

    class FakeRuntime:
        threads = FakeThreads()

    async def fake_fetch_metadata(pr_ref: GitHubPrRef, *, token: str) -> dict[str, object]:
        return {
            "title": "Test PR",
            "html_url": pr_ref.url,
            "base": {"sha": "base-sha", "ref": "main"},
            "head": {"sha": "head-sha", "ref": "feature-branch"},
        }

    async def fake_create_agent_run(
        thread_id: str,
        graph_id: str,
        *,
        input_payload: dict,
        config: dict,
        if_not_exists: str = "create",
    ) -> dict:
        captured["run"] = {
            "thread_id": thread_id,
            "graph_id": graph_id,
            "input_payload": input_payload,
            "config": config,
            "if_not_exists": if_not_exists,
        }
        return {"run_id": "run-1", "status": "completed"}

    def fail_get_client(*_args, **_kwargs):
        raise AssertionError("OSS reviewer path must not call LangGraph SDK client")

    monkeypatch.setenv("OPEN_SWE_RUNTIME", "oss")
    monkeypatch.setattr(webapp, "get_oss_runtime", lambda: FakeRuntime())
    monkeypatch.setattr(webapp, "get_client", fail_get_client)
    monkeypatch.setattr(webapp, "ALLOWED_REVIEWER_GITHUB_REPOS", frozenset())
    monkeypatch.setattr(webapp, "ALLOWED_REVIEWER_GITHUB_ORGS", frozenset())
    monkeypatch.setattr(
        webapp,
        "get_github_app_installation_token_with_expiry",
        lambda: _async_return(("app-token", None)),
    )
    monkeypatch.setattr(webapp, "fetch_github_pr_metadata", fake_fetch_metadata)
    monkeypatch.setattr(webapp, "persist_encrypted_github_token", lambda *a, **k: _async_return(""))
    monkeypatch.setattr(webapp, "set_reviewer_thread_metadata", lambda *a, **k: _async_return(None))
    monkeypatch.setattr(webapp, "is_thread_active", lambda *_a, **_k: _async_return(False))
    monkeypatch.setattr(webapp, "create_agent_run", fake_create_agent_run)

    result = await webapp.trigger_pr_review_from_ref(
        GitHubPrRef(
            owner="clinikk",
            repo="subscription-service",
            number=120,
            url="https://github.com/clinikk/subscription-service/pull/120",
        ),
        source="github",
        github_login="clkravi",
        github_user_id=123,
    )

    assert result["success"] is True
    assert captured["created_thread_id"]
    run = captured["run"]
    assert run["graph_id"] == "reviewer"
    assert run["if_not_exists"] == "create"
    assert run["config"]["configurable"]["repo"] == {
        "owner": "clinikk",
        "name": "subscription-service",
    }


async def _async_return(value):
    return value
