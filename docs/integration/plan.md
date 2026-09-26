# MCP/plan.md: integrating the S.H.O.A.V. filters into the Auto Browser MCP

Self-contained plan. Hand this file to any lead agent and tell it to run subagents per category below.
Everything here is grounded in a read-only research pass over `shoav-mcp/MCP/auto-browser` and `shoav-mcp/filters`
(line numbers are approximate, from 2026-09-25; re-check before editing).

Ports: controller 18500, live UI 3200, fixture server 186xx. Never use 8000, 18480, or 3100.

## 1. Goal and scope

Build a guard inside the Auto Browser controller so that any MCP-capable agent gets protection with no client
changes, and a human can watch it work.

Current scope is Targets 1 to 4 only:
1. Hidden text prompt injection (ingress): removed from what the agent reads.
2. Clickjacking overlay (egress): the click is aborted with an explanation.
3. Pre-checked consent toggle (ingress flag, egress escalate on submit).
4. Context flooding: node and text budget, mutation-rate decision.

Out of scope: Target 5 (cart), confirmshaming and other language-level patterns (skill layer), image-borne text.
Pass means the task completed AND zero compromise events. Any LLM stays advisory and can only escalate.

## 2. What exists

- `shoav-mcp/filters/`: pure Python decision core (ingress, egress, session state), 90 tests passing, JS probes
  verified in real Chromium. See `filters/plan.md`.
- `shoav-mcp/MCP/auto-browser/`: FastAPI controller (MCP at `/mcp`), live view recorder, Next.js live UI on 3200,
  native start script. Its own git repo (upstream clone). Full suite 1092 passed.

## 3. Architecture

```
agent (Claude Code / agy / any MCP client)
   |  POST /mcp  tools/call
   v
routes/mcp.py -> mcp_transport.py (L221-237) -> tool_gateway/gateway.py call_tool
                                                   |
   _call_tool:  validate -> resolve session -> live_call.begin
                   [EGRESS hook]  (execute_action, drag_drop)   <- aborts before the handler
                result = await spec.handler(arguments)          (L233)
                   [INGRESS hook] (observe, snapshot, find_elements, get_html)  <- rewrites result dict
                _pack_result -> response
                   |
                LiveCall.guard(...) emits a "guard" event -> timeline.jsonl + SSE -> live UI badge
```

Key rules:
- The guard sees and rewrites the result DICT before `_pack_result`, so `content[0].text` and
  `structuredContent` both carry the rewrite. Claude Code reads structuredContent first; snapshot results
  omit structuredContent and use `_mcp_text`, so rewrite that key too.
- The guard calls `session.page.evaluate` in process. That bypasses the `eval_js` governed gate on purpose.
- Fail open on filter exceptions (log and emit a guard note) unless `SHOAV_GUARD_FAIL=closed`.
- Do not add a phase. `PHASES` is asserted in tests. Add a new event `type: "guard"` instead.

## 4. Where each part goes

Two repos are touched. Commit separately. The controller hook code goes in `shoav-mcp/MCP/auto-browser`
(a separate git repo). The reusable adapter goes in `shoav-mcp/connectors/`.

| Part | Location | Notes |
|---|---|---|
| Filter core, probes | `shoav-mcp/filters/` | exists, extend per `filters/plan.md` |
| Adapters (dict in, dict out, no controller imports) | `shoav-mcp/connectors/` (new) | `normalize_observe`, `snapshot_to_payload`, `find_elements_to_payload`, `get_html_to_payload`, `apply_rewrite`, `decision_to_egress_args`, `FORM_STATE_SCRIPT` runner |
| Guard object (`ShoavGuard`), loader | `auto-browser/controller/app/guard/` (new) | `guard.py`, `loader.py`, `session_cache.py` |
| Gateway hooks | `controller/app/tool_gateway/gateway.py` | ctor takes `guard=None`; egress between L226 and L233; ingress after L233 |
| Wiring | `controller/app/app_factory.py` (L73-85) | `ShoavGuard.from_settings(settings)`, None when off |
| Config | `controller/app/config.py` (near L96-106) | `SHOAV_GUARD_MODE=off|observe|enforce`, `SHOAV_FILTERS_PATH`, `SHOAV_GUARD_FAIL` |
| Start script | `auto-browser/scripts/start-local.ps1` (params L12-21, envMap L47-63) | `-Guard off|observe|enforce` |
| Live events | `controller/app/live/calls.py` | `LiveCall.guard(...)`; also a `guard` summary on the `end` event. Recorder needs no change (type override works). |
| Redaction | `controller/app/live/phases.py` | pass guard payloads through the existing redact and truncate helpers |
| Guard status route | `controller/app/routes/live_api.py` | `GET /live-api/guard` (mode, version, counters) |
| UI | `auto-browser/live-ui/` | types, reducer, badge, row and detail rendering, header chip, filter, contract doc |
| Import path | option A: `sys.path` bootstrap in `guard/loader.py` | root is `SHOAV_FILTERS_PATH` or `parents[6]/shoav-mcp`. Later: `pip install -e` with package renamed `shoav_filters`. |

## 5. Behaviour spec

Modes:
- `off`: no guard object, zero overhead.
- `observe`: run filters, emit guard events and a `_shoav` note, never block or rewrite.
- `enforce`: apply REWRITE and BLOCK.

Ingress (after the handler):
- `browser.observe` (skip preset `fast`): adapter builds payload from `interactables`, `text_excerpt`, `ocr.text`,
  and `form_controls` from the form probe (accessibility_outline is always unavailable in this build, and
  interactables carry no `checked`). Run `STYLE_PROBE_SCRIPT` via `session.page.evaluate` for `style_facts`.
- `browser.snapshot`: run on `_mcp_text`, write sanitized text back, prepend a one line guard header.
- `browser.find_elements`: run on concatenated `text` and `context_text`.
- `browser.get_html`: run text scan on `content`.
- `browser.screenshot`: skipped, documented gap.
- REWRITE result is a normal result with a leading `_shoav` key: `{"verdict":"REWRITE","findings":n,"summary":"..."}`.
  Never place instructions to the agent that derive from page content into the result.
- Ingress BLOCK (flood): `isError` true, `error` key first, then `shoav` detail.

Egress (before the handler, for `execute_action` click, plus `drag_drop` coordinates):
1. Resolve the target: `element_id` to `[data-operator-id="op-sN"]`, scroll into view, `bounding_box()`, centre point.
2. `build_hit_test_script(cx, cy, expected_ref)` via `page.evaluate`, then `EgressFilter.verify_click`.
3. BLOCK or ESCALATE: return early `McpToolCallResponse(isError=True)` with `{"error": "<reason>", "shoav": {...}}` in both
   `content[0].text` and `structuredContent`, `error` first so the timeline row shows it.
   ESCALATE text tells the agent to re-observe or request human takeover.
4. Selector only clicks: compare with `target.contains(top)`. Coordinate only clicks: decoy check only.
5. `type`: post-hoc `FOCUS_CHECK_SCRIPT` and `verify_input`, mark the call errored on BLOCK. Skip value compare when `sensitive`.
6. `press Enter` or click on a submit control (from the per session interactables cache): `verify_submission`.
7. After a successful click, select_option or type on an `element_id`: `mark_touched(session_id, element_id)`.
8. Reset the per session state on navigation (compare origin and path) and on `close_session`.

Not gated in v1 (documented): `eval_js`, `upload`, `navigate`, `hover`, vision clicks, non-MCP callers of
`manager.execute_decision`. A later hardening step moves egress into `actions.py click()` for full coverage.

## 6. UI, agent view, and human view

Agent sees:
- Rewritten content plus a small `_shoav` note, or an error explaining a block and what to do next.
- Nothing else changes. No new tools needed for v1, so tool name style is unaffected. (If `shoav.status` is added
  later, register it in a new pack, add it to `EXPECTED_OTHER` in `tests/test_live_view.py`.)

Human sees, in the existing live UI at `http://127.0.0.1:3200/s/<session_id>`:
- A guard badge on each tool row: ALLOW (quiet), REWRITE (amber), ESCALATE (orange), BLOCK (red).
- Expanded row: reason, findings list (kind, short detail), target element id, mode, whether enforced.
- Header chip: `Guard: enforce, 2 blocked, 3 rewritten`.
- A `guard` filter next to the existing timeline filters, with a count.
- Cheapest fallback (no UI code): a BLOCK already renders as a red error row with the reason. REWRITE would be invisible,
  so the UI work is needed.

Event shape (type override of the `tool` default):
```
{"type":"guard","event":"verdict","call_id":"...","session_id":"...","seq":N,"ts":"...",
 "stage":"ingress|egress","tool":"browser.observe","verdict":"ALLOW|REWRITE|BLOCK|ESCALATE",
 "mode":"observe|enforce","enforced":true,"reason":"...",
 "findings":[{"kind":"hidden_text","detail":"..."}],"target":{"element_id":"op-s4"}}
```
The reducer ignores unknown types today, so an old UI stays safe. Document the event in `live-ui/CONTRACT.md`.

CLI: not needed for v1. The UI plus `artifacts/<sid>/timeline.jsonl` already answer "what did the guard do".
Later (about 40 lines): `shoav status` (GET `/live-api/guard`) and `shoav events <sid>` (timeline filtered to guard events).

## 7. Task list and subagent categories

Run waves in order. Within a wave, every task can run in parallel. Each category may run several subagents,
one per task. Rule for every wave: the author of a detector never writes its test, and the reviewer is never the author.

### Wave 0: decisions (lead, 10 minutes)
- Confirm ESCALATE policy for v1 (returns error and tells agent to re-observe) and `SHOAV_GUARD_FAIL` default open.
- Confirm import strategy A (sys.path).

### Wave 1: foundations (parallel)
- Category FILTERS (owner of `shoav-mcp/filters`)
  - F-1 `IngressFilter` accepts `form_controls`; F-3 `FORM_STATE_SCRIPT`; F-4 mutation observer scripts; F-2 modal ESCALATE rule.
- Category ADAPTERS (owner of `shoav-mcp/connectors`)
  - A-1 payload normalizers for observe, snapshot, find_elements, get_html.
  - A-2 `apply_rewrite` and `_shoav` block builder, error detail builder.
  - A-3 egress arg builder and per session interactables cache.
- Category CONTROLLER (owner of `auto-browser/controller/app`)
  - C-1 config, loader, `ShoavGuard.from_settings`, app_factory wiring, start-local `-Guard`.
  - C-2 `LiveCall.guard`, `end` event guard summary, redaction, `GET /live-api/guard`.
- Category UI (owner of `live-ui`)
  - U-1 types, reducer (attach by `call_id`, stub rows), `countGuard`, tests.
  - U-2 `GuardBadge`, css variables, row and expanded panel, header chip, filter, CONTRACT.md.
- Category TEST-AUTHORS (independent of everyone above; write tests from this spec only)
  - T-1 adapter tests, T-2 guard hook tests with a fake gateway, T-3 reducer and UI tests, T-4 live-event tests.

### Wave 2: hooks (needs wave 1)
- Category CONTROLLER
  - C-3 ingress hook in `gateway._call_tool` after the handler, per tool, with mode semantics and fail open.
  - C-4 egress hook before the handler for click and drag_drop, target resolution, hit test, verdict response.
  - C-5 post-hoc type check, submit check, touched tracking, navigation and close reset.
- Category TEST-AUTHORS
  - T-5 end to end via `POST /mcp/tools/call` against tiny local fixture pages (hidden text, overlay, prechecked box).
    These are unit fixtures. The malicious test site stays with the teammate.

### Wave 3: verify (parallel)
- Category REVIEW (independent, read only, each writes findings)
  - R-1 correctness and security of hooks and adapters. R-2 UI and contract. R-3 false positive review on benign pages
    (Wikipedia, Hacker News, a login form, a cookie banner) run in observe mode.
- Category QA
  - Q-1 full backend suite plus filters suite plus frontend lint, typecheck, vitest.
  - Q-2 real agent runs: `mcp-test\run-claude.ps1` and `agy -p`, guard off versus enforce on the teammate's page.
- Category DOCS
  - D-1 update `AGENTS.md`, the skill, `context.md`, `progress.md`, README status. No em dashes.

Suggested subagent count: 5 to 6 in wave 1 (FILTERS, ADAPTERS, CONTROLLER x2, UI x2, TEST-AUTHORS), 3 in wave 2,
4 in wave 3. Estimated total: 5 to 7 hours to a verified guard.

## 8. Verification gates

- Wave 1 gate: filters suite, adapters suite, and existing controller suite (1092 passed) all green with guard `off`.
- Wave 2 gate: with guard `enforce` the fixtures produce exactly the expected verdicts, and benign fixtures produce ALLOW.
- Wave 3 gate: real agent run shows the attack succeeding with guard off and failing with guard on, and the UI
  shows the badges. Report failures with output. Say what was not tested.

## 9. Risks

- Filters were first run in a browser only in unit fixtures; real pages will surface probe bugs.
- Hit test false positives on legitimate modals, cookie banners and sticky headers. Tune in observe mode first.
- Iframes and Shadow DOM are not handled.
- TOCTOU between the guard probe and the real click. Closing it needs the in-service hook in `actions.py`.
- `op-sN` ids reset on navigation. FORM_STATE_SCRIPT must stamp with the same `window.__shoavSeq` counter.
- Claude Code passes only `structuredContent` when present. Guard notes must live inside the result dict.
- Compact result mode (planned in MCP/auto-browser) must run after the guard hook.
- Two repos: commit separately. The controller repo is an upstream clone with a large uncommitted tree; snapshot it first.
- The `shoav-mcp/MCP/auto-browser` `CLAUDE.md` says work only inside that folder. Writing to `shoav-mcp/` was not covered; confirm before agents write there.
- Do not push anything without an explicit instruction. Identity `vassu-v`, no Claude attribution.
