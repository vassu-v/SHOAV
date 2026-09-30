# MCP tool surface: smoke results

Every tool the controller advertises, called through both transports: REST
`POST /mcp/tools/call`, and MCP JSON-RPC on `POST /mcp` (initialize, capture the
`MCP-Session-Id` header, `notifications/initialized`, `tools/list`, `tools/call`).
Produced by `e2e/tools_smoke.py` (stdlib only, serves `e2e/fixtures` itself):

```
python e2e/tools_smoke.py --controller http://127.0.0.1:18580 --profile full --fixture-port 18650
```

Controller for these numbers: raw uvicorn from `server/controller`, headless,
`SHOAV_GUARD_MODE=enforce`, `MCP_TOOL_NAME_STYLE=underscore`, default
`MAX_SESSIONS=1` and the default rate limit (120 requests per minute; the runner
honours HTTP 429 by waiting `retry_after_seconds`, like a well behaved client).

## How a result is classified

- **OK**: `isError` false.
- **clean error**: `isError` true with a short message that says what was wrong
  and what to do next.
- **BUG**: HTTP 5xx, or a 4xx in place of a result; non-JSON; no reply within
  60 s; an empty or opaque message ("Tool execution failed" alone, or the
  generic internal-error text); a bare id as the whole message; a traceback; a
  local path (`C:\`, `/app/`); a raw exception class name; an unknown session
  accepted as real; or a sensitive typed value echoed back by a later call.

Cases per tool: a valid call against a fixture page; required arguments missing;
a wrong JSON type; a session id that never existed; the id of a session that was
created and then closed. Edge cases: overlay click and drag with the guard in
enforce (guard), a page that does not load (badnav), `wait_for_selector` on a
selector that never appears (timeout), and a `sensitive: true` type followed by
execute_action, observe, snapshot and find_elements (sensitive). "n/a" means the
case does not apply (no required arguments, or no `session_id`). Tools with no
arguments get `arguments` as a JSON array for the wrong-type case.

## Totals (after fixes)

| Profile | Tools | Transport | OK | Clean error | n/a | BUG |
|---|---|---|---|---|---|---|
| minimal | 10 | REST | 11 | 35 | 9 | 0 |
| minimal | 10 | MCP | 11 | 35 | 9 | 0 |
| curated | 37 | REST | 37 | 110 | 45 | 0 |
| curated | 37 | MCP | 37 | 110 | 45 | 0 |
| full | 74 | REST | 76 | 196 | 105 | 0 |
| full | 74 | MCP | 76 | 196 | 105 | 0 |

Before the fixes the full profile had 92 BUG rows on REST: 69 bare-id messages
for unknown or closed sessions, 9 HTTP 422 envelope replies, 7 bare-id messages
for unknown approvals, harness runs and skills, 3 opaque "Tool execution
failed", 2 unknown sessions accepted by the witness tools, and 2 error payloads
carrying local paths. Later runs exposed 4 more (items 6, 7, 8 and 9 below).

Valid calls that end as a clean error are expected in this setup: the feature
is not configured (proxy persona file, CDP endpoint), the default
`MAX_SESSIONS=1` blocks a second session (fork), or the smoke data does not
allow the action (single tab, finished job, no staged candidate). A closed
session reads as OK for tools that serve stored records (get_session,
verify_witness, export_witness_bundle, list_downloads, get_remote_access).

## Per tool (full profile, REST; the MCP transport gave identical results)

Profile is the smallest profile that advertises the tool (minimal is a subset of
curated, which is a subset of full).

| Tool | Profile | Valid call | Bad args (missing / wrong type) | Unknown session | Closed session | Notes |
|---|---|---|---|---|---|---|
| `browser_activate_tab` | minimal | OK | clean error / clean error | clean error | clean error |  |
| `browser_approve_approval` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_cancel_agent_job` | full | clean error | clean error / clean error | n/a | n/a | Smoke job had already finished: "Only queued or running jobs can be cancelled" |
| `browser_cdp_attach` | full | clean error | clean error / clean error | n/a | n/a | Needs a remote CDP browser; none in the test: "could not reach the target ... check the URL" |
| `browser_close_session` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_close_tab` | curated | clean error | clean error / clean error | clean error | clean error | Only one tab open: "Cannot close the only open tab in a session" |
| `browser_create_cron_job` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_create_proxy_persona` | full | clean error | clean error / clean error | n/a | n/a | Not configured: "No PROXY_PERSONA_FILE configured, cannot save proxy personas" |
| `browser_create_session` | minimal | OK | n/a / clean error | n/a | n/a | badnav (dead start_url): clean error "could not reach the target" |
| `browser_delete_cron_job` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_delete_memory_profile` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_delete_proxy_persona` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_discard_agent_job` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_drag_drop` | curated | OK | n/a / clean error | clean error | clean error | guard (overlay drag, enforce): clean error |
| `browser_enable_shadow_browse` | full | OK | n/a / clean error | clean error | clean error |  |
| `browser_eval_js` | curated | OK | clean error / clean error | clean error | clean error | Governed: parks an approval; after approve_approval the repeat with approval_id runs it (curated has no approve tool, so valid is a clean "not approved" error there) |
| `browser_execute_action` | minimal | OK | clean error / clean error | clean error | clean error | guard (overlay click, enforce): clean error; badnav (dead page): clean error; sensitive type then 4 follow-up calls: secret never echoed |
| `browser_execute_approval` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_export_script` | full | OK | n/a / clean error | clean error | clean error |  |
| `browser_export_witness_bundle` | curated | OK | n/a / clean error | clean error | OK |  |
| `browser_find_elements` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_fork_session` | curated | clean error | n/a / clean error | clean error | clean error | MAX_SESSIONS=1 (default): "Session limit reached ..." with the live session id; badnav: clean error |
| `browser_get_agent_job` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_get_auth_profile` | curated | OK | clean error / clean error | n/a | n/a |  |
| `browser_get_console` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_cookies` | full | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_html` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_local_storage` | full | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_memory_profile` | curated | OK | clean error / clean error | n/a | n/a |  |
| `browser_get_network_log` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_page_errors` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_remote_access` | full | OK | n/a / clean error | clean error | OK |  |
| `browser_get_request_failures` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_get_session` | curated | OK | n/a / clean error | clean error | OK |  |
| `browser_list_agent_jobs` | full | OK | n/a / clean error | OK | OK |  |
| `browser_list_approvals` | full | OK | n/a / clean error | OK | OK |  |
| `browser_list_auth_profiles` | curated | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_cron_jobs` | full | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_downloads` | curated | OK | n/a / clean error | clean error | OK |  |
| `browser_list_memory_profiles` | curated | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_providers` | full | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_proxy_personas` | full | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_sessions` | curated | OK | n/a / clean error | n/a | n/a |  |
| `browser_list_tabs` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_observe` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_pii_scrubber_status` | full | OK | n/a / clean error | n/a | n/a |  |
| `browser_queue_agent_run` | full | OK | clean error / clean error | clean error | clean error |  |
| `browser_queue_agent_step` | full | OK | clean error / clean error | clean error | clean error |  |
| `browser_readiness_check` | curated | OK | n/a / clean error | n/a | n/a |  |
| `browser_reject_approval` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_request_human_takeover` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_resume_agent_job` | full | clean error | clean error / clean error | n/a | n/a | Smoke job is not an agent_run: "Job is not resumable" |
| `browser_save_auth_profile` | curated | OK | clean error / clean error | clean error | clean error |  |
| `browser_save_auth_state` | full | OK | clean error / clean error | clean error | clean error |  |
| `browser_save_memory_profile` | curated | OK | clean error / clean error | clean error | clean error |  |
| `browser_screenshot` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_set_cookies` | full | OK | clean error / clean error | clean error | clean error |  |
| `browser_set_local_storage` | full | OK | clean error / clean error | clean error | clean error |  |
| `browser_set_viewport` | curated | OK | clean error / clean error | clean error | clean error |  |
| `browser_share_session` | full | OK | n/a / clean error | clean error | clean error |  |
| `browser_snapshot` | minimal | OK | n/a / clean error | clean error | clean error |  |
| `browser_stop_trace` | curated | OK | n/a / clean error | clean error | clean error |  |
| `browser_trigger_cron_job` | full | OK | clean error / clean error | n/a | n/a |  |
| `browser_verify_witness` | curated | OK | n/a / clean error | clean error | OK |  |
| `browser_wait_for_selector` | minimal | OK | clean error / clean error | clean error | clean error | timeout (missing selector, 1.5s): clean error "timed out ... re-observe" |
| `harness_check_all_drifts` | full | OK | n/a / clean error | n/a | n/a |  |
| `harness_check_drift` | full | OK | clean error / clean error | n/a | n/a |  |
| `harness_get_candidate` | full | clean error | clean error / clean error | n/a | n/a | No candidate staged in a fresh data dir: "... not found. Call harness_list_candidates" |
| `harness_get_status` | curated | OK | clean error / clean error | n/a | n/a |  |
| `harness_get_trace` | curated | OK | clean error / clean error | n/a | n/a |  |
| `harness_graduate` | full | clean error | clean error / clean error | n/a | n/a | Mock run did not stage a candidate: "Only converged runs with staged candidates can be graduated" |
| `harness_list_candidates` | full | OK | n/a / clean error | n/a | n/a |  |
| `harness_list_runs` | curated | OK | n/a / clean error | n/a | n/a |  |
| `harness_start_convergence` | full | OK | clean error / clean error | clean error | clean error |  |

## Bugs found and fixed

All fixes are in `server/controller`. Regression tests:
`server/controller/tests/test_shoav_tools_smoke.py` (22 tests, in process).

1. **Bare session id as the error.** Any session tool called with an unknown or
   closed session returned only the id (for example `'f4a484086e3f'`), because the
   `KeyError(session_id)` text was passed through. Now: "Session 'x' was not
   found or is already closed. Call browser_list_sessions to see live sessions,
   or browser_create_session to open a new one." The same mapping names agent
   jobs, approvals, harness runs, skill candidates and auth profiles, each with
   the list tool that shows valid ids. Hints use the advertised name style.
2. **Opaque "Tool execution failed" for browser errors.** Playwright timeouts
   and errors (`wait_for_selector` timeout, `create_session` with a dead
   `start_url`, `cdp_attach` to a closed port) fell into the catch-all. They now
   say "timed out", "could not reach the target" or "page was closed", with the
   first line of the browser error and a next step. The catch-all itself now
   names the tool and says to retry once, re-observe or open a new session.
3. **Local paths in error payloads.** A failed navigation returned
   `snapshot.screenshot_path` (`C:\Users\...`) and approval payloads returned
   `remote_access.info_path`. Error payloads now drop `*_path` keys that hold
   local paths (the `*_url` twins stay) and replace paths in error text with
   `<path>`. Success results are unchanged. Failed actions also carry a short
   `reason` (first line of the browser error).
4. **HTTP 422 for a malformed REST envelope.** `arguments` that is not an object
   returned FastAPI's raw 422. REST now returns an `isError` result that shows the
   expected shape. The JSON-RPC `-32602` reply now puts the field errors in the
   message and is always JSON serialisable.
5. **Witness tools accepted a session that never existed.** `verify_witness` and
   `export_witness_bundle` returned an empty "valid" chain for any id. They now
   need a live session or a stored record (closed sessions still work).
6. **A governed call on an unknown session parked an approval**, then failed on
   retry with an unhandled `PermissionError`. The governed gate now checks the
   session first, and `PermissionError` (approval not approved, approval for
   another session) comes back as "Not permitted: ... Check the approval with
   browser_list_approvals, or ask the user to approve it."
7. **`execute_approval` on a governed tool approval** failed with "Unsupported
   action: request_human_takeover". It now explains that such an approval is
   consumed by repeating the tool call with `approval_id`. Approval errors also
   carry a `next_step` field.
8. **Sensitive value leak (reported by the guide-skill agent).** After
   `execute_action type` with `sensitive: true`, the next result showed the typed
   value in `before.active_element.label`, because the page scripts fell back to
   a field's `value` for its label. `ACTIVE_ELEMENT_SCRIPT`, `INTERACTABLES_SCRIPT`
   and `PAGE_SUMMARY_SCRIPT` now read `value` only for button-like inputs. As a
   second layer the gateway remembers sensitive typed values (4 or more
   characters; also values the server auto-detected as sensitive) and replaces
   them with `[redacted]` in every later result, before the live timeline
   records it.
9. **Guard false positive on sensitive typing by selector.** In enforce mode a
   `type` with `sensitive: true` (or into a password field) addressed by CSS
   selector was always blocked as "Input focus deflection", because the selector
   string was compared with the focused element's operator ref. The gateway now
   resolves the selector to its ref first, and when the field has no ref yet it
   checks `document.activeElement.matches(selector)`. A real focus change is
   still blocked; guard fail-open semantics are unchanged.

## Known limits (not bugs)

- Rate limit: 120 requests per minute per client by default. A full two
  transport run is throttled about 40 times and waits it out (about 6 minutes).
- `eval_js` needs `workflow_profile=governed` and an approved approval. Curated
  has no approve tool, so a human approves through the live UI or REST.
- `find_by_vision` is not advertised without a vision provider, so it is not in
  the table.
