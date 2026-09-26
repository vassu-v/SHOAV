# SHOAV MCP

Guarded copy of Auto Browser for S.H.O.A.V. (Targets 1 to 4).
Controller on 18500, live UI on 3200, fixtures on 18600 to 18699.
Never use 8000, 18480, or 3100. Upstream credit: Auto Browser by LvcidPsyche (see `auto-browser/README.md`, `auto-browser/CHANGELOG.md`, `auto-browser/LICENSE`).

## Prerequisites

- Python 3.10 with controller deps plus `python -m playwright install chromium`
- Node.js only for the live UI
- This folder: `shoav-mcp/MCP`

## Start (one command per mode)

Run from `shoav-mcp/MCP/auto-browser`. Each command is per-process (no global settings changed).

Off (no guard):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Guard off -Background
```

Observe (guard notes only, never blocks):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Guard observe -Background
```

Enforce (blocks and rewrites):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Guard enforce -Background
```

Status and stop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Status
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Stop
```

Live UI (separate terminal, from `auto-browser/live-ui`):

```powershell
npm install
npm run build
npm start
```

It serves `http://127.0.0.1:3200`.

## Connect (one config example)

Same shape for Claude Code (`.mcp.json`) and `agy` (`.agents/mcp_config.json`):

```json
{
  "mcpServers": {
    "auto-browser": {
      "type": "http",
      "url": "http://127.0.0.1:18500/mcp"
    }
  }
}
```

Copy `agent-template/mcp_config.json` to your client config path. Keep `MCP_TOOL_NAME_STYLE=underscore` (the start script sets it) because `agy` rejects dotted tool names.

## Live link

Every session returns a banner with a watch link:

```text
http://127.0.0.1:3200/s/<sid>
```

Replace `<sid>` with the session id. After `browser.close_session` the same link becomes a read-only archive.

## How to see BLOCK and REWRITE

Agent side:

- REWRITE: normal result with cleaned content plus a leading `_shoav` note (`verdict`, `findings`, `summary`). Continue on the cleaned content.
- BLOCK or ESCALATE: `isError: true` with `error` first and `shoav` detail after, in both `content[0].text` and `structuredContent`. Do not retry a blocked click. Re-observe or request human takeover when told to.

Human side: open the live link above. Each tool row carries a guard badge (REWRITE amber, BLOCK red, ESCALATE orange, ALLOW quiet). The expanded row shows reason, findings, target element id, mode, and whether enforced. The header chip shows running counters.

Quick check in enforce mode:

1. `GET http://127.0.0.1:18500/healthz` returns `{"status": "ok"}`
2. `GET http://127.0.0.1:18500/live-api/guard` shows mode plus counters
3. Hidden-text fixture observe returns REWRITE with a `_shoav` note
4. Overlay fixture click returns BLOCK with reason and next step

## Ports and config note

- Controller 18500, live UI 3200, fixtures 186xx. The runner refuses 8000, 18480, and 3100.
- `controller/app/config.py` still defaults `live_ui_base_url` to `http://127.0.0.1:3100`. That default was left as is (file not edited). At runtime `scripts/start-local.ps1` passes `-LiveUiBaseUrl` default `http://127.0.0.1:3200` via `LIVE_UI_BASE_URL`, which overrides the code default, so banners point at 3200 when launched the documented way. Docs and skill point at 3200 to match. Upstream tests that assert 3100 were also left untouched.
- Agent entry point: read `agent-template/AGENT_START.md` first, then `agent-template/SETUP.md`.

## Stop

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1 -Port 18500 -Stop
```

Stop exactly the process tree you started. Data lives under `auto-browser/.local-data/<port>/` (git ignored).
