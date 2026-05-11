from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_oss_runtime_runs_agent_without_langgraph_server(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.oss_runtime import OSSRuntime

    captured: dict[str, object] = {}

    class FakeAgent:
        async def ainvoke(self, input_payload: dict, config: dict) -> dict:
            captured["input"] = input_payload
            captured["config"] = config
            return {"ok": True}

    async def fake_get_agent(config: dict) -> FakeAgent:
        captured["factory_config"] = config
        return FakeAgent()

    monkeypatch.setattr("agent.server.get_agent", fake_get_agent)

    runtime = OSSRuntime()
    run = await runtime.create_run(
        thread_id="thread-1",
        graph_id="agent",
        input_payload={"messages": [{"role": "user", "content": "hello"}]},
        config={"configurable": {"source": "slack"}, "metadata": {"existing": "value"}},
        if_not_exists="create",
    )

    assert run["status"] == "completed"
    assert run["thread_id"] == "thread-1"
    assert run["run_id"]

    factory_config = captured["factory_config"]
    assert isinstance(factory_config, dict)
    assert factory_config["configurable"]["thread_id"] == "thread-1"
    assert factory_config["configurable"]["__is_for_execution__"] is True
    assert factory_config["metadata"] == {"existing": "value"}

    thread = await runtime.threads.get("thread-1")
    assert thread["status"] == "idle"
    assert thread["metadata"] == {"existing": "value"}


@pytest.mark.asyncio
async def test_oss_runtime_marks_thread_idle_after_agent_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.oss_runtime import OSSRuntime

    class FailingAgent:
        async def ainvoke(self, input_payload: dict, config: dict) -> dict:
            raise RuntimeError("boom")

    async def fake_get_agent(config: dict) -> FailingAgent:
        return FailingAgent()

    monkeypatch.setattr("agent.server.get_agent", fake_get_agent)

    runtime = OSSRuntime()

    with pytest.raises(RuntimeError, match="boom"):
        await runtime.create_run(
            thread_id="thread-1",
            graph_id="agent",
            input_payload={"messages": []},
            config={"configurable": {"source": "linear"}},
        )

    thread = await runtime.threads.get("thread-1")
    assert thread["status"] == "idle"
    runs = await runtime.runs.list("thread-1")
    assert runs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_webapp_create_run_uses_oss_runtime_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent import webapp

    fake_runtime = AsyncMock()
    fake_runtime.create_run = AsyncMock(return_value={"run_id": "run-1", "status": "completed"})

    monkeypatch.setenv("OPEN_SWE_RUNTIME", "oss")
    monkeypatch.setattr(webapp, "get_oss_runtime", lambda: fake_runtime)

    run = await webapp.create_agent_run(
        "thread-1",
        "agent",
        input_payload={"messages": [{"role": "user", "content": "hello"}]},
        config={"configurable": {"source": "slack"}},
        if_not_exists="create",
    )

    assert run == {"run_id": "run-1", "status": "completed"}
    fake_runtime.create_run.assert_awaited_once()


def test_oss_run_endpoint_dispatches_agent_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent import webapp

    async def fake_create_agent_run(
        thread_id: str,
        graph_id: str,
        *,
        input_payload: dict,
        config: dict,
        if_not_exists: str = "create",
    ) -> dict:
        assert thread_id == "thread-1"
        assert graph_id == "agent"
        assert input_payload["messages"][0]["role"] == "user"
        assert config["configurable"]["repo"] == {"owner": "acme", "name": "api"}
        assert config["configurable"]["source"] == "oss"
        assert if_not_exists == "create"
        return {"run_id": "run-1", "status": "completed"}

    monkeypatch.setenv("OPEN_SWE_RUNTIME", "oss")
    monkeypatch.setattr(webapp, "create_agent_run", fake_create_agent_run)

    client = TestClient(webapp.app)
    response = client.post(
        "/oss/runs",
        json={
            "thread_id": "thread-1",
            "message": "fix the health endpoint",
            "repo": {"owner": "acme", "name": "api"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"run_id": "run-1", "status": "completed"}
