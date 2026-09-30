<div align="center">

<table align="center">
  <tr>
    <td align="left" valign="middle">
      <h1>S.H.O.A.V.</h1>
      <b>S</b>hield for <b>H</b>ostile <b>O</b>perations &amp; <b>A</b>gent <b>V</b>ulnerability
    </td>
    <td align="center" valign="middle">
      <h2>AI<br>BODYGUARD</h2>
    </td>
  </tr>
</table>

<br>

![Status](https://img.shields.io/badge/status-alpha,_active_development-f59e0b?style=flat-square)
![Core](https://img.shields.io/badge/core-deterministic-16a34a?style=flat-square)
![Works with](https://img.shields.io/badge/works_with-any_MCP_client-2563eb?style=flat-square)

<br>

<a href="docs/DESIGN.md">Design</a> &nbsp;·&nbsp;
<a href="AGENTS.md">Connect an agent</a> &nbsp;·&nbsp;
<a href="skills/README.md">Skills</a> &nbsp;·&nbsp;
<a href="docs/research/">Research</a>

<br>

</div>

An MCP server that gives any agent a real browser with a bodyguard in the path. It stops deceptive interfaces and
injected instructions before the agent acts on them. Think of it as a seatbelt for web agents. Pronounced "shop".

> [!NOTE]
> The four detection targets come from research and are measured against synthetic attack and benign pages. Thresholds are
> heuristics until they are tuned on real traffic. See [Honest limits](docs/DESIGN.md#8-honest-limits).

---

## Built on

<table>
  <tr>
    <td><a href="https://github.com/LvcidPsyche/auto-browser"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/readme/card-auto-browser-dark.svg"><img src="assets/readme/card-auto-browser-light.svg" alt="LvcidPsyche/auto-browser" width="400"></picture></a></td>
    <td><a href="https://github.com/purseclab/liteagent"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/readme/card-liteagent-dark.svg"><img src="assets/readme/card-liteagent-light.svg" alt="purseclab/liteagent" width="400"></picture></a></td>
  </tr>
  <tr>
    <td><a href="https://github.com/sst/opencode"><picture><source media="(prefers-color-scheme: dark)" srcset="assets/readme/card-opencode-dark.svg"><img src="assets/readme/card-opencode-light.svg" alt="sst/opencode" width="400"></picture></a></td>
    <td><picture><source media="(prefers-color-scheme: dark)" srcset="assets/readme/card-agy-dark.svg"><img src="assets/readme/card-agy-light.svg" alt="agy" width="400"></picture></td>
  </tr>
</table>

Auto Browser is MIT licensed and is included here in reworked form with its licence and credit. LiteAgent has no licence,
so none of its code is in this repo. agy is the reference test client. OpenCode is a further target.

## The problem

Developers now give AI agents a browser: coding agents, research agents, and automation agents reached through MCP.
Agents read the DOM or the pixels, not the way a person looks at a page, and hostile or deceptive pages exploit that.
Hidden text instructs the agent, invisible layers sit over the real button, boxes are ticked before the agent arrives,
and pages are stuffed to flood the agent's context.

Existing defenses are either an LLM judging the content, which the page can talk out of its warning, or a plugin tied to
one specific agent. There is no deterministic safety boundary between the model and untrusted web pages that works with
whatever agent you run.

S.H.O.A.V. is a browser MCP server with a deterministic guard in the path, plus a portable skill for agents that keep their
own browser. Any MCP capable agent can use it, and a human can watch every session in a live view.

## What is MCP?

The Model Context Protocol (MCP) is a standard way for an agent to call tools. An MCP server hands the agent a set of
tools, and here those tools drive a real browser. The agent needs no plugin and no code change, it only needs to be
pointed at the server's URL.

## What is in this repo

| Folder | What it is | Who needs it |
|---|---|---|
| [`server/`](server/SHOAV.md) | The SHOAV MCP server: a reworked Auto Browser with a real Chromium, a live view and the guard in the path | Anyone who wants enforcement |
| [`guard/`](guard/README.md) | The deterministic filters (`filters/`) and the adapters that connect them to the server (`connectors/`) | Contributors, and anyone auditing the rules |
| [`skills/`](skills/README.md) | Two agent skills: `guide/` teaches an agent (and you) how to start and drive the MCP; `defense/` is the defence manual and audit scripts for agents that keep their own browser (advice only) | Every agent that uses the MCP (guide); agents with their own browser (defence) |
| [`cli/`](cli/README.md) | The `shoav` installer and runner: writes agent config, starts and stops the server | Everyone, it is the easy path |
| [`e2e/`](e2e/README.md) | Synthetic attack and benign pages, and the runner that checks off, observe and enforce | Contributors, and anyone verifying an install |
| [`docs/`](docs/README.md) | Design notes, overview, the integration report and the research | Readers who want the evidence |
| `web/` | The project website | Nobody needs it to run the product |
| `assets/` | Images used by the docs | Nobody |

## Choose your path

| Path | What you get | Limits |
|---|---|---|
| Skill only | A defence manual and audit scripts your own agent follows in its own browser | Advice. Nothing is enforced, and the agent can ignore it |
| MCP only | A real browser for the agent, with the guard rewriting and blocking in the path, and a live view | The agent must use these tools for all browsing, and structural checks miss wording tricks like fake urgency |
| Both (recommended) | Enforcement for the structural traps, plus advice on the wording tricks a structural check cannot see | Each part keeps its own limits |

The skill is advice. The MCP enforces.

## Quick start

You need Python 3.11+ and Node.js 18+. Everything runs locally.

1. **Get the `shoav` command once.** It is a small Node CLI with no dependencies.

   ```bash
   npm install -g github:vassu-v/SHOAV
   ```

   Prefer not to install it globally? Prefix any command below with `npx github:vassu-v/SHOAV`.

2. **Install into a project.** From the folder your agent works in, run the interactive installer, or pass flags.

   ```bash
   shoav install
   # or non-interactive, for example Claude Code with both parts:
   shoav install --what both --agent claude --yes
   ```

3. **Start the server.** The first run creates a virtual environment in `~/.shoav`, installs the Python dependencies and Chromium.

   ```bash
   shoav start --ui
   ```

4. **Run your agent in that folder** and open the live link it prints for each session, `http://127.0.0.1:3200/s/<id>`.

Check the setup with `shoav status` and `shoav doctor`. Per-agent details, the file lists and troubleshooting are in
[`AGENTS.md`](AGENTS.md). Full CLI reference: [`cli/README.md`](cli/README.md).

<details>
<summary>Manual path, without the CLI</summary>

```powershell
# Windows, from the server folder
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start-local.ps1 -Port 18500 -Guard enforce -Background
```

```bash
# Linux and macOS, from server/controller, after pip install -r requirements.txt
# and python -m playwright install chromium
SHOAV_GUARD_MODE=enforce MCP_TOOL_NAME_STYLE=underscore ALLOWED_HOSTS='*' \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 18500
```

Then add the MCP to your agent by hand, for example `claude mcp add --transport http shoav http://127.0.0.1:18500/mcp` or
`agy mcp add --type http shoav http://127.0.0.1:18500/mcp`. The live view starts separately from `server/live-ui`
(`npm install`, `npm run build`, `npm start`). Copy-paste config for each agent is in
[`AGENTS.md`](AGENTS.md#manual-setup-without-the-cli), and server details are in [`server/SHOAV.md`](server/SHOAV.md).

</details>

## What you will see

Every session prints a live link, `http://127.0.0.1:3200/s/<id>`. Open it to watch each tool call, the latest screenshot,
and a guard badge on any row the guard touched. After the session closes, the same link is a read-only archive.

| Verdict | Badge | What the agent gets back |
|---|---|---|
| ALLOW | none | The normal result |
| REWRITE | amber | The normal result with dangerous text removed, and a leading `_shoav` note listing the findings |
| ESCALATE | orange | An error saying the action is suspicious but not provable, for example a form submitted with an untouched pre-ticked box. Re-check the form or ask a human |
| BLOCK | red | An error saying what was in the way, for example an invisible layer over the button. The agent should not retry the click |

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/screens/02-live-dark.png">
  <img src="assets/screens/02-live-light.png" alt="live session view with tool timeline and latest screenshot" width="820">
</picture><br><sub>The live view of an agent session. Guard badges appear on the tool rows.</sub></p>

## Use it in one project only

By default the installer works at project scope. It writes config only inside the directory you choose, so only agents
started in that folder get the SHOAV tools, and nothing global is touched. `--scope user` is there if you want it
everywhere. The exact files per agent are listed in [`AGENTS.md`](AGENTS.md#scoping-to-one-directory).

## Our approach: Tool-First Agent Diagnostic Design

Put the guard where every agent has to pass, at the browser. One MCP server owns the browser and checks each step.

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/architecture-dark.svg">
  <img src="assets/readme/architecture-light.svg" alt="agent, S.H.O.A.V. MCP server with ingress and egress filters, browser" width="820">
</picture></p>

- **A tool, not a plugin.** Most agents have no browser and cannot be extended, and the ones that can are each different.
  So the browser is the product. Claude, agy, OpenCode or any MCP client can use it, and it can be hosted once for everyone
  on your network. It is not locked to one agent.
- **Deterministic core.** The checks look at structure that page text cannot argue with: what is under the click, what is
  visible, what a form will submit. A model may advise, and it can only raise suspicion, never lower it.
- **Skill for the rest.** Agents that already have their own browser can use the S.H.O.A.V. skill. The skill is advice, the
  MCP is enforcement, and they work best together.

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/pipeline-dark.svg">
  <img src="assets/readme/pipeline-light.svg" alt="read page, ingress filter, agent decides, egress filter, action" width="820">
</picture></p>

## What it stops

| | Trap | What the guard does |
|---|---|---|
| 1 | Hidden text that tries to instruct the agent | Removes it before the agent reads the page |
| 2 | Invisible layer over the real button | Aborts the click and says why |
| 3 | Consent boxes ticked in advance | Flags them, and stops a submit that leaves them untouched |
| 4 | Pages stuffed to flood the agent's context | Caps and blocks the flood |

Every result is one of four verdicts:

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/verdicts-dark.svg">
  <img src="assets/readme/verdicts-light.svg" alt="ALLOW, REWRITE, ESCALATE, BLOCK" width="600">
</picture></p>

Guard modes are set with `--guard` on the CLI, or `SHOAV_GUARD_MODE` on the server: `off` costs nothing, `observe` logs and
annotates but never changes a result, `enforce` rewrites and blocks. A crashing filter fails open unless
`SHOAV_GUARD_FAIL=closed`. Rules are in [`guard/README.md`](guard/README.md), the server in [`server/SHOAV.md`](server/SHOAV.md),
and the synthetic pages plus the check runner in [`e2e/README.md`](e2e/README.md).

## Tech stack

<table>
  <tr><td><b>Guard core</b></td><td><img src="https://skillicons.dev/icons?i=py" alt=""> <img src="https://img.shields.io/badge/standard_library_only-3776AB?style=for-the-badge" alt="standard library only"></td></tr>
  <tr><td><b>MCP server</b></td><td><img src="https://skillicons.dev/icons?i=py,fastapi" alt=""> <img src="https://img.shields.io/badge/MCP_over_HTTP-111827?style=for-the-badge&logo=anthropic&logoColor=white" alt="MCP_over_HTTP"></td></tr>
  <tr><td><b>Browser</b></td><td><img src="https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright"> <img src="https://img.shields.io/badge/Chromium-4285F4?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Chromium"></td></tr>
  <tr><td><b>Live view</b></td><td><img src="https://skillicons.dev/icons?i=nextjs,ts,tailwind" alt=""> <img src="https://img.shields.io/badge/shadcn/ui-000000?style=for-the-badge&logo=shadcnui&logoColor=white" alt="shadcn/ui"></td></tr>
  <tr><td><b>State</b></td><td><img src="https://skillicons.dev/icons?i=sqlite" alt=""> <sub>audit, approvals, per-session timelines. All local.</sub></td></tr>
  <tr><td><b>Skill and CLI</b></td><td><img src="https://skillicons.dev/icons?i=nodejs,py" alt=""> <img src="https://img.shields.io/badge/Agent_Skill-7c3aed?style=for-the-badge&logo=markdown&logoColor=white" alt="Agent_Skill"> <sub>installed by the <code>shoav</code> CLI</sub></td></tr>
  <tr><td><b>Tests</b></td><td><img src="https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white" alt="pytest"> <img src="https://skillicons.dev/icons?i=vitest" alt=""> <img src="https://img.shields.io/badge/node:test-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="node:test"> <img src="https://img.shields.io/badge/real_Chromium_probes-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="real_Chromium_probes"></td></tr>
  <tr><td><b>Test clients</b></td><td><img src="https://img.shields.io/badge/agy-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="agy"></td></tr>
</table>

<sub>Python 3.11+ for the server. The guard rules are pure functions over plain data, so each one is testable without a browser.</sub>

## Status and honest limits

| Part | State |
|------|-------|
| Guard `guard/` | Done. Tested, JS probes verified in a real browser. |
| Server `server/` | Working natively with a live view. Guard hooked into the gateway. |
| Skills `skills/` | Defence skill done (manual and audit scripts). Guide skill added (how to drive the MCP, tested recipes). |
| CLI `cli/` | In development. |
| Status | Alpha, under active development. |

Measured on 2026-09-26 with a real Chromium on synthetic pages: enforce 27/27, observe 17/17, off 22/22 checks
([report](docs/integration/REPORT.md)). A real `agy` run confirmed hidden text stripped and the overlay click blocked.
Only `agy` has been measured as a client. Claude Code, OpenCode, Codex and Cursor are supported by configuration but not yet
measured. Tool profiles: 37 curated tools by default, 74 full, 10 with `MCP_TOOL_PROFILE=minimal`. Thresholds are heuristics
until tuned on real traffic. More in [`docs/DESIGN.md`](docs/DESIGN.md) and [`docs/OVERVIEW.md`](docs/OVERVIEW.md).

## Roadmap

What is next, in no fixed order:

- Live DOM mutation-rate feed for the flood check
- Iframe and Shadow DOM hit testing
- Tune thresholds on real page traffic
- ESCALATE instead of BLOCK for legitimate modals
- Measure more agent clients (Claude Code, OpenCode)
- Publish the CLI and skill package to npm
- Evaluate against public agent benchmarks such as TrickyArena

<details>
<summary>Why a deterministic core instead of asking a model?</summary>

A model can be talked out of a warning by the page it is reading. Structural checks cannot: the page either has an
element under the click or it does not. A model may advise, and it can only raise suspicion, never lower it.

</details>

<details>
<summary>My agent already has a browser. Do I need the MCP?</summary>

You can use the skill alone for advice, but only the MCP enforces. If you can, point the agent at the MCP instead, or
install both with `--what both`.

</details>

<details>
<summary>What is out of scope?</summary>

Language-level tricks such as fake urgency (the skill covers those), text inside images, and cart-level checks that are
site specific. See the design notes for the full list.

</details>

---

<br>

<div align="center">

**[Vassu-V](https://github.com/Vassu-V)**
&nbsp;&nbsp;·&nbsp;&nbsp;
**[str-VaibhavThakkar](https://github.com/str-VaibhavThakkar)**

<br>

<sub>No agents were tricked into a free trial during the making of this project.<br>
Several were tempted.</sub>

<br>

</div>
