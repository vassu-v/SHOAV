# The SHOAV server

This folder is the S.H.O.A.V. MCP server: a browser MCP server with a deterministic guard in the path. It is a reworked copy of
[Auto Browser](https://github.com/LvcidPsyche/auto-browser) by LvcidPsyche (MIT, copyright JAI Studios). The upstream README is [`README.md`](README.md), and
the upstream changelog and licence are in [`CHANGELOG.md`](CHANGELOG.md) and [`LICENSE`](LICENSE). Credit for the browser control,
the tool gateway and most of the controller belongs to that project.

Most people should use the `shoav` CLI ([`../cli/README.md`](../cli/README.md)), which installs dependencies, starts this server and writes agent
config. This page is for starting it by hand.

## How it differs from upstream Auto Browser

| Area | SHOAV |
|---|---|
| Guard | A deterministic guard ([`../guard/`](../guard/README.md)) hooked into the tool gateway: egress before a click or drag runs, ingress after observe, snapshot, find elements and get HTML return. Switched with `SHOAV_GUARD_MODE` |
| Run mode | Native. No Docker, a visible Chromium by default, one start script |
| Live view | `live-ui/` shows every tool call, the latest screenshot, guard badges and a read-only archive per session |
| Tool names | Underscores (`browser_observe`), because some clients reject dots. Set by `MCP_TOOL_NAME_STYLE=underscore` |
| Tool profiles | 37 curated tools by default, 74 full, 10 minimal (`MCP_TOOL_PROFILE=minimal`) |
| Identity | The MCP server key is `shoav` (Claude Code allow rule `mcp__shoav`). Tool names stay `browser_*` |

A rewrite lands in both the text and the structured half of the MCP result, because different clients read different halves.

## Ports and health

| What | Value |
|---|---|
| Controller and MCP endpoint | `http://127.0.0.1:18500/mcp` |
| Health | `http://127.0.0.1:18500/healthz` |
| Guard mode and counters | `http://127.0.0.1:18500/live-api/guard` |
| Live view | `http://127.0.0.1:3200/s/<session_id>` |
| Test fixtures | 186xx |

Never use 8000, 3100 or 18480. Those are upstream defaults or belong to other tools.

```bash
curl http://127.0.0.1:18500/healthz          # {"status": "ok", ...}
curl http://127.0.0.1:18500/live-api/guard   # mode and counters
```

## Start it on Windows

From this folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Port 18500 -Status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Port 18500 -Stop
```

Options: `-Port`, `-Guard off|observe|enforce` (default enforce), `-Headless`, `-Background`, `-DataDir`, `-AllowedHosts`,
`-LiveUiBaseUrl`. The script sets per-process environment only, no global settings. It expects Python with the controller's
requirements and Chromium installed (`pip install -r controller\requirements.txt`, `python -m playwright install chromium`).

## Start it on Linux and macOS

There is no PowerShell script to run. Use the CLI, or raw uvicorn from `controller/`:

```bash
cd server/controller
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
SHOAV_GUARD_MODE=enforce MCP_TOOL_NAME_STYLE=underscore ALLOWED_HOSTS='*' \
  API_BIND_SCOPE=loopback OCR_ENABLED=false LIVE_UI_BASE_URL=http://127.0.0.1:3200 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 18500
```

The Windows script also points the data roots (artifacts, sessions, `state.db`) under `.local-data/<port>`. For raw uvicorn set
`ARTIFACT_ROOT`, `UPLOAD_ROOT`, `SESSION_STORE_ROOT`, `STATE_DB_PATH` and friends to a folder you own if the defaults are not
writable, and add `HEADLESS=true` on a machine with no display.

## Environment variables

| Variable | Meaning |
|---|---|
| `SHOAV_GUARD_MODE` | `off`, `observe`, `enforce`. The controller's own default if this is unset is `off` (fails safe for embedders who set nothing); `start-local.ps1` and the `shoav` CLI both explicitly set it to `enforce`, so the two documented ways to start the server are protected by default |
| `SHOAV_GUARD_FAIL` | `open` (default, a crashing filter lets the result through) or `closed` |
| `SHOAV_FILTERS_PATH` | Override where the guard code is loaded from. Defaults to `../guard` in this repo |
| `MCP_TOOL_NAME_STYLE` | `underscore` or `dotted` (upstream default) |
| `MCP_TOOL_PROFILE` | `curated` (37, default), `full` (74), `minimal` (10) |
| `HEADLESS` | `true` hides the browser window |
| `ALLOWED_HOSTS` | Hosts the browser may visit. Upstream defaults to a short list. The local script sets `*` |
| `LIVE_UI_BASE_URL` | Where the live view is served. Used for the watch links and as the CORS origin |
| `LIVE_UI_ORIGINS` | Explicit CORS origins for `/live-api`, comma separated. Defaults to the origin of `LIVE_UI_BASE_URL` |

Upstream variables are documented in [`README.md`](README.md) and `controller/app/config.py`.

## The live view

`live-ui/` is a Next.js app that reads the controller's `/live-api`. Start it in a second terminal (or with `shoav start --ui`):

```bash
cd server/live-ui
npm install
npm run build
npm start          # port 3200, override with PORT
```

Every session result carries a watch link, `http://127.0.0.1:3200/s/<id>`. Open that exact origin: if the page says it cannot reach the
controller, the origin you opened does not match `LIVE_UI_BASE_URL` / `LIVE_UI_ORIGINS`, so CORS refuses it. After
`browser_close_session` the link becomes a read-only archive.

## Guard modes

| Mode | Behaviour |
|---|---|
| off | No guard, no cost |
| observe | Checks run and findings are logged. Content is never rewritten and actions are never blocked; a flagged result only gains an informational `_shoav` note (`enforced: false`) |
| enforce | Rewrites and blocks apply. ALLOW, REWRITE, ESCALATE and BLOCK are described in [`../guard/README.md`](../guard/README.md) |

Verify a running server with the synthetic pages: [`../e2e/README.md`](../e2e/README.md). Measured results and the wiring plan are in
[`../docs/integration/REPORT.md`](../docs/integration/REPORT.md).
