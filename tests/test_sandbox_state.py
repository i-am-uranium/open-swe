from __future__ import annotations

import logging

import pytest

from agent.utils import sandbox_state


@pytest.mark.asyncio
async def test_get_sandbox_id_from_metadata_treats_missing_runnable_context_as_empty(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_get_config() -> dict:
        raise RuntimeError("Called get_config outside of a runnable context")

    monkeypatch.setattr(sandbox_state, "get_config", fake_get_config)

    with caplog.at_level(logging.WARNING):
        sandbox_id = await sandbox_state.get_sandbox_id_from_metadata("thread-1")

    assert sandbox_id is None
    assert "Failed to read thread metadata for sandbox" not in caplog.text


@pytest.mark.asyncio
async def test_get_sandbox_id_from_metadata_reads_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sandbox_state,
        "get_config",
        lambda: {"metadata": {"sandbox_id": "sandbox-1"}},
    )

    sandbox_id = await sandbox_state.get_sandbox_id_from_metadata("thread-1")

    assert sandbox_id == "sandbox-1"
