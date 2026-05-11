# Open SWE Production Manifests

This directory is a starting point for a self-hosted Open SWE controller running on Kubernetes.
It deploys one controller/webhook pod with the OSS runtime and a subscription-backed CLI agent.

## Apply Flow

1. Build and push an application image that contains:
   - this repository at `/app`
   - Python dependencies installed for `uv run`
   - `git`, `gh`, `codex`, and/or `claude`
   - Node.js for Codex and Claude Code CLIs
2. Replace `ghcr.io/your-org/open-swe:self-host-runtime` in `deployment.yaml`.
3. Replace `open-swe.example.com` in `ingress.yaml`.
4. Create a real `open-swe-secrets` secret. Do not apply `secret.example.yaml` as-is.
5. Create the namespace, config, service account, and PVC before seeding CLI auth:

```bash
kubectl apply -f infrastructure/prod/namespace.yaml
kubectl apply -f infrastructure/prod/service-account.yaml
kubectl apply -f infrastructure/prod/configmap.yaml
kubectl apply -f infrastructure/prod/pvc.yaml
```

6. Authenticate the dedicated subscription account into the PVC-backed home directory:
   - Codex: run `codex login --device-auth` with `CODEX_HOME=/home/openswe/.codex`
   - Claude: run `claude auth login` with `HOME=/home/openswe`
7. Optionally use `auth-bootstrap-pod.yaml` to seed CLI auth into the PVC:

```bash
kubectl apply -f infrastructure/prod/auth-bootstrap-pod.yaml
kubectl exec -n open-swe-prod -it open-swe-auth-bootstrap -- codex login --device-auth
kubectl exec -n open-swe-prod -it open-swe-auth-bootstrap -- codex login status
kubectl delete pod -n open-swe-prod open-swe-auth-bootstrap
```

For Claude Code, replace the two `codex` commands with:

```bash
kubectl exec -n open-swe-prod -it open-swe-auth-bootstrap -- claude auth login
kubectl exec -n open-swe-prod -it open-swe-auth-bootstrap -- claude auth status
```

8. Apply the workload manifests:

```bash
kubectl apply -k infrastructure/prod
```

## Runtime Defaults

The default config uses:

- `OPEN_SWE_RUNTIME=oss`
- `OPEN_SWE_AGENT_BACKEND=codex_cli`
- `OPEN_SWE_GITHUB_AUTH_MODE=github_app`
- `SANDBOX_TYPE=local`
- a single replica with `Recreate` rollout strategy
- one PVC mounted at `/home/openswe` and `/workspace/open-swe`

Keep `replicas: 1` until the OSS runtime state is moved out of process. Today, thread and run
state are in memory, and the PVC only preserves CLI auth, cloned repos, work directories, and logs.

## What Can Go Wrong Starting Fresh

- Image is incomplete: the current upstream Dockerfile is closer to a sandbox/tooling image than
  a production app image. The production image must include the app source, dependencies, and CLIs.
- Subscription auth is missing: Codex/Claude login state is interactive and must be pre-seeded into
  the mounted home directory. API keys are not a substitute for subscription mode.
- Horizontal scaling breaks work routing: multiple pods would each have separate in-memory runtime
  state and could duplicate or lose jobs.
- PVC access mode blocks rollout: `ReadWriteOnce` plus a rolling update can deadlock on some
  clusters. This manifest uses `Recreate` to avoid two pods mounting the same volume.
- Webhook retries can duplicate work: GitHub, Linear, and Slack retry failed or slow webhooks. The
  app needs durable idempotency before high-volume production use.
- CLI agents can exhaust subscription limits: long multi-repo tasks can consume large message
  budgets and then stall until the vendor usage window resets.
- Local sandbox is container-local, not hostile-code isolation: the agent can run arbitrary repo
  commands inside the controller pod. Use a dedicated cluster namespace, no cloud credentials beyond
  what is required, and strict GitHub branch protections.
- NetworkPolicy may be too broad or too narrow: outbound HTTPS and SSH are allowed for GitHub,
  Linear, Slack, OpenAI/Anthropic, package managers, and git remotes. Tighten once real endpoints
  are known.
- Secrets can leak through logs or prompts: keep GitHub App credentials in Kubernetes Secrets and
  avoid adding broad cloud provider credentials to the pod.
- Branch protection is still mandatory: the app blocks direct `main`/`master` pushes in local mode,
  but GitHub branch protection is the real production guard.
