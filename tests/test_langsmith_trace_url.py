from __future__ import annotations

import logging

from agent.utils.langsmith import get_langsmith_trace_url


def test_get_langsmith_trace_url_returns_none_without_project_env(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.delenv("LANGSMITH_TENANT_ID_PROD", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING_PROJECT_ID_PROD", raising=False)

    with caplog.at_level(logging.WARNING):
        trace_url = get_langsmith_trace_url("thread-1")

    assert trace_url is None
    assert "Failed to build LangSmith trace URL" not in caplog.text


def test_get_langsmith_trace_url_builds_thread_url(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_URL_PROD", "https://smith.example.test")
    monkeypatch.setenv("LANGSMITH_TENANT_ID_PROD", "tenant-1")
    monkeypatch.setenv("LANGSMITH_TRACING_PROJECT_ID_PROD", "project-1")

    trace_url = get_langsmith_trace_url("thread-1")

    assert trace_url == "https://smith.example.test/o/tenant-1/projects/p/project-1/t/thread-1"
