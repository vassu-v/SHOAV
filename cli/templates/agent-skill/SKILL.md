---
name: auto-browser
description: >-
  Connect to and drive the local Auto Browser MCP server (visible Chromium, session id, live
  view link). Use when a task needs a real browser: opening pages, reading them, clicking,
  typing, taking screenshots. Also covers how to start the server if it is not running,
  what the tools are, and what to tell the user when a session starts.
---

# Auto Browser MCP

A local MCP server that drives a **visible** Chromium window. Every session gets an id and a
link the user can open to watch what you do, live, in a normal browser tab.

Everything here is local to this folder. Do not edit global agent or CLI settings.

## 1. Is it running?

```powershell
.\auto-browser\scripts\start-local.ps1 -Port 18500 -Status
```

- `up   http://127.0.0.1:18500/mcp` : go to step 3.
- `down`: start it (step 2).

Health URL: `GET http://127.0.0.1:18500/healthz` returns `{"status":"ok"}`.

## 2. Start it

```powershell
.\auto-browser\scripts\start-local.ps1 -Port 18500 -Background   # returns when healthy
.\auto-browser\scripts\start-local.ps1 -Port 18500 -Stop         # stops it and its browser
```

- If port 18500 is taken by something else, the script refuses. Choose another port with
  `-Port 8100` and use that port everywhere below. Do not kill a process you did not start.
- Data goes to `auto-browser\.local-data\<port>\`. Logs: `controller.log` / `controller.log.err` there.
- `-AllowedHosts "example.com,*.wikipedia.org"` restricts which sites the browser may open
  (default `*`, loopback only). `-Headless` hides the window; the default is a visible window.
- Needs Python 3.10+ with the controller requirements and `python -m playwright install chromium`.

The live view UI (Next.js) is separate: `cd auto-browser\live-ui; npm install; npm run build; npm start`
serves `http://127.0.0.1:3200`. Pass `-LiveUiBaseUrl` to the script if you use another port.
Without the UI running, the MCP still works; only the watch link will not open.

## 3. Connect

Endpoint: `http://127.0.0.1:18500/mcp` (Streamable HTTP, JSON-RPC 2.0).

Claude Code (project scope, `.mcp.json` in your working dir):
```json
{ "mcpServers": { "auto-browser": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```

Antigravity `agy` (workspace scope, `.agents/mcp_config.json`; tested):
```json
{ "mcpServers": { "auto-browser": { "type": "http", "url": "http://127.0.0.1:18500/mcp" } } }
```
agy rejects tool names containing a dot, so the controller must run with `MCP_TOOL_NAME_STYLE=underscore`
(`start-local.ps1` sets it). Tools then appear as `browser_observe`; the server accepts either spelling.
In `agy -p` (non-interactive) mode MCP calls need an allow rule such as `mcp(auto-browser/*)`.

Any other MCP client: use the HTTP URL. A stdio bridge also exists:
`python auto-browser\scripts\mcp_stdio_bridge.py` with env `AUTO_BROWSER_BASE_URL=http://127.0.0.1:18500/mcp`.

## 4. Workflow

1. `browser.create_session` with `start_url`. **Show the user the banner** (below) before continuing.
2. `browser.snapshot` (or `browser.observe` with `preset: "text"`) to read the page. Observe returns `interactables`, each
   with an `element_id` and `selector_hint`. Use presets `normal` or `rich` only when you need a screenshot.
3. `browser.execute_action` with `action: { action, element_id, reason, ... }`. **`reason` is required**
   on every action. Action kinds: `navigate click hover select_option type press scroll wait reload
   go_back go_forward upload request_human_takeover done`.
4. Observe again to confirm the result. Repeat.
5. `browser.close_session` when done. The link then becomes a read-only archive.

Only **one live session** is allowed by default. If you get `Session limit reached`, the error names
the live session and its link; reuse it or close it.

If you skip step 1, the first observe or action creates a session for you and returns the banner anyway.

## 5. Navigate efficiently (fewer tokens, fewer steps)

Measured on a large page (Wikipedia "Alan Turing"), one call each:

| Call | Cost | Use it for |
|---|---|---|
| `find_elements` with `selector` or `query` | ~60-180 tokens | **First choice.** Read one fact, or find a link/button: `{selector:"h1"}`, `{query:"Born", limit:3}` |
| `observe` `preset:"fast"` | ~900 | Session state and URL only (no text, no elements). Cheap "where am I" check |
| `observe` `preset:"text"`, `limit:10` | ~2,500 | Page text plus the first 10 clickable elements |
| `observe` `preset:"text"` (default limit) | ~4,600 | Only when you must see many elements |
| `observe` `preset:"normal"` | ~4,700 | Same as text, plus a screenshot file |
| `observe` `preset:"rich"` | ~8,100 | Avoid |
| `get_html` | **~436,000** | **Never** on real pages. Use `find_elements` |
| `snapshot` (default) | ~2,500 (8,000 chars max) | **Read a page as a compact tree** with a ref per link, button and field. Tables keep rows. Add `selector:"main"` |
| `snapshot` `selector:"table.infobox"` | ~400 | One table or section: the cheapest full read of a structure |
| `screenshot` (default) | ~800 + 500 text | A real image you can see (JPEG, 75 percent scale). `image:false` gives only a path |

Rules that follow from this:

1. **Skip clicking through when you know the URL.** Search sites: `navigate` straight to
   `https://en.wikipedia.org/w/index.php?search=Alan+Turing` or `https://www.youtube.com/results?search_query=...`
   instead of type, press Enter, observe. One action replaces three calls.
2. **Ask for what you need.** Need a birth date? `find_elements {query:"Born"}`, not a full observe.
3. **After an action, do not re-observe by reflex.** The action result's `session` block already has
   `current_url` and `title`; check those first and observe only if you still need the page contents.
4. **Cap `limit`** on observe (5-10) unless you are searching for something on a crowded page.
5. **Target by `element_id`** from the latest observe (or a CSS selector from `find_elements`). Ids can go
   stale after navigation: observe again if an action says the element is gone.
6. **Every result repeats a ~600-token `session` block.** Skim it for `current_url` and `title` only; the
   rest (paths, isolation, witness, remote access) is noise for you.
7. **Prefer `snapshot` to read, `screenshot` to look.** `snapshot` returns text: headings, landmarks, links,
   form fields and tables (`row: a | b | c`), skipping hidden content (the header line counts what it
   skipped). Each control has a ref like `op-s1f`; use it as `element_id` in `execute_action`, the same as
   ids from `observe`. Inline links look like `[Learn more|op-s1]`. Big page: the default returns the first
   8,000 characters and ends with a line saying how to continue (`offset=`), narrow (`selector`) or shrink
   (`depth`). On Wikipedia "Alan Turing" the whole tree is about 121,000 characters (2,488 controls), so
   scope it: `selector:"main"`, `selector:"table.infobox"`, or `viewport_only:true` (about 4,000 characters).
   `screenshot` returns an actual image block (JPEG, 960x600, about 60 KB, about 800 tokens) that you can look
   at, plus a small text block with the URL and file path. Use it for layout, charts, captchas and "did that
   work" checks. Options: `image:false` (path only), `format:"png"`, `scale`, `quality`, `full_page:true`,
   `selector` (one element). Very tall pages can time out with `full_page`; use `selector` or scroll. The
   `observe` presets still return only a screenshot file, and `accessibility_outline` there is always
   `available:false` (Playwright removed it); `snapshot` replaces it.
8. `wait` with `wait_ms` only when something is loading (video ads, spinners). Prefer `wait_for_selector`.
9. Blocked by a bot check (for example Google's "unusual traffic" page)? Do not try to get past it.
   Switch to another route (a direct URL, another site) or tell the user.

## 6. The session banner

A tool result that creates a session starts with `_notice` and `live_view` (`session_id`, `url`, `banner`),
and has an extra text block with the banner. It looks like:

```
┌──────────────────────────────────────────────────────────┐
│ AUTO BROWSER  live view                                  │
│ session  a5af842a89e1                                    │
│ watch    http://127.0.0.1:3200/s/a5af842a89e1            │
└──────────────────────────────────────────────────────────┘
```

Before your next tool call, paste it to the user exactly as given, in a code block, then continue.
Do this even if the user did not ask: they cannot see tool output, and this is how they find the
watch link. The user watches the same
timeline you produce: each tool call, whether it was a read, a screenshot or an action, the
arguments and the result.

## 7. Tools

Discover them at runtime with `tools/list` (names, descriptions, JSON schemas) and read the
`instructions` string returned by `initialize`. The same catalogue is at
`GET http://127.0.0.1:18500/live-api/tools`. Curated profile groups:

- **Session**: `browser.create_session` `list_sessions` `get_session` `close_session` `fork_session` `list_tabs` `activate_tab` `close_tab`
- **Read**: `observe` (`preset: text`) `get_html` `find_elements` `get_console` `get_page_errors` `get_request_failures` `get_network_log` `wait_for_selector` `list_downloads`
- **Screenshot**: `screenshot`, `observe` with a non-text preset
- **Act**: `execute_action` `drag_drop` `eval_js` (needs `workflow_profile=governed`) `set_viewport` `request_human_takeover`
- **Other**: memory profiles, auth profiles, `verify_witness`, `export_witness_bundle`, `readiness_check`, `harness.*`

Sensitive actions can require an approval (`approval_id`) or human takeover. Do not try to bypass it;
tell the user.

## 8. Failure modes

| Symptom | Cause / fix |
|---|---|
| Cannot connect | Server is down. Step 1 and 2. |
| `Invalid arguments ... action.reason: Field required` | Add `reason` to the action. |
| `Session limit reached: max_sessions=1` | Use or close the named session. |
| `Host '...' is not allowlisted` | Restart with `-AllowedHosts` that includes the site. |
| Watch link does not open | The live UI is not running. Start it (step 2) or tell the user the session id. |
| No window visible | Started with `-Headless`, or it is behind other windows. |

## 9. SHOAV guard demo

- Template pack: `shoav-mcp/MCP/agent-template/` (`AGENT_START.md` first, then `SETUP.md`, `OUTPUTS.md`).
- Start with `-Port 18500 -Guard enforce` (never port 8000). Guard notes arrive inside the result dict
  (`_shoav` on rewrite; `error` plus `shoav` on block or escalate). Blocked clicks: do not retry, re-observe
  or request human takeover.
