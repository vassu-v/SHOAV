# SHOAV tool reference

Generated from a running server (controller on a scratch port, `MCP_TOOL_NAME_STYLE=underscore`), by
calling `GET /mcp/tools` and JSON-RPC `tools/list` once per profile. Both lists matched:

| `MCP_TOOL_PROFILE` | Tools | Notes |
|---|---|---|
| `minimal` | 10 | smallest set for a full loop: open, read, act, close |
| `curated` | 37 | the default. Adds diagnostics, tabs, auth and memory profiles, witness, `eval_js` |
| `full` | 74 | adds approvals, cookies and storage, background agent jobs, cron, proxies, harness |

Tools outside the active profile are not registered, so a call to them fails. Names are shown with
underscores (`browser_observe`); the server also accepts the dotted form (`browser.observe`).

Re-check at runtime: `tools/list` over MCP, or `GET http://127.0.0.1:18500/mcp/tools`. Call a tool
over plain HTTP with `POST /mcp/tools/call` and body `{"name": "browser_observe", "arguments": {...}}`.

`session_id` is accepted by almost every browser tool and left out of the args column. It may be
omitted when exactly one session is live.

## The action object (`browser_execute_action`)

```json
{"action": {"action": "click", "element_id": "op-s3", "reason": "submit the form"}}
```

| Field | Used by | Notes |
|---|---|---|
| `action` | all | `navigate click hover select_option type press scroll wait reload go_back go_forward upload request_human_takeover done` |
| `reason` | all | required, 1 to 1000 chars |
| `element_id` | click, hover, type, select_option, upload | a ref from `snapshot` (`op-s3`) or `observe` `interactables` |
| `selector` | same as above | CSS selector, alternative to `element_id` |
| `x`, `y` | click, hover | coordinates, last resort |
| `text`, `clear_first`, `sensitive` | type | `clear_first` defaults true; set `sensitive` for secrets |
| `key` | press | for example `Enter`, `Tab` |
| `value`, `label`, `index` | select_option | pick one way to name the option |
| `delta_x`, `delta_y` | scroll | `delta_y` defaults 600 |
| `wait_ms` | wait | 0 to 30000, default 1000 |
| `url` | navigate | absolute URL |
| `file_path` | upload | local file |
| `risk_category`, `confidence` | any | optional hints (`read write upload post payment account_change destructive`) |

Top-level `approval_id` is only for actions that a policy held for approval.

## Read tool options worth knowing

- `browser_observe`: `preset` one of `text` (cheap, no screenshot), `fast` (state and URL only),
  `normal` (adds a screenshot file), `rich`; `limit` 1 to 200, default 40 interactables.
- `browser_snapshot`: `selector` (CSS scope), `depth` 1 to 20 (default 8), `max_chars` 500 to 30000
  (default 8000), `offset` to page, `viewport_only`, `include` `interactive` (default) or `all`.
- `browser_find_elements`: `selector` or `query` (case-insensitive text, `regex: true` for JS regex),
  `context` chars around each match (0 to 500), `limit` 1 to 100 (default 20).
- `browser_screenshot`: `image` (false returns only the path), `format`, `scale`, `quality`,
  `full_page`, `selector`.
- `browser_wait_for_selector`: `selector` required, `state` visible, hidden, attached or detached,
  `timeout_ms`.

## Minimal profile (10 tools, also in curated and full)

| Tool | Purpose | Key args (* required) |
|---|---|---|
| `browser_activate_tab` | Bring one tab to the foreground so subsequent observations and actions target it. | `index`* |
| `browser_close_session` | Close a session and finalize its trace/artifacts. | none |
| `browser_create_session` | Create a browser session, optionally at a start URL. | `name`, `start_url`, `storage_state_path`, `auth_profile`, `memory_profile`, `proxy_persona`, `proxy_server` |
| `browser_execute_action` | Run one browser action (navigate, click, type, press, select, scroll, ...) in a session. | `approval_id`, `action`* |
| `browser_find_elements` | Find elements by CSS selector, or by text/regex query with context. | `selector`, `query`, `regex`, `context`, `limit` |
| `browser_list_tabs` | List currently open tabs/pages for one session. | none |
| `browser_observe` | Observe the page: interactables, tabs, console, summary. | `preset`, `limit` |
| `browser_screenshot` | Screenshot the page as viewable JPEG plus a text block; full PNG is saved. | `label`, `image`, `format`, `scale`, `quality`, `full_page`, `selector` |
| `browser_snapshot` | Compact text tree of the page: headings, links, fields, tables. | `selector`, `depth`, `max_chars`, `offset`, `viewport_only`, `include` |
| `browser_wait_for_selector` | Wait for a CSS selector to reach a specific state (visible, hidden, attached, detached). | `selector`*, `timeout_ms`, `state` |

## Curated profile adds (27 tools, also in full)

| Tool | Purpose | Key args (* required) |
|---|---|---|
| `browser_close_tab` | Close one tab index if more than one tab is open. | `index`* |
| `browser_drag_drop` | Drag from one element or coordinate to another. | `source_selector`, `source_x`, `source_y`, `target_selector`, `target_x`, `target_y` |
| `browser_eval_js` | Execute a JavaScript expression in the current page context and return the result. | `expression`* |
| `browser_export_witness_bundle` | Export a session's Witness receipts as a self-contained evidence bundle: every receipt, the head hash, the signing key id, and the Ed25519 public key. | none |
| `browser_fork_session` | Fork a session: snapshot its cookies, storage state, and current URL, then create a new independent session with that state. | `name`, `start_url` |
| `browser_get_auth_profile` | Inspect one saved auth profile by name: its normalized name, on-disk profile directory, storage-state metadata, and any saved profile metadata. | `profile_name`* |
| `browser_get_console` | Read recent browser console messages for an active session. | `limit` |
| `browser_get_html` | Get the HTML source of the current page. | `full_page`, `text_only` |
| `browser_get_memory_profile` | Retrieve a saved memory profile by name. | `profile_name`* |
| `browser_get_network_log` | Return captured HTTP request/response entries for a session. | `limit`, `method`, `url_contains` |
| `browser_get_page_errors` | Read recent uncaught page errors for an active session. | `limit` |
| `browser_get_request_failures` | Read recent failed network requests for an active session. | `limit` |
| `browser_get_session` | Get the full record for one browser session by ID: the live session summary (status, current page, tabs) when the session is active, or the persisted session record when it has been closed. | none |
| `browser_list_auth_profiles` | List reusable saved auth profiles that can be loaded into a new session. | none |
| `browser_list_downloads` | List files captured from browser downloads for one session. | none |
| `browser_list_memory_profiles` | List all saved memory profiles. | none |
| `browser_list_sessions` | List live and persisted browser sessions. | none |
| `browser_readiness_check` | Run a deployment readiness check. | `mode` |
| `browser_request_human_takeover` | Ask for a human to take over the shared browser desktop. | `reason` |
| `browser_save_auth_profile` | Save the current session storage state into a reusable named auth profile. | `profile_name`* |
| `browser_save_memory_profile` | Save a named memory profile with context from the current session. | `profile_name`*, `goal_summary`, `completed_steps`, `discovered_selectors`, `notes` |
| `browser_set_viewport` | Resize the browser viewport to the specified width and height. | `width`*, `height`* |
| `browser_stop_trace` | Finalize the current Playwright trace for an active session and return its artifact path. | none |
| `browser_verify_witness` | Verify a session's Witness receipt chain. | none |
| `harness_get_status` | Read one convergence run record and current status. | `run_id`* |
| `harness_get_trace` | Read the latest or selected trace for one convergence run. | `run_id`*, `attempt_index` |
| `harness_list_runs` | List recent Agent Skill Induction convergence runs, newest first, with each run's ID, contract, provider, attempt count, and current status. | `status`, `limit` |

## Full profile adds (37 tools)

| Tool | Purpose | Key args (* required) |
|---|---|---|
| `browser_approve_approval` | Approve a pending approval item. | `approval_id`*, `comment` |
| `browser_cancel_agent_job` | Cancel a queued or running background agent job. | `job_id`* |
| `browser_cdp_attach` | Attach to an already-running Chrome instance via CDP URL. | `cdp_url`* |
| `browser_create_cron_job` | Create a browser automation job that runs on a cron schedule and/or via an HTTP webhook trigger. | `name`*, `goal`*, `provider`, `schedule`, `start_url`, `auth_profile`, `proxy_persona` |
| `browser_create_proxy_persona` | Create or update a named proxy persona with server URL and credentials. | `name`*, `server`*, `username`, `password`, `description` |
| `browser_delete_cron_job` | Delete a cron / webhook trigger job. | `job_id`* |
| `browser_delete_memory_profile` | Delete a named memory profile. | `profile_name`* |
| `browser_delete_proxy_persona` | Delete a named proxy persona. | `name`* |
| `browser_discard_agent_job` | Discard a queued or finished background agent job so operators can clear stale work. | `job_id`* |
| `browser_enable_shadow_browse` | Switch a stuck session to headed (visible) mode for debugging. | none |
| `browser_execute_approval` | Execute an already approved action. | `approval_id`* |
| `browser_export_script` | Export the current session's recorded actions as a runnable Playwright Python script. | none |
| `browser_get_agent_job` | Read one browser-agent job record. | `job_id`* |
| `browser_get_cookies` | Get all cookies for the current session context. | `urls` |
| `browser_get_local_storage` | Read a key (or all keys) from localStorage or sessionStorage in the current page context. | `storage_type`, `key` |
| `browser_get_remote_access` | Read current remote-access metadata for takeover/API forwarding. | none |
| `browser_list_agent_jobs` | List queued or completed browser-agent jobs. | `status` |
| `browser_list_approvals` | List pending or historical approval items. | `status` |
| `browser_list_cron_jobs` | List all configured cron / webhook trigger jobs. | none |
| `browser_list_providers` | List configured model providers for browser-agent orchestration. | none |
| `browser_list_proxy_personas` | List all configured proxy personas. | none |
| `browser_pii_scrubber_status` | Return the current PII scrubber configuration: which patterns are active, which layers are enabled, and the replacement string. | none |
| `browser_queue_agent_run` | Queue a short agent loop for background execution. | `request`* |
| `browser_queue_agent_step` | Queue one agent step for background execution. | `request`* |
| `browser_reject_approval` | Reject a pending approval item. | `approval_id`*, `comment` |
| `browser_resume_agent_job` | Resume an interrupted, failed, or step-limited background agent run from checkpoints. | `job_id`*, `max_steps` |
| `browser_save_auth_state` | Save session storage state to the per-session auth-state root. | `path`* |
| `browser_set_cookies` | Set one or more cookies in the current session context. | `cookies`* |
| `browser_set_local_storage` | Write a key-value pair to localStorage or sessionStorage in the current page context. | `storage_type`, `key`*, `value`* |
| `browser_share_session` | Create a time-limited share token for a session. | `ttl_minutes` |
| `browser_trigger_cron_job` | Immediately trigger a cron job (internal - no webhook auth required). | `job_id`* |
| `harness_check_all_drifts` | Run drift checks for all staged skill candidates. | none |
| `harness_check_drift` | Re-run verifier checks for one staged skill candidate and write drift.json. | `skill_id`* |
| `harness_get_candidate` | Read one staged skill candidate by skill ID. | `skill_id`* |
| `harness_graduate` | Return the staged candidate for a converged run. | `run_id`* |
| `harness_list_candidates` | List staged skill candidates emitted by converged harness runs. | none |
| `harness_start_convergence` | Start an Agent Skill Induction convergence run from a task contract. | `contract`*, `provider`, `mock_final_observation`, `max_attempts` |
