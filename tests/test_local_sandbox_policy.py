from __future__ import annotations

from agent.integrations.local import create_local_sandbox


def test_local_sandbox_blocks_push_to_main(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", "/tmp")

    sandbox = create_local_sandbox()
    result = sandbox.execute("git push origin main")

    assert result.exit_code == 1
    assert "protected branch" in result.output


def test_local_sandbox_blocks_force_push(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", "/tmp")

    sandbox = create_local_sandbox()
    result = sandbox.execute("git push --force origin feature/test")

    assert result.exit_code == 1
    assert "force push" in result.output


def test_local_sandbox_blocks_pr_merge(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_SANDBOX_ROOT_DIR", "/tmp")

    sandbox = create_local_sandbox()
    result = sandbox.execute("GH_TOKEN=token gh pr merge 123 --merge")

    assert result.exit_code == 1
    assert "merge pull requests" in result.output
