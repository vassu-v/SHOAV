# S.H.O.A.V. Overview

**Shield for Hostile Operations & Agent Vulnerability**, an AI bodyguard for agents that browse the web.
**Maintainers:** Vassu-V and str-VaibhavThakkar
**Status:** alpha, under active development

---

## 1. The problem

Developers now give AI agents a browser: coding agents, research agents, and RPA or automation agents reached through MCP.
These agents read the DOM or the pixels, not the way a person looks at a page, and hostile or deceptive pages exploit that.

- Hidden text that instructs the agent. Research finds roughly 70% of validated prompt injections sit in non-rendered HTML
  (metadata, comments, zero-size CSS), invisible to a person but read by an agent.
- Invisible layers placed over the real button, so a click lands somewhere else.
- Boxes ticked before the agent arrives, such as consent and data-sharing toggles.
- Pages stuffed with filler to flood the agent's context.

Published work reports agents are about 2.3x more susceptible to dark patterns than humans (over 70% versus 31%, Stanford
DECEPTICON), and that reasoning models can rationalize manipulative choices.

Existing defenses are either an LLM judging content, which the page can talk out of its warning, or a plugin tied to one
specific agent. Some also cut legitimate task completion sharply. A developer has no deterministic safety boundary between
the model and untrusted web pages that works with whatever agent they run.

## 2. The solution

S.H.O.A.V. is a browser MCP server with a deterministic guard in the path, plus a portable skill for agents that keep their
own browser. Any MCP capable agent can use it, and a human can watch every session in a live view.

The guard checks structure that page text cannot argue with: computed CSS visibility, physical hit testing with
`elementFromPoint`, and form state. It prefers sanitizing to blocking a whole page, so the agent can still finish its task.
Pass means the task completed and there were zero compromise events. Any LLM in the design is advisory and can only raise
suspicion, never clear it.

### Features

- **Browser MCP with the guard wired in.** A reworked [Auto Browser](https://github.com/LvcidPsyche/auto-browser) in
  `server/`, running natively (no Docker) with a visible Chromium. The guard sits in the tool gateway behind
  `SHOAV_GUARD_MODE=off|observe|enforce`.
- **Four traps covered:** hidden text, invisible overlay, pre-checked consent, context flooding. Measured on synthetic pages:
  enforce 27/27, observe 17/17, off 22/22 checks (see `docs/integration/REPORT.md`).
- **Live view.** A per-session page streaming tool calls, screenshots and guard badges over Server-Sent Events, with a
  read-only archive afterwards.
- **Skill package.** `skill/`, a portable defence manual with audit scripts (hit testing, WCAG contrast, form audit,
  confirmshaming text normalization), installed by the `shoav` CLI (`--what skill`).
- **`shoav` CLI.** Installs the skill and MCP config into a project for Claude Code, OpenCode, agy, Codex or Cursor, and starts, stops and inspects the server.

## 3. Architecture and stack

Data flows in four stages:

1. **Agent call.** The agent sends standard MCP tool calls (observe, click, type and so on) to the S.H.O.A.V. server.
2. **Ingress filter.** Page results are checked on the way back: invisible nodes, comments and flooding content are stripped
   (`REWRITE`), or refused (`BLOCK`) if the page is an unrecoverable flood.
3. **Egress filter.** Before a click or submit runs, the guard runs `document.elementFromPoint(x, y)` on the live page to
   confirm the click target is what the agent meant, and holds submits that leave pre-checked boxes untouched.
4. **Execution and telemetry.** Verified actions run in Playwright Chromium. Events, screenshots and guard verdicts stream
   to the live view (port 3200) and are stored locally in SQLite.

Verdicts are ALLOW, REWRITE, ESCALATE and BLOCK.

**Stack:**

- Guard core: Python standard library only, pure functions over plain data (`guard/filters/`).
- MCP server: Python 3.11+, FastAPI, MCP over HTTP, on port 18500 by default.
- Browser: Playwright and Chromium.
- Live view: Next.js, TypeScript and Tailwind, on port 3200.
- State: SQLite, all local.
- Skill: Markdown manual with Node and Python audit scripts. CLI: Node.js.
- Reference test client: agy (Antigravity CLI). Other MCP clients are on the roadmap.

## 4. Status and roadmap

Alpha, under active development. The guard core, the skill and the gateway wiring are done and measured on synthetic pages.
A real `agy` run confirmed hidden text stripped and the overlay click blocked. Thresholds are heuristics until tuned on real
traffic.

Next:

- Live DOM mutation-rate feed
- Iframe and Shadow DOM hit testing
- Tune thresholds on real page traffic
- ESCALATE instead of BLOCK for legitimate modals
- Measure more agent clients (Claude Code, OpenCode)
- Ship the `shoav` CLI (in development)
- Publish the CLI and skill package to npm
- Evaluate against public agent benchmarks such as [TrickyArena](https://agenttrickydps.vercel.app)

Out of scope for now: language-level tricks such as fake urgency (the skill covers advice on these), text inside images, and
site specific cart checks. See [DESIGN.md](DESIGN.md) for limits and evidence.
