# Live View contract (controller <-> live-ui)

Single source of truth for the backend (Python, `controller/app`) and the frontend
(Next.js, `live-ui/`). If you need to change it, change it here and say so in your report.

## Goal

When an agent starts using the MCP, it gets a session id and a link at once and is told to
show both to the user. The user opens the link in a normal browser tab and watches what the
agent does in real time: which tool ran, whether it was reading, taking a screenshot or acting,
the arguments, the result, the latest screenshot. When the session closes the same link becomes
a read-only archive, with a "restart" that opens a fresh session at the same start URL.

## Ports and config

| What | Default | Env |
|---|---|---|
| Controller (FastAPI, MCP at `/mcp`) | 8000 | uvicorn `--port` |
| live-ui (Next.js) | 3100 | `PORT` |
| Base URL used to build links | `http://127.0.0.1:3100` | `LIVE_UI_BASE_URL` (controller) |
| Controller URL used by the browser | `http://127.0.0.1:8000` | `NEXT_PUBLIC_CONTROLLER_URL` (live-ui) |
| Origins allowed by CORS on the controller | `LIVE_UI_BASE_URL` | `LIVE_UI_ORIGINS` (comma list) |
| Colour in the console banner | off | `LIVE_BANNER_COLOR=true` |

The link for a session is `{LIVE_UI_BASE_URL}/s/{session_id}`.

## Tool phases

Every tool call is classified into exactly one phase:

| phase | tools |
|---|---|
| `session` | `browser.create_session`, `browser.close_session`, `browser.fork_session`, `browser.list_sessions`, `browser.get_session`, `browser.list_tabs`, `browser.activate_tab`, `browser.close_tab` |
| `screenshot` | `browser.screenshot`, `browser.observe` when `preset` is not `text` (default preset counts as screenshot) |
| `read` | `browser.observe` with `preset=text`, `browser.get_html`, `browser.snapshot`, `browser.find_elements`, `browser.get_console`, `browser.get_page_errors`, `browser.get_request_failures`, `browser.get_network_log`, `browser.wait_for_selector`, `browser.list_downloads` |
| `act` | `browser.execute_action`, `browser.drag_drop`, `browser.eval_js`, `browser.set_viewport`, `browser.request_human_takeover` |
| `other` | everything else (memory, auth profiles, witness, harness, readiness) |

## Events

Events written by Live View (`type: "tool"` and `type: "note"`) have `type`, `session_id`,
`seq` (int, monotonic per session, starts at 1) and `ts` (ISO 8601 UTC). These are the only
events in `timeline` and the only SSE frames with an `id:` line.

Legacy bus events (`observe`, `action`, `approval`, `session`) are NOT restamped. They have no
`type`, `seq` or `ts`; they use `event` (the kind), `timestamp` and, for some, `status`, and are
sent as plain `data:` frames without `id:`. The UI must ignore them for ordering and dedup (only
frames with `type` and `seq` take part). A session opened or closed through a non-MCP path (HTTP
delete route, idle expiry, crashed page) is detected by polling `GET /live-api/sessions/{id}`.

### `type: "tool"` (new)

Two events per call, sharing `call_id`:

```json
{ "type": "tool", "event": "start", "call_id": "9f2c...", "seq": 4, "ts": "...",
  "session_id": "a5af842a89e1", "tool": "browser.execute_action", "phase": "act",
  "args": { "action": { "action": "click", "element_id": "op-1", "reason": "open link" } },
  "client": "claude-code" }

{ "type": "tool", "event": "end", "call_id": "9f2c...", "seq": 5, "ts": "...",
  "session_id": "a5af842a89e1", "tool": "browser.execute_action", "phase": "act",
  "status": "ok", "duration_ms": 812,
  "result_summary": "click ok, now at https://www.iana.org/help/example-domains",
  "result": { "...truncated JSON, max 4000 chars serialised..." },
  "screenshot_url": "/artifacts/a5af842a89e1/....png" }
```

- `status` is `ok` or `error`. On error `result_summary` is the error message.
- `args` and `result` are redacted (see Redaction) and each string is cut at 500 chars,
  the whole serialised value at 4000 chars (`"...[truncated]"` marker).
- `screenshot_url` only when the call produced or refreshed a screenshot. Path is relative
  to the controller origin and must be fetchable there.
- `client` is `clientInfo.name` of the MCP connection when known, else omitted.

### Existing events

Legacy `session` (`status`), `observe`, `action`, `approval` events keep working as they do
today, in the legacy shape described above. The UI must ignore events it does not know.

### `type: "guard"` (new)

One verdict event per guarded tool call, sharing `call_id` with the `type: "tool"`
start/end pair for that call. It carries its own `seq` and `ts` and takes part in
ordering and dedup like tool events.

```json
{ "type": "guard", "event": "verdict", "call_id": "9f2c...", "seq": 6, "ts": "...",
  "session_id": "a5af842a89e1", "stage": "ingress", "tool": "browser.observe",
  "verdict": "REWRITE", "mode": "enforce", "enforced": true,
  "reason": "removed hidden-text prompt injection",
  "findings": [{ "kind": "hidden_text", "detail": "div.hidden ..." }],
  "target": { "element_id": "op-s4" } }
```

- `event` is always `verdict`.
- `stage` is `ingress` (observe, snapshot, find_elements, get_html) or `egress`
  (execute_action, drag_drop). Omitted when unknown.
- `verdict` is `ALLOW` | `REWRITE` | `BLOCK` | `ESCALATE`.
- `mode` is the guard mode that produced the verdict: `observe` or `enforce`.
  In `observe` mode verdicts are advisory and `enforced` is false; nothing is
  blocked or rewritten.
- `enforced` is true when the verdict was applied, false when advisory only.
- `reason` is a short human readable explanation. `findings` is a list of
  `{ kind, detail }` pairs. `target.element_id` names the clicked element for
  egress verdicts and is omitted otherwise.
- A guard event may arrive before its tool start/end (or without them, when the
  tool call was rejected before running). The UI attaches it by `call_id` and
  renders a stub row in that case.
- The reducer ignores guard events with an unknown verdict and ignores unknown
  event types entirely (only `lastSeq` advances), so an old UI without guard
  support keeps working.
- Guard UI: each timeline row shows a `GuardBadge` for its attached verdict
  (ALLOW quiet gray, REWRITE amber, ESCALATE orange, BLOCK red). The expanded
  row shows reason, findings (`kind`, `detail`), target element id, mode, and
  whether enforced. The session header shows a `Guard: <mode>, <n> blocked,
  <n> rewritten` chip (escalated count appended when nonzero), hidden until
  the first guard event. The timeline filter bar has a `guard` filter that
  shows intervening rows (rewrite, block, escalate) with its count.

## HTTP API (controller)

All under `/live-api`, GET unless noted, JSON, CORS-enabled for `LIVE_UI_ORIGINS`.

- `GET /live-api/sessions` -> `{ "sessions": [SessionSummary] }`, newest first, live and archived.
- `GET /live-api/sessions/{id}` -> `SessionSummary` or 404.
- `GET /live-api/sessions/{id}/timeline?after_seq=0&limit=500` ->
  `{ "session": SessionSummary, "events": [Event], "last_seq": 12, "has_more": false }`.
  Works for archived sessions (read from disk). Events are oldest-first, all with seq > `after_seq`.
  `limit` defaults to 500 (max 2000) and a response is also capped at about 2 MB, so it may hold
  fewer events than `limit`. `last_seq` is the seq of the last event returned (`after_seq` if none).
  While `has_more` is true, request again with `after_seq=<last_seq>`; the client should loop until
  `has_more` is false before opening SSE. Clients that ignore `has_more` keep working but only see
  the first page.
- `POST /live-api/sessions/{id}/restart` -> `{ "session": SessionSummary }`, creates a new live
  session at the archived session's `start_url`. 409 if `id` is still live. 403 if the request has
  an `Origin` not in `LIVE_UI_ORIGINS`, or `Sec-Fetch-Site: cross-site`; callers with no `Origin`
  (curl, scripts) are allowed.
- `GET /live-api/tools` -> `{ "tools": [{ "name", "description", "phase", "read_only", "required": [..] }], "instructions": "..." }`.
  This is the same catalogue an agent sees, for the "Tools" panel.
- Live stream: existing `GET /sessions/{id}/events` (SSE). Each frame is `id: <seq>` +
  `data: <json Event>`. For an archived session it just emits nothing.

- `GET /live-api/sessions/{id}/stream` -> live picture of the session's active tab, see "Live stream".
- `GET /live-api/stream-stats` -> `{ total_viewers, sessions: { id: { viewers, screencast_active, frames, bytes } } }`
  (debug aid, counters only).
- `GET /live-api/guard` -> `{ "mode": "off|observe|enforce", "version": "1",
  "counters": { "allow": n, "rewrite": n, "block": n, "escalate": n } }`
  (debug aid, counters only, no page content). Counters aggregate the guard
  object behind the tool gateway: per-stage snapshot keys (`ingress_allow`,
  `egress_block`, ...) are summed into the four verdict totals, and plain
  `allow`/`rewrite`/`block`/`escalate` keys are accepted as well. The route
  duck-types `tool_gateway.guard` (`shoav_guard`, `shoav` aliases) via
  `status()`/`snapshot()`/`describe()` or a `counters` dict/attr. Guard off
  (no guard object) returns `mode: "off"` with all counters zero.

```ts
type SessionSummary = {
  id: string; name: string | null;
  state: "live" | "archived";
  start_url: string | null; current_url: string | null; title: string | null;
  created_at: string; closed_at: string | null;
  tool_calls: number; last_screenshot_url: string | null;
  live_url: string;            // {LIVE_UI_BASE_URL}/s/{id}
  client: string | null;
};
```

Client rule (race): load `timeline` first, then open SSE, drop any SSE event whose `seq`
is already <= the highest seq shown. The frontend must also reconnect SSE with backoff and
show a visible "reconnecting" state.

## Persistence

Timeline is appended per session to `{artifact_root}/{session_id}/timeline.jsonl`, one Event per
line, written on every emit. Summary metadata to `{artifact_root}/{session_id}/summary.json`,
rewritten on start, on URL change and on close. Both survive controller restarts.
A controller restart marks previously `live` sessions with no live browser as `archived`.

## What the agent is told (this is the part that reaches the CLI)

1. `initialize.instructions` explains the workflow (create_session -> observe -> execute_action
   with `reason` -> close_session) and says that session-creating
   results carry a `live_view` object and `_notice` as the first keys of the JSON in the first
   content block, and to show its `banner` to the user verbatim before continuing.
2. Every tool call that creates a session (explicit `browser.create_session`, or implicitly by
   `observe`/`execute_action` when none is live, or `fork_session`) returns:
   - `content[0].text`: the JSON of the normal result with two keys placed FIRST:
     `"_notice": "The user is watching this session live. Before your next tool call, tell the user the session id and watch link by pasting live_view.banner as-is in a code block in your reply, then continue the task."` and
     `"live_view": { "session_id", "url", "banner" }` (banner newlines are `
` in the JSON).
     Some MCP clients only surface the first block, so this is the channel that must work.
   - `structuredContent`: the same merged object (so `structuredContent.live_view` exists).
   - one extra `content` text block whose text is the banner (kept for clients that show all blocks).
   Results of calls that do not create a session carry none of this.
   The `max_sessions` error text also names the live session link.
3. `banner` is plain Unicode box drawing, 60 columns wide, no ANSI (ANSI is only used in the
   controller's own console print when `LIVE_BANNER_COLOR=true`):

```
┌──────────────────────────────────────────────────────────┐
│ AUTO BROWSER  live view                                  │
│ session  a5af842a89e1                                    │
│ watch    http://127.0.0.1:3100/s/a5af842a89e1            │
└──────────────────────────────────────────────────────────┘
```

4. The `browser.create_session` tool description says the same thing in one sentence.
5. Session-limit error (`max_sessions`) already names the live session; append its `live_url`.

## Redaction

Never emit values for keys whose words match pass/password/pwd/secret/token/cookie/authorization/api key/totp
(word-boundary match: `passed`, `bypass`, `max_tokens`, `tokens_used` are kept; `X-Auth*` headers are hidden),
never emit sensitive-named query params in URLs (value replaced), never emit `eval_js` results (length only),
never emit `text` when the action has `sensitive: true`, replace with `"[redacted]"`.
`browser.set_cookies` / `set_local_storage` / `eval_js` args are replaced by a short
description (`{"redacted": true, "keys": 3}` / expression length). Screenshots are already
scrubbed by the existing PII code path; do not bypass it.

## Backend notes (added by the controller implementation)

- Extra event `type: "note"` (`event`: `capped` or `archived`, plus `message`) may appear in a
  timeline. The UI should show or ignore it. Timelines are capped at 5000 persisted events; after
  the cap only the in-memory tail (last 1000) and SSE carry new events.
- CORS for `LIVE_UI_ORIGINS` covers `/live-api/*` and `GET /sessions/{id}/events` (the SSE stream).
  If the controller requires a bearer token, the UI cannot call it cross-origin (no credentials).
- `GET /sessions/{id}/events` for an archived session with a timeline stays open with keepalives only.
- Banner: a line too long for the box (long watch URL) is printed without its right border and
  overflows, so the link stays unbroken and copy-pasteable.
- `state` in SessionSummary is derived at read time from the live browser set, not from summary.json.
- `POST /live-api/sessions/{id}/restart` also returns 409 when the session limit is reached.

## Live stream

`GET /live-api/sessions/{id}/stream` is an MJPEG feed (`multipart/x-mixed-replace; boundary=frame`,
one `image/jpeg` part per frame with `Content-Length`), so the UI uses a plain `<img src>`.
It is built on CDP `Page.startScreencast` of the session's active page. The screencast runs only
while at least one viewer is connected (started by the first, stopped when the last leaves) and is
shared by all viewers. A slow viewer drops frames (queue of 2); it never blocks the browser or others.
It follows the active tab (activate, open, close tab, crash) and does not resize the viewport, focus
a window or change page state. A static page sends few frames: a new viewer gets the last frame at once.

- Settings: `LIVE_STREAM_ENABLED` (true), `LIVE_STREAM_FPS` (6), `LIVE_STREAM_QUALITY` (55),
  `LIVE_STREAM_MAX_WIDTH` (1024), `LIVE_STREAM_MAX_VIEWERS_PER_SESSION` (5), `LIVE_STREAM_MAX_VIEWERS` (20).
- Statuses: 200 stream (ends cleanly when the session closes); 404 unknown or malformed id;
  409 `{"detail", "state": "archived"}` for an archived session; 429 `{"state": "limit", "scope", "limit"}`
  with `Retry-After` beyond the viewer caps; 503 `{"state": "disabled"}` when `LIVE_STREAM_ENABLED=false`;
  403 when `Origin` is not in `LIVE_UI_ORIGINS`, or `Sec-Fetch-Site: cross-site` without a Referer from an allowed origin.
- Auth: same global bearer-token middleware as the rest. An `<img>` cannot send `Authorization`, so with a
  bearer token configured the UI gets 401 and shows the "feed unavailable" state; there is deliberately no
  token-in-query fallback. Use a same-origin proxy that adds the header if you need both.
- UI rule: show the stream by default for a live session, fall back to the latest capture on any error,
  retry with backoff, and drop the `<img>` while the browser tab is hidden or the page is unmounted.
