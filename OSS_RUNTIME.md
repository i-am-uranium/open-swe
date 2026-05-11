# OSS Self-Hosted Runtime

This fork can run without LangGraph Cloud or the production LangGraph Agent Server by using
the in-process OSS runtime.

## Local Run

```bash
cd /Users/eren/ClinikkDev/backend/open-swe
uv sync --all-extras --dev

export OPEN_SWE_RUNTIME=oss
export OPEN_SWE_GITHUB_AUTH_MODE=github_app
export SANDBOX_TYPE=local
export TOKEN_ENCRYPTION_KEY="$(uv run python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)"

export OPENAI_API_KEY="..."
export GITHUB_APP_ID="..."
export GITHUB_APP_INSTALLATION_ID="..."
export GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----"

uv run uvicorn agent.webapp:app --host 0.0.0.0 --port 8000
```

## Subscription CLI Backends

The default backend is still the LangChain model path:

```bash
export OPEN_SWE_AGENT_BACKEND=langchain
export LLM_MODEL_ID="openai:gpt-5.5"
export OPENAI_API_KEY="..."
```

For dedicated subscription accounts, run through the vendor CLI instead of API keys.

### Codex Subscription

Authenticate the bot account once in the same user home that the service will use:

```bash
codex logout
codex login --device-auth
codex login status
```

Then run Open SWE with:

```bash
export OPEN_SWE_AGENT_BACKEND=codex_cli
export OPEN_SWE_RUNTIME=oss
export SANDBOX_TYPE=local
```

The runtime executes:

```bash
codex exec --dangerously-bypass-approvals-and-sandbox \
  --ask-for-approval never \
  --sandbox danger-full-access \
  --cd "$WORK_DIR" -
```

Optional:

```bash
export OPEN_SWE_CODEX_MODEL="gpt-5-codex"
```

### Claude Code Subscription

Authenticate the bot account once in the same user home that the service will use:

```bash
claude auth login
claude auth status
```

Do not set `ANTHROPIC_API_KEY` when you want Claude Code to use the subscription login.

Then run Open SWE with:

```bash
export OPEN_SWE_AGENT_BACKEND=claude_code
export OPEN_SWE_RUNTIME=oss
export SANDBOX_TYPE=local
```

The runtime executes:

```bash
claude -p \
  --output-format stream-json \
  --permission-mode bypassPermissions \
  --max-turns "${OPEN_SWE_CLI_MAX_TURNS:-100}"
```

Optional:

```bash
export OPEN_SWE_CLAUDE_MODEL="sonnet"
export OPEN_SWE_CLI_MAX_TURNS="100"
```

### Kubernetes State

For subscription-backed execution, mount a PVC as the bot user's home directory, or mount
provider-specific state directories into that home. At minimum, preserve:

- Codex auth/config state under the bot user's `CODEX_HOME` or `~/.codex`
- Claude Code auth/config state under the bot user's home
- Open SWE runtime state, task logs, and work directories

The GitHub App credentials should stay in Kubernetes Secrets. The GitHub installation token is
resolved at run time and injected into the sandbox as `GH_TOKEN` and `OPEN_SWE_GITHUB_TOKEN`.

## Direct Run Endpoint

```bash
curl -X POST http://127.0.0.1:8000/oss/runs \
  -H 'content-type: application/json' \
  -d '{
    "thread_id": "demo-1",
    "message": "Inspect the repo and make the requested change. Open a draft PR when done.",
    "repo": {"owner": "your-org", "name": "your-repo"}
  }'
```

Slack and Linear webhooks also dispatch through the OSS runtime when
`OPEN_SWE_RUNTIME=oss` is set.

## Safety Policy

The OSS local sandbox enforces hard command-level protections:

- refuses `git push` to `main` or `master`
- refuses force pushes
- refuses `gh pr merge`

This is in addition to prompt instructions. GitHub branch protection should still be enabled
on all production repositories.

## Production Direction

`SANDBOX_TYPE=local` is useful for proving the end-to-end flow but is not isolated enough for
production. The next production step is a Kubernetes sandbox provider that implements the same
Deep Agents sandbox protocol and runs each task in an isolated pod.
