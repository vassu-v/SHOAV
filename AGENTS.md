# Set up SHOAV for your agent

S.H.O.A.V. is a browser MCP server with a deterministic guard in the path, plus a skill for agents that keep their own
browser. This page is for humans and for agents. Any agent that can call an MCP tool over HTTP can use it (Claude Code,
OpenCode, Antigravity CLI `agy`, Codex, Cursor, others).

## What you get

- **MCP** (`--what mcp`): a real Chromium the agent drives through `browser_*` tools, with the guard rewriting or blocking
  hostile content on the way in and unsafe clicks and submits on the way out. A live view lets you watch every session.
  Also installs the `shoav-guide` skill, which teaches the agent how to start and drive the MCP.
- **Skills** (`--what skill`): the `shoav` defence skill (a defence manual and audit scripts, advice only, nothing is
  enforced) plus the `shoav-guide` skill. No MCP config.
- **Both** (default, recommended): enforcement plus advice for the wording tricks a structural check cannot see.

## 60 second setup

Requirements: Python 3.11+, Node.js 18+. Run these in the folder your agent works in.

```bash
npx github:vassu-v/SHOAV                       # interactive installer
# or from a clone
git clone https://github.com/vassu-v/SHOAV && cd SHOAV && node cli/bin/shoav.js
```

Non-interactive examples (add `--dir <path>` to target another folder, `--dry-run` to preview):

```bash
npx github:vassu-v/SHOAV install --what both --agent claude   --yes   # Claude Code
npx github:vassu-v/SHOAV install --what both --agent opencode --yes   # OpenCode
npx github:vassu-v/SHOAV install --what both --agent agy      --yes   # Antigravity CLI
npx github:vassu-v/SHOAV install --what mcp  --agent codex    --yes   # Codex
npx github:vassu-v/SHOAV install --what both --agent cursor   --yes   # Cursor
npx github:vassu-v/SHOAV install --what both --agent claude,cursor --guard observe --yes
```

Then start the server and run your agent in that folder:

```bash
shoav start --ui          # first run creates a venv in ~/.shoav, installs dependencies and Chromium
shoav status
```

If `shoav` is not on your PATH, use `npx github:vassu-v/SHOAV start --ui` or `node cli/bin/shoav.js start --ui` from a clone.

Install options: `--what skill|mcp|both`, `--agent claude,opencode,agy,codex,cursor,generic`, `--scope project|user`
(default project), `--dir <path>`, `--url <mcp url>` (default `http://127.0.0.1:18500/mcp`), `--guard off|observe|enforce`
(default enforce), `--yes`, `--dry-run`. See [`cli/README.md`](cli/README.md).

## Scoping to one directory

With `--scope project` (the default) everything is written inside the target directory, so only agents run in that folder
get SHOAV, and nothing global is touched. Files created per agent:

| Agent | Files |
|---|---|
| Claude Code | `.mcp.json`, `.claude/settings.json` (allow rule `mcp__shoav`), `CLAUDE.md` containing `@AGENTS.md`, skills in `.claude/skills/shoav-guide` and `.claude/skills/shoav` |
| OpenCode | `opencode.json`, skills in `.opencode/skills/` |
| agy | `.agents/mcp_config.json`, skills in `.agents/skills/shoav-guide` and `.agents/skills/shoav` |
| Codex | `AGENTS.md`, plus a printed `codex mcp add shoav --url ...` command to run yourself (best effort, depends on your Codex version) |
| Cursor | `.cursor/mcp.json`, skills in `.cursor/skills/`, and a rule file |
| generic | `AGENTS.md` and a JSON snippet to paste into your client |

For the MCP part the installer also appends an idempotent "Browsing with SHOAV" block to the project's `AGENTS.md`. It tells
the agent to use the `shoav` tools for all browsing and how to read verdicts. Re-running the install does not duplicate it.

## Running it

| Command | What it does |
|---|---|
| `shoav start [--guard m] [--port 18500] [--headless] [--ui] [--yes]` | Start the server. `--ui` also starts the live view |
| `shoav stop` | Stop it |
| `shoav status` | Show whether it is up |
| `shoav events <sid>` | Print the events of one session |
| `shoav open [sid]` | Open the live view, optionally for one session |
| `shoav doctor` | Check Python, Node, Chromium, ports and config |

Ports: controller `18500`, live view `3200`, test fixtures `186xx`. Never use 8000, 3100 or 18480, those belong to upstream
defaults and other tools.

| URL | What |
|---|---|
| `http://127.0.0.1:18500/mcp` | MCP endpoint |
| `http://127.0.0.1:18500/healthz` | Health |
| `http://127.0.0.1:18500/live-api/guard` | Guard mode and counters |
| `http://127.0.0.1:3200/s/<session_id>` | Live view for a session |

### Guard modes

| Mode | Behaviour | Use it for |
|---|---|---|
| `off` | No guard | Comparing behaviour with and without SHOAV |
| `observe` | Checks run and are logged, nothing changes | Trying it on your own tasks without risking broken flows |
| `enforce` | Rewrites and blocks apply | Real use. This is the default |

A crashing filter fails open unless the server has `SHOAV_GUARD_FAIL=closed`.

## What the agent sees

Typical loop: `browser_create_session`, then `browser_observe` or `browser_snapshot`, then `browser_execute_action`. Every
session result carries a watch link.

| Verdict | What comes back |
|---|---|
| ALLOW | The normal result. |
| REWRITE | The normal result with dangerous text removed and a leading `_shoav` note (`verdict`, `findings`, `summary`). Carry on with the cleaned content. |
| BLOCK | `isError: true`. The `error` says what was in the way, for example an invisible layer over the button. Do not retry the click. Re-observe the page, or ask for human takeover. |
| ESCALATE | `isError: true`. Suspicious but not provable, for example a form submitted with an untouched pre-ticked consent box. Re-observe the form, tick or untick it on purpose, or ask a human. |

The human sees each tool call as a row in the live view, with a badge (REWRITE amber, BLOCK red, ESCALATE orange). Expand a row
for the reason and findings. After `browser_close_session` the same link is a read-only archive.

Tool profiles: 37 curated tools by default, 74 full, 10 minimal (`MCP_TOOL_PROFILE=minimal` on the server). Tool names use
underscores because some clients, such as `agy`, reject dotted names.

## Manual setup without the CLI

Start the server first (see [Linux and macOS](#linux-and-macos) or [`server/SHOAV.md`](server/SHOAV.md)). On Windows, from `server\`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
```

Then register the MCP.

**Claude Code**, plain command:

```bash
claude mcp add --transport http shoav http://127.0.0.1:18500/mcp
```

or `.mcp.json`:

```json
{ "mcpServers": { "shoav": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```

and `.claude/settings.json` so tool calls are not prompted one by one:

```json
{ "permissions": { "allow": ["mcp__shoav"] } }
```

**OpenCode**, `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": { "shoav": { "type": "remote", "url": "http://127.0.0.1:18500/mcp", "enabled": true } }
}
```

**agy**, plain command:

```bash
agy mcp add --type http shoav http://127.0.0.1:18500/mcp
```

or `.agents/mcp_config.json`:

```json
{ "mcpServers": { "shoav": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```

**Cursor**, `.cursor/mcp.json`:

```json
{ "mcpServers": { "shoav": { "url": "http://127.0.0.1:18500/mcp" } } }
```

**Codex** (best effort, depends on your version):

```bash
codex mcp add shoav --url http://127.0.0.1:18500/mcp
```

Config file formats change between client versions. If one of these is rejected, check your client's MCP docs and use the
same URL. To also install the skills by hand, copy [`skills/guide/`](skills/guide/SKILL.md) as `shoav-guide` and
[`skills/defense/`](skills/defense/README.md) as `shoav` into the agent's skills directory (see [`skills/README.md`](skills/README.md)).

## Linux and macOS

There is no PowerShell script to run. Use the CLI (`shoav start --ui`), or start the controller directly:

```bash
cd server/controller
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
SHOAV_GUARD_MODE=enforce MCP_TOOL_NAME_STYLE=underscore ALLOWED_HOSTS='*' \n  API_BIND_SCOPE=loopback LIVE_UI_BASE_URL=http://127.0.0.1:3200 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 18500
```

The live view, in a second terminal: `cd server/live-ui && npm install && npm run build && npm start`. On a headless Linux
box add `HEADLESS=true`. More in [`server/SHOAV.md`](server/SHOAV.md).

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| Agent says the server is not reachable | The server is not running. Run `shoav status`, then `shoav start`. Check `curl http://127.0.0.1:18500/healthz` |
| Port already in use | Another process holds 18500. Use `shoav start --port <n>` and pass `--url http://127.0.0.1:<n>/mcp` to install, or stop the other process |
| Chromium missing or browser fails to launch | Run `shoav doctor`, or `python -m playwright install chromium` in the server's Python environment |
| Tools do not show up after adding the MCP | Most agents read MCP config at startup. Restart the agent in that folder |
| Live view says "cannot reach controller" | Open `http://127.0.0.1:3200`, not another host or `localhost`. The controller only allows the live view's own origin for CORS. If you serve the live view elsewhere, set `LIVE_UI_BASE_URL` (or `LIVE_UI_ORIGINS`) on the server to match |
| Guard does nothing | Check the mode at `http://127.0.0.1:18500/live-api/guard`. `off` disables it |
| Agent uses its own browser instead | Make sure the "Browsing with SHOAV" block is in the project's `AGENTS.md`, and that the agent is run in that folder |

## Uninstall

Delete the files listed under [Scoping to one directory](#scoping-to-one-directory) for the agents you installed. Remove the
"Browsing with SHOAV" block from `AGENTS.md`, everything between the two shoav marker comments. If you ran
`codex mcp add`, remove it with your Codex version's `mcp remove`. Stop the server with `shoav stop`. Local state lives in
`~/.shoav`, delete that folder to remove the virtual environment and downloaded Chromium.

## Quick check

```bash
curl http://127.0.0.1:18500/healthz
curl http://127.0.0.1:18500/live-api/guard
python e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode enforce
```

The last command serves the synthetic pages and prints a pass or fail line per check. See [`e2e/README.md`](e2e/README.md).

## More

- Measured results on synthetic pages: enforce 27/27, observe 17/17, off 22/22 checks ([`docs/integration/REPORT.md`](docs/integration/REPORT.md)). A real `agy` run confirmed hidden text stripped and the overlay click blocked. Only `agy` has been measured as a client.
- Design and limits: [`docs/DESIGN.md`](docs/DESIGN.md). Server: [`server/SHOAV.md`](server/SHOAV.md). Guard: [`guard/README.md`](guard/README.md). Skills: [`skills/README.md`](skills/README.md).
- The tool list and arguments come from the MCP itself (`tools/list`). Upstream docs and licence are in `server/` (`README.md`, `docs/`, `LICENSE`).
