# S.H.O.A.V. design notes

Tool-First Agent Diagnostic Design. Companion to the README, not a second README. The README is the overview; this page is the dense one.
Everything marked as working here was run against the final code. The measured results are in section 10.

## 1. Why a tool, not a plugin

We were asked to build a middle layer between the agent and the web. Two obvious routes fail on reach:

| Route | Problem |
|---|---|
| Guard inside one agent (a plugin for Claude Code, agy, or similar) | Locks the defence to one carrier. Most agents cannot be extended this way at all. |
| Proxy in front of an agent's own browser | Most agents have no browser to proxy, and the ones that do rarely expose a hook we can use. |

So the browser itself is the product. We run one MCP server that owns the browser, and any agent that can call an MCP
tool gets a real Chromium with the guard already in the path. Claude, agy, OpenCode and anything else that speaks MCP
can use it. It runs over HTTP, so it can be hosted once and used by anyone on the same network.

Agents that already have their own browser can use the skill instead. The skill is advisory: it teaches the agent what
to check. The MCP is enforcing: it checks for the agent. They are meant to be used together where possible.

## 2. Two layers

| Layer | Where | What it does | Can it be argued with? |
|---|---|---|---|
| Deterministic guard | inside the MCP server | Checks structure: what is really under a click, what is visible, what a form will submit | No. It never reads page language as instructions. |
| Cognitive skill | in the agent | Teaches the agent to spot manipulation that needs language (confirmshaming, fake urgency, trick wording) | It is advice, not enforcement. |

Rule for any model in the design: it may raise suspicion and never lower it. Fooling it costs a false alarm, not a breach.

## 3. What the guard covers

Targets are drawn from the research in `docs/research/`. Each one is now measured against a fixture page (section 10); thresholds are still heuristics.

| # | Target | Mechanism | Layer | Deterministic check |
|---|---|---|---|---|
| 1 | Hidden text injection | display:none, opacity 0, font-size 0, off-screen, zero-width characters, HTML comments | ingress | Computed style and geometry, plus a Unicode and keyword scan. The hidden text is removed before the agent reads it. |
| 2 | Clickjacking overlay | Transparent or stacked element above the real target | egress | `elementFromPoint` at the target centre. If the top element is not the target or one of its children, the click is checked as a decoy. |
| 3 | Pre-checked consent | Marketing or sharing box already ticked | ingress and egress | Form state captured at load. Flagged at read time. A submit with the box untouched is held before the click reaches the page for selector-based clicks, including when the agent never called observe first. A submit clicked by `element_id` can currently skip this check; a fix is in progress and this row will be updated once it is verified. |
| 4 | Context flooding | Huge repeated DOM, rapid meaningless mutation | ingress | Node and text budgets are live. The mutation-rate check is wired to a live MutationObserver feed on observe and snapshot; its thresholds and sampling window are still being tuned. |

Out of scope by design: cart sneaking (site specific, cannot be hardcoded), language-level dark patterns (skill layer),
text drawn inside images.

## 4. Where the guard sits

```
agent  ->  POST /mcp tools/call
             |
             v
        gateway  ->  session resolved
             |          EGRESS check   (click, drag)      abort with a reason if it fails
             |          tool handler runs
             |          INGRESS check  (observe, snapshot, find_elements, get_html)   rewrite the result
             v
        result returned to the agent, and a guard event goes to the live view
```

Both channels an MCP result can use (`content[0].text` and `structuredContent`) carry the rewrite, because some clients
read only one of them. Guard notes live inside the result itself for the same reason.

## 5. Verdicts

| Verdict | Meaning | What the agent gets |
|---|---|---|
| ALLOW | Nothing found | The normal result |
| REWRITE | Something removed or flagged | The result with the dangerous parts removed and a short note saying what was removed |
| ESCALATE | Suspicious but not provably hostile (for example the click target is covered by an ordinary element, or a form is submitted with an untouched pre-checked consent box) | In enforce mode an egress action (click or submit) is held and the agent gets an error asking it to re-observe or request human takeover. An ingress ESCALATE is currently logged but the result is returned as is; holding it is being added. It is recorded as a guard event and counted. It does not create an approval record; the human decides through the live view. |
| BLOCK | Physical obstruction or flood | The action is not performed, with a plain reason |

Modes: `off` (no guard, zero overhead), `observe` (checks run and are logged; content is never rewritten and actions are never
blocked, but a flagged result carries an informational `_shoav` note), `enforce` (rewrites and blocks apply). The server's own
default is off; the `shoav` CLI and `scripts/start-local.ps1` start it in enforce. If a filter throws, the call fails open unless the fail policy is set to closed.

## 6. What the human sees

Every agent session gets an id and a link. The live view shows each tool call with its phase, arguments and result, the
latest screenshot, and an archive after the session ends. Guard events appear as badges on the tool rows, with the reason
and findings when a row is expanded, and a header chip with the counts. The same counters are served at `GET /live-api/guard`.

<!-- screenshots go here: assets/screens/live-list.png, live-session.png, guard-block.png, guard-rewrite.png -->

## 7. What we changed in the base project

The base is [Auto Browser](https://github.com/LvcidPsyche/auto-browser) by LvcidPsyche (MIT, copyright JAI Studios, see
`server/LICENSE`). We kept its browser control and MCP transport and changed:

- Runs natively with a visible Chromium, no Docker required.
- A live per-session view with a Next.js UI, and a timeline of every tool call.
- Real image screenshots the model can see, and a compact page snapshot tool with stable element references.
- Tool names that work in clients that reject dots.
- The guard, wired into the tool gateway through thin hooks (`controller/app/guard/`), behind an off, observe or enforce switch.
- Tool profiles: 37 curated by default, 74 full, or a 10 tool minimal profile (`MCP_TOOL_PROFILE=minimal`) so the tool list stays small for the agent.

## 8. Honest limits

- Keyword lists are pattern matching, not understanding. A paraphrased injection can pass the deterministic layer.
- Thresholds are heuristics until there is attack and benign data to tune them against.
- Iframes and Shadow DOM are not handled by the hit test.
- Only the MCP path is guarded. Other callers of the browser service are not.
- Text inside images is out of reach.
- A page that changes between our check and the click can slip through a small window.

## 9. Evidence

The research behind the targets is in `docs/research/` (`08-synthesis/SYNTHESIS.md`, then
`09-verification-closeout/CLOSEOUT.md` before citing any number).

## 10. Testing

Detector code and its tests are written by different people. A run passes only if the task completed and there were zero
compromise events. Unit fixtures are tiny synthetic pages. The malicious test site is maintained separately.

Measured on 2026-09-26 with a real headless Chromium, through `POST /mcp/tools/call`, using `e2e/run_t5.py`:

| Guard mode | Checks | Result |
|---|---|---|
| off | 22 | 22 pass. Attacks succeed, no guard markers appear, benign pages read clean. |
| observe | 17 | 17 pass. Guard notes are emitted, nothing is blocked or rewritten. |
| enforce | 27 | 27 pass. Hidden text is stripped, the overlay click is blocked, an untouched pre-checked submit is held, the flood is blocked, five benign pages stay ALLOW. |

Unit and integration suites: filters, connectors and CLI 268 passed; controller 1148 passed (plus 19 in one deselected
file that also passes); live UI lint, typecheck and vitest pass. A real `agy` run confirmed hidden text stripped and the
overlay blocked with no retry by the agent.

Not measured: Claude Code as a client, the live mutation-rate feed, screenshot text, and any external site.
The full report is [`integration/REPORT.md`](integration/REPORT.md), a historical record whose paths predate the restructure.

## 11. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Guard core (`guard/filters/`) | Python, standard library only | Pure functions over dicts. No browser, network or I/O in the rules, so each rule is unit testable and cannot be reached by page content. |
| Connectors (`guard/connectors/`) | Python, dict in and dict out | Adapters between the MCP payloads and the filter inputs. No controller imports, so they can be tested alone. |
| MCP server | Python 3.11+, FastAPI, uvicorn | MCP over HTTP (JSON-RPC at `/mcp`). Hostable once, usable from any machine on the network. |
| State | SQLite (`state.db`), JSON and JSONL files | Audit events, approvals, per-session timelines. All local, nothing uploaded. |
| Browser | Playwright 1.62, Chromium (visible) | Real rendering is required for style, geometry and hit tests. |
| Live view | Next.js 16, TypeScript, Tailwind CSS 4, shadcn/ui, SSE | A page per session at `/s/<id>`, live and archived. |
| Skill and CLI | Markdown plus Node and Python audit scripts, installed by the `shoav` CLI (Node) | Portable to any agent that supports skills or instruction files. |
| Tests | pytest, vitest, node:test, Playwright browser probes | Detector authors and test authors are different people. |
| Test clients | agy (measured) | Other MCP clients, such as Claude Code and OpenCode, are on the roadmap. |

## 12. How it was built

1. Research first: attack and dark-pattern literature, and what can be decided deterministically (`docs/research/`).
2. Chose the tool-first shape: extend an existing browser MCP instead of writing a proxy.
3. Reworked the base: native run, visible browser, live view, image screenshots, page snapshot with stable refs.
4. Built the guard core as an independent package with fixtures, then verified its JS probes in a real Chromium.
5. Wired it into the tool gateway through thin hooks and adapters, behind an off, observe or enforce switch.
6. Split work across parallel agents with separate authors, testers and reviewers, and reviewed every result by running it.

## 13. Repository map

| Path | What is there |
|---|---|
| `guard/filters/` | Deterministic ingress and egress rules, probes, session state, tests |
| `guard/connectors/` | Payload adapters between the MCP and the filters |
| `server/` | The browser MCP server, live UI and start scripts |
| `cli/` | The `shoav` installer and runner |
| `e2e/fixtures/` | Tiny synthetic pages for unit and end-to-end tests |
| `skills/` | The agent skills: `defense/` (defence manual and audit scripts) and `guide/` (how to drive the MCP) |
| `docs/integration/` | The integration plan and measured report (historical) |
| `web/` | The project website |
| `docs/research/` | Evidence base |
