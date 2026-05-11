import os
import re

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

_PROTECTED_BRANCH_PUSH_RE = re.compile(
    r"\bgit\s+push\b[^\n;&|]*(?:\brefs/heads/)?(?:main|master)\b"
)
_FORCE_PUSH_RE = re.compile(r"\bgit\s+push\b[^\n;&|]*(?:--force(?:-with-lease)?|\s-f(?:\s|$))")
_GH_PR_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")


class GuardedLocalShellBackend(LocalShellBackend):
    """Local shell backend with hard git safety policy for OSS runtime."""

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if _PROTECTED_BRANCH_PUSH_RE.search(command):
            return ExecuteResponse(
                output="Blocked by Open SWE policy: refusing to push to protected branch main/master.",
                exit_code=1,
                truncated=False,
            )
        if _FORCE_PUSH_RE.search(command):
            return ExecuteResponse(
                output="Blocked by Open SWE policy: refusing to force push.",
                exit_code=1,
                truncated=False,
            )
        if _GH_PR_MERGE_RE.search(command):
            return ExecuteResponse(
                output="Blocked by Open SWE policy: refusing to merge pull requests.",
                exit_code=1,
                truncated=False,
            )
        return super().execute(command, timeout=timeout)


def create_local_sandbox(sandbox_id: str | None = None):
    """Create a local shell sandbox with no isolation.

    WARNING: This runs commands directly on the host machine with no sandboxing.
    Only use for local development with human-in-the-loop enabled.

    The root directory defaults to the current working directory and can be
    overridden via the LOCAL_SANDBOX_ROOT_DIR environment variable.

    Args:
        sandbox_id: Ignored for local sandboxes; accepted for interface compatibility.

    Returns:
        LocalShellBackend instance implementing SandboxBackendProtocol.
    """
    root_dir = os.getenv("LOCAL_SANDBOX_ROOT_DIR", os.getcwd())

    return GuardedLocalShellBackend(
        root_dir=root_dir,
        inherit_env=True,
        virtual_mode=False,
    )
