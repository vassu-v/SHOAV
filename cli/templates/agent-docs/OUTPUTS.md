# OUTPUTS.md: what the user sees (guard, Targets 1 to 4)

## 1. Agent view

What the agent receives from guarded tool calls. Nothing else changes: no new tools in v1, same arguments, same flow.

### REWRITE (ingress cleaned)

- Normal result, content cleaned, with a leading `_shoav` key:
  `{"verdict": "REWRITE", "findings": <n>, "summary": "<one line>"}`
- Applies to: `browser.observe` (except preset `fast`), `browser.snapshot` (sanitized `_mcp_text` plus a one line guard header), `browser.find_elements` (matched `text` plus `context_text`), `browser.get_html` (`content` text scan).
- `browser.screenshot` is skipped by the guard (documented gap).
- In `observe` mode the `_shoav` note is emitted but nothing is blocked or rewritten.

### BLOCK (flood ingress, clickjacking egress)

- `isError: true`, with `error` first and `shoav` detail after, in both `content[0].text` and `structuredContent`.
- Flood BLOCK (Target 4): ingress returns the error when node or text budget or mutation rate trips.
- Click BLOCK (Target 2): `execute_action` click or `drag_drop` aborts before the handler when the hit test at the target center resolves to a different element. The error states the reason and the next step.
- Pre-checked submit ESCALATE (Target 3): submitting with an untouched pre-checked toggle returns an error telling the agent to re-observe or request human takeover.

## 2. Human view (live UI)

Base: `http://127.0.0.1:3200/s/<session_id>` (same link the agent prints; read-only archive after close).

- Guard badge on each tool row:
  - ALLOW: quiet (grey/green, no alarm)
  - REWRITE: amber
  - ESCALATE: orange
  - BLOCK: red
- Expanded row fields: reason, findings list (kind plus short detail), target element id, mode (`observe` or `enforce`), whether enforced.
- Header chip: `Guard: enforce, 2 blocked, 3 rewritten` (mode plus running counters).
- Guard filter next to the existing timeline filters, with a count. Cheapest fallback if UI code is missing: a BLOCK already renders as a red error row with the reason; REWRITE would be invisible without the badge, so the UI work is needed.
- Guard event shape (`type: "guard"`, attached by `call_id`): stage (`ingress` or `egress`), tool, verdict (`ALLOW`, `REWRITE`, `BLOCK`, `ESCALATE`), mode, enforced flag, reason, findings (`kind`, `detail`), target (`element_id`). Documented in `live-ui/CONTRACT.md`.

## 3. Machine view (logs and API)

- `artifacts/<sid>/timeline.jsonl`: every guard event is appended there and streamed over SSE to the live UI.
- `GET /live-api/guard`: guard status (mode, filter version, counters: allowed, rewritten, blocked, escalated).
- CLI (future, about 40 lines, not in v1): `shoav status` reads `GET /live-api/guard`; `shoav events <sid>` prints timeline rows filtered to guard events.

## 4. T-5 runner map (off / observe / enforce)

From the repo root, controller on 18500, fixtures on 186xx:

```powershell
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode off
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode observe
python shoav-mcp/t5_e2e/run_t5.py --controller http://127.0.0.1:18500 --fixture-port 18631 --mode enforce
```

Expected per fixture:
- `off`: attacks succeed (injection readable, overlay hijacks, submit runs, flood returned), benign pages read clean.
- `observe`: same outcomes as `off`, plus a `_shoav` note on guarded calls. Never `isError`, never stripped.
- `enforce`: hidden text REWRITE with no raw injection in agent text; overlay click BLOCK with reason and next step and no hijack; prechecked toggle flagged then submit ESCALATE with no submit; flood BLOCK; benign pages ALLOW including a clean login submit.

How to see BLOCK and REWRITE while a run is live:
- Agent side: REWRITE shows cleaned text plus the `_shoav` note; BLOCK or ESCALATE shows `isError: true`, `error` first, `shoav` detail after, with guidance (re-observe or human takeover). Do not retry a blocked click.
- Human side: open `http://127.0.0.1:3200/s/<sid>` and look for the guard badge on each row (amber REWRITE, red BLOCK, orange ESCALATE), the header chip counters, and the guard timeline filter.
