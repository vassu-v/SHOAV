# SETUP.md: prerequisites, start, stop, verify, troubleshoot

## 1. Prerequisites

- Python 3.11+ (the controller declares `requires-python >= 3.11`).
- Controller deps: `auto-browser/controller/requirements.txt` plus `requirements-dev.txt` for tests.
- Playwright Chromium: `python -m playwright install chromium`.
- Node.js (only for the live UI): `cd auto-browser/live-ui; npm install`.
- This template: `shoav-mcp/MCP/agent-template/` (`mcp_config.json`, `settings.json`, `AGENT_START.md`, `OUTPUTS.md`, `REVIEW.md`).

## 2. Start

```powershell
cd <repo>\shoav-mcp\MCP\auto-browser
.\scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
.\scripts\start-local.ps1 -Port 18500 -Status
```

Live UI (separate terminal):

```powershell
cd <repo>\shoav-mcp\MCP\auto-browser\live-ui
npm install
npm run build
npm start
```

Live UI serves `http://127.0.0.1:3200`. Watch link per session: `http://127.0.0.1:3200/s/<sid>`.

## 3. Stop

```powershell
.\scripts\start-local.ps1 -Port 18500 -Stop
```

Stop exactly the process tree you started. Data for the port lives in `auto-browser/.local-data/<port>/` (git-ignored). Logs there: `controller.log`, `controller.log.err`.

## 4. Ports

- Never use 8000, 18480, or 3100. They belong to the user or other services.
- Template default is 18500. If taken, the script refuses: pick another port with `-Port N` and use that port in `mcp_config.json`, `.mcp.json`, status checks, and stop commands.

## 5. Rebuild the UI after changes

```powershell
cd <repo>\shoav-mcp\MCP\auto-browser\live-ui
npm run build
npm test
```

Backend tests:

```powershell
cd <repo>\shoav-mcp\MCP\auto-browser\controller
python -m pytest -q
```

Guard contract rule: change `live-ui/CONTRACT.md` and both sides (emitter and renderer) together.

## 6. Verify

1. `GET http://127.0.0.1:18500/healthz` returns `{"status": "ok"}`.
2. `GET http://127.0.0.1:18500/live-api/guard` shows mode `enforce` plus counters.
3. `agy mcp list-tools auto-browser` lists underscore tools (`browser_observe`, ...).
4. `browser.create_session` returns the boxed banner; the watch link opens the live timeline.
5. Fixture check in enforce mode: hidden-text page returns REWRITE with a `_shoav` note; overlay click returns BLOCK with reason and next step; benign pages (Wikipedia, Hacker News, a login form, a cookie banner) return ALLOW.

## 8. Guard modes and the T-5 runner

Start the controller once per mode, then run the matching runner line from the repo root:

```powershell
.\scripts\start-local.ps1 -Port 18500 -Guard off -Background
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode off
.\scripts\start-local.ps1 -Port 18500 -Stop
```

```powershell
.\scripts\start-local.ps1 -Port 18500 -Guard observe -Background
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode observe
.\scripts\start-local.ps1 -Port 18500 -Stop
```

```powershell
.\scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode enforce
.\scripts\start-local.ps1 -Port 18500 -Stop
```

`--mode auto` (the default) probes `GET /live-api/guard` and runs the matching set.
Fixture ports must stay in 18600-18699. The runner refuses 8000, 18480, and 3100.

How to see BLOCK and REWRITE:
- REWRITE: agent text arrives cleaned with a leading `_shoav` note (`verdict`, `findings`, `summary`); the live row at `http://127.0.0.1:3200/s/<sid>` shows an amber REWRITE badge with the findings list.
- BLOCK or ESCALATE: the call returns `isError: true` with `error` first and `shoav` detail after, in both `content[0].text` and `structuredContent`; the live row shows a red BLOCK (or orange ESCALATE) badge with the reason.

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Banner not printed by the agent | Known client defect: some clients pass only part of the result or the model omits it. The server sends the banner as `_notice` plus `live_view` first keys and a text block. Fix at the agent layer: follow `AGENT_START.md` step 4 and paste the banner verbatim before the next call. |
| `agy` shows 0 tools or name errors | `agy` rejects dots in tool names. Run with `MCP_TOOL_NAME_STYLE=underscore` (the start script sets it). Tools appear as `browser_observe`; calls accept either spelling. |
| `structuredContent`-only clients miss notes | Some clients read only `structuredContent` when present. Guard notes live inside the result dict itself (`_shoav`, `error`, `shoav`), never only in the text block. Snapshot results omit `structuredContent` so the tree plus note reach the model. |
| Port in use | The script refuses to take a port held by another process. Pick another port with `-Port N`. Never kill processes you did not start. |
| Watch link does not open | The live UI is not running. Start it (section 2) or tell the user the session id. |
| `-Guard` flag unknown | The flag lands with Wave 1 task C-1. Until then, set the `settings.json` values as environment variables (`SHOAV_GUARD_MODE`, `SHOAV_FILTERS_PATH`, `SHOAV_GUARD_FAIL`, `MCP_TOOL_NAME_STYLE`). |
