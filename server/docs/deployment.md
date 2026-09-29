# Auto Browser Deployment Guide

Native only: run with `scripts/start-local.ps1` (data under `.local-data/<port>/`).

This is the recommended deployment shape for a **single-tenant, trusted-operator** production install.

## Recommended topology

- Auto Browser controller + browser node on one private host
- Front the controller and takeover UI with **Cloudflare Access** or **Tailscale**
- Keep published ports bound to `127.0.0.1`
- Use native `shared_browser_node` session mode via `scripts/start-local.ps1`

## Required production settings

At minimum:

```env
APP_ENV=production
API_BIND_SCOPE=exposed
API_BEARER_TOKEN=<strong-random-secret>
REQUIRE_OPERATOR_ID=true
AUTH_STATE_ENCRYPTION_KEY=<44-char-fernet-key>
REQUIRE_AUTH_STATE_ENCRYPTION=true
REQUEST_RATE_LIMIT_ENABLED=true
METRICS_ENABLED=true
CONTROLLER_ALLOWED_HOSTS=<controller-ingress-hosts>
```

Strongly recommended:

```env
SESSION_ISOLATION_MODE=shared_browser_node
MAX_SESSIONS=1
ALLOWED_HOSTS=<your-real-allowlist>
STATE_DB_PATH=/data/db/operator.db
ARTIFACT_RETENTION_HOURS=168
UPLOAD_RETENTION_HOURS=168
AUTH_RETENTION_HOURS=168
```

`CONTROLLER_ALLOWED_HOSTS` protects the controller itself from unexpected HTTP Host headers.
Keep `ALLOWED_HOSTS` for browser navigation targets, and set `CONTROLLER_ALLOWED_HOSTS`
to the hostnames operators use to reach the controller, such as `browser.example.com`
or `localhost,127.0.0.1,::1` for a local-only install.

When it is unset and the controller runs without a bearer credential (a loopback
deployment), only loopback Host names — `localhost`, `127.0.0.1`, `[::1]` — are
answered. An unauthenticated API that accepts any Host header can be driven by a web
page through DNS rebinding, so this default holds until you either list the names
clients use or configure `API_BEARER_TOKEN`. `/healthz` is exempt.

## Auth profiles

Auto Browser now supports reusable named auth profiles under:

```text
/data/auth/profiles/<profile-name>/
```

Use them when you want a human to log in once and let future sessions resume from saved browser state without passing raw storage-state file paths around.

Recommended pattern:
- use one profile per account/workflow
- keep auth-state encryption enabled in production
- treat profile names as operator-facing labels, not secrets

## Provider authentication choices

You now have two viable ways to authenticate model providers:

### Option A — API keys

Use:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

This is still the cleanest option for CI and broadly automated installs.

### Option B — subscription-backed CLIs

Use this on a trusted private box if you already run:

- `codex` via ChatGPT/Codex login
- `claude` via Claude Code login/subscription
- `gemini` via Gemini CLI login

Set:

```env
OPENAI_AUTH_MODE=cli
CLAUDE_AUTH_MODE=cli
GEMINI_AUTH_MODE=cli
CLI_HOME=/data/cli-home
```

Then copy the signed-in CLI state into the mounted data directory:

```bash
mkdir -p data/cli-home
rsync -a ~/.codex data/cli-home/.codex
cp ~/.claude.json data/cli-home/.claude.json
rsync -a ~/.claude data/cli-home/.claude
rsync -a ~/.gemini data/cli-home/.gemini
```

Treat `data/cli-home` like a password vault. Never commit it.

If the easiest path is to sign in on the target box directly, use:

```bash
./scripts/bootstrap_cli_auth.sh codex
./scripts/bootstrap_cli_auth.sh claude
./scripts/bootstrap_cli_auth.sh gemini
```

That helper opens the provider CLI on the host with `HOME=$CLI_HOME`, so the resulting login state lands where `*_AUTH_MODE=cli` expects it.

If the target machine already has those subscription logins locally, prefer the host-mount override instead of copying caches:

Native only: start with `.\scripts\start-local.ps1`
(data under `.local-data/<port>/`), sign in on the host, and point `CLI_HOME`
at the host login state. Do not use `bootstrap_cli_auth.sh` with a host-style home;
sign in on the host first and then start with `scripts/start-local.ps1`.

If Codex subscription auth still fails on the host, switch only OpenAI to the host bridge:

```bash
mkdir -p data/host-bridge
python3 scripts/codex_host_bridge.py --socket-path data/host-bridge/codex.sock
```

To keep that bridge running like a host-local skill, install the included user-service template:

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/codex-host-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now codex-host-bridge.service
```

Then:

```env
OPENAI_AUTH_MODE=host_bridge
OPENAI_HOST_BRIDGE_SOCKET=/data/host-bridge/codex.sock
```

That keeps `codex` on the host, reuses the host login state directly, and lets the native controller call it over a shared Unix socket.
The controller now health-checks that socket and the bridge kills stuck host `codex` jobs after 55 seconds by default.
Treat the socket as a host-trust boundary: any local process that can connect to it can trigger host-side `codex exec`.

In `APP_ENV=production`, startup now fails fast if:
- any `*_AUTH_MODE` value is not one of its supported modes (`api`, `cli`, and for OpenAI also `host_bridge`)
- a provider is set to `cli` mode but its CLI binary is missing
- OpenAI is set to `host_bridge` mode but the bridge socket is missing, stale, not a real Unix socket, or failing `/healthz`
- `CLI_HOME` is set but the expected auth-state files are missing for that CLI

## Generate an auth-state encryption key

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

## Local/private production run

```powershell
cp .env.example .env
# edit .env with the required production values above
.\scripts\start-local.ps1
# data lives under .local-data/<port>/ for native runs
```

## Health and readiness checks

```bash
curl -fsS http://127.0.0.1:18500/healthz | jq
curl -fsS http://127.0.0.1:18500/readyz | jq
curl -fsS http://127.0.0.1:18500/metrics | head
curl -fsS http://127.0.0.1:18500/maintenance/status | jq
```

If `METRICS_ENABLED=false`, skip the `/metrics` check; the endpoint returns `404`.

## Common pitfalls and failure modes

### Browser session dies or Chromium crashes

- recreate the session first; do not assume browser state is still valid
- check controller logs and browser-node logs before retrying the same action loop
- inspect the latest artifacts/screenshots to confirm where the flow broke

### Saved auth profile stops working

- the site may have expired cookies, revoked the session, or triggered MFA again
- recreate the profile with a fresh manual login
- avoid reusing one profile across multiple unrelated accounts or workflows

### noVNC works locally but not remotely

- keep controller and noVNC ports bound to `127.0.0.1`
- verify your access layer first: Cloudflare Access, Tailscale, or reverse tunnel
- if remote takeover breaks, treat it as a gateway/tunnel problem before debugging Playwright

### Production boot fails closed

- this is intentional in `APP_ENV=production`
- check required env vars first: bearer token, operator ID enforcement, encryption key, rate limiting
- if using `*_AUTH_MODE=cli` or `host_bridge`, verify the expected auth files or socket actually exist

### Actions fail after redirects or external handoffs

- update `ALLOWED_HOSTS` to include the real target domains involved in login, redirects, uploads, and downloads
- remember that identity providers, CDNs, and file hosts may differ from the main app domain

### OCR output looks incomplete or wrong

- Tesseract OCR is helpful, not authoritative
- use screenshots and DOM observations as the primary source of truth
- expect worse OCR quality on small text, low-contrast UIs, and dense dashboards

## Gateway recommendations

Use **one** of:

- **Cloudflare Access** in front of the controller + noVNC paths
- **Tailscale** and keep the whole stack private
- the included reverse-SSH path for bastion-style access when direct reachability is not available

Do **not** expose raw controller or noVNC ports directly to the public internet.

`VNC_PASSWORD` adds VNC authentication to noVNC (6080) and raw VNC (5900) on the
native shared browser node; noVNC prompts for it. Set it
whenever those ports are reachable beyond loopback — but treat it as a second layer,
not the gateway: the VNC protocol uses only the first 8 characters and a
DES-based challenge.

Native only: the browser runs as a host-local Chromium launched by the controller
via `scripts/start-local.ps1`. Keep controller and takeover ports bound to
`127.0.0.1` and put Cloudflare Access or Tailscale in front for remote use.

## Backups

Back up at least:

- `/data/db/` if using SQLite
- `/data/sessions/`
- `/data/jobs/`
- `/data/auth/` if you intentionally keep reusable auth state
- `/data/audit/`

## Cleanup

The controller can now prune stale artifacts/uploads/auth-state automatically.

Manual run:

```bash
curl -s http://127.0.0.1:18500/maintenance/cleanup \
  -X POST \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -H 'X-Operator-Id: ops' | jq
```

## Credential handoff checklist

Before live debugging, gather:

- OpenAI / Anthropic / Gemini API keys, or populated CLI auth caches under `data/cli-home`
- gateway credentials (Cloudflare Access or Tailscale)
- bastion SSH details if using reverse tunnels
- operator identity convention (`X-Operator-Id` values)
- allowlisted target hosts/domains

## First live-debug session

1. Bring the stack up privately
2. Verify `/readyz`
3. Verify `/metrics` (unless `METRICS_ENABLED=false`)
4. Create one session against a non-sensitive site
5. Verify observe/click/type flow
6. Add real creds
7. Test one real target workflow with human takeover ready
