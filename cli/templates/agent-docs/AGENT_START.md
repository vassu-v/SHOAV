# AGENT_START.md: start here (SHOAV guarded browser, D-1 template)

Read this file first. It is the only entry point for an agent running the guarded browser.

## 1. Go to the controller folder

```powershell
cd shoav-mcp\MCP\auto-browser
```

All server commands run from there. Do not run them from `shoav-mcp/MCP/agent-template/`.

## 2. Start the server with the guard on

```powershell
.\scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
.\scripts\start-local.ps1 -Port 18500 -Status
```

Rules:

- Never use port 8000, 18480, or 3100. They belong to the user or other services. If 18500 is taken, pick another free port and use it everywhere below.
- `-Guard enforce` is the recommended mode. `observe` logs guard verdicts without blocking. `off` disables the guard.
- Until the `-Guard` flag lands in `start-local.ps1` (plan Wave 1, task C-1), set the same values by environment using `settings.json` in this folder: `SHOAV_GUARD_MODE=enforce`, `SHOAV_FILTERS_PATH=<path to shoav-mcp/filters>`, `SHOAV_GUARD_FAIL=open`, `MCP_TOOL_NAME_STYLE=underscore`.
- Keep `MCP_TOOL_NAME_STYLE=underscore` always. `agy` rejects dotted tool names.

Expected status output: `up  http://127.0.0.1:18500/mcp`.

## 3. Connect your client

Endpoint: `http://127.0.0.1:18500/mcp` (replace the port if you changed it).

`agy` (workspace scope, copy `mcp_config.json` from this folder to `.agents/mcp_config.json`):

```json
{ "mcpServers": { "auto-browser": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```

In `agy -p` (non-interactive) mode, MCP calls need an allow rule such as `mcp(auto-browser/*)`.

Claude Code (project scope, `.mcp.json` in your working dir):

```json
{ "mcpServers": { "auto-browser": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```

Tools appear with underscore names (`browser_observe`). The server accepts either spelling.

## 4. Create a session and print the banner verbatim

Call `browser.create_session` with `start_url` first. It returns a session id and a watch link in a boxed banner. Paste that banner to the user exactly as given, in a code block, before your next tool call. Do this even if the user did not ask. The banner looks like:

```
┌──────────────────────────────────────────────────────────┐
│ AUTO BROWSER  live view                                  │
│ session  a5af842a89e1                                    │
│ watch    http://127.0.0.1:3200/s/a5af842a89e1            │
└──────────────────────────────────────────────────────────┘
```

Live link pattern for every session: `http://127.0.0.1:3200/s/<sid>`. When closed, the same link becomes a read-only archive.

## 5. Observe, execute, close

1. `browser.observe` with `preset: "text"` (or `browser.snapshot`) to read. For one fact, prefer `browser.find_elements` with a `query` first.
2. `browser.execute_action` to act. Every action needs a `reason`. Target by `element_id` from the latest observe.
3. Observe again to confirm the result. Repeat.
4. `browser.close_session` when finished.

Guard behavior while you work:

- Ingress REWRITE: content arrives cleaned plus a small `_shoav` note (`verdict`, `findings`, `summary`). Continue the task on the cleaned content.
- Egress BLOCK or ESCALATE: the call returns `isError: true` with an `error` reason and a `shoav` detail plus what to do next (re-observe or request human takeover). Do not retry the same click. Do not try to bypass it.

## 6. Stop

```powershell
.\scripts\start-local.ps1 -Port 18500 -Stop
```

Stop exactly the process tree you started. Never kill processes you did not start.
