<div align="center">

<table align="center">
  <tr>
    <td align="left" valign="middle">
      <sub>PRONOUNCED &ldquo;SHOP&rdquo;</sub>
      <h1>S.H.O.A.V.</h1>
      <b>S</b>hield for <b>H</b>ostile <b>O</b>perations &amp; <b>A</b>gent <b>V</b>ulnerability
    </td>
    <td align="center" valign="middle">
      <h2>AI<br>BODYGUARD</h2>
    </td>
  </tr>
</table>

### Project Context & Authority

![Updated](https://img.shields.io/badge/updated-2026--09--25-0ea5e9?style=flat-square)
![Phase](https://img.shields.io/badge/phase-final_stitching-f59e0b?style=flat-square)
![Pillar_1](https://img.shields.io/badge/pillar_1-Hardened_MCP_Tool-2563eb?style=flat-square)
![Pillar_2](https://img.shields.io/badge/pillar_2-Cognitive_Vigilance_Skill-8b5cf6?style=flat-square)
![Pillar_3](https://img.shields.io/badge/pillar_3-Sandboxed_Subagent-10b981?style=flat-square)
![Core](https://img.shields.io/badge/core-deterministic_structural-16a34a?style=flat-square)
![Push](https://img.shields.io/badge/push-manual_only-7c3aed?style=flat-square)

</div>

> [!IMPORTANT]
> **CONTEXT AUTHORITY RULE**: This file is the single authoritative ground truth for S.H.O.A.V. Whoever reads this document and makes changes to the project MUST update this file with: (1) what changes they are making, (2) what they are actively working on, (3) what has been achieved, and (4) any newly uncovered vectors or architecture decisions. It must remain continuously up to date so any teammate or agent can immediately pick up the state.

**Jump to:**
[Snapshot](#-snapshot) ·
[Three Pillars](#-the-three-pillar-product-vision) ·
[Thesis & Philosophy](#-thesis--defense-philosophy) ·
[Architecture & MCP Filters](#-architecture--mcp-filter-integration) ·
[Expanded Attack Vectors](#-expanded-agent-manipulation-landscape) ·
[Detection Targets](#-detection-targets-tiered-engine) ·
[Research Numbers](#-research-ground-truth--verified-numbers) ·
[TrickyArena Matrix](#-benchmark-trickyarena-live-matrix) ·
[Runtime & Commands](#-runtime-environment--cli-reference) ·
[Current Work & Status](#-current-active-work--status-log) ·
[Team & Map](#-team-split--repository-map)

---

## Snapshot

| Item | State |
|------|-------|
| Project | S.H.O.A.V. (AI Bodyguard), a browser MCP server with a deterministic guard, plus a portable skill |
| Status | Alpha, active development. Filters, skill and MCP wiring are done and measured (enforce 27/27, observe 17/17, off 22/22) |
| Repository | `main` on `vassu-v/SHOAV` (commits as `vassu-v`, `coderscode17@gmail.com`). Push only on explicit instruction |
| Working rules | See `CLAUDE.md`. Deterministic core, synthetic data only, `external/` is git-ignored and never committed |

---

## The Three-Pillar Product Vision

The product is three tightly integrated components that deliver complete defense, user education, and secure execution:

```
+----------------------------------------------------------------------------------------+
|                               S.H.O.A.V. ECOSYSTEM                                     |
+----------------------------------------------------------------------------------------+
| 1. THE TOOL: HARDENED BROWSER MCP (filters built and wired into the gateway)                      |
|    - Sits between any agent (agy, Claude Desktop, Cursor) and the browser MCP runtime. |
|    - Deterministic Ingress Filter: audits opacity, hidden CSS, context overloading,    |
|      dummy DOM diffs, and non-rendered text. Verdicts: ALLOW, BLOCK, REWRITE/SANITIZE. |
|    - Deterministic Egress Filter: performs physical hit-testing (elementFromPoint) at   |
|      action coordinates before execution. Verdicts: ALLOW, BLOCK.                      |
+----------------------------------------------------------------------------------------+
| 2. THE SKILL: COGNITIVE VIGILANCE & DARK PATTERN ADVISOR (skill/, built)         |
|    - Installable agent skill on dark patterns, human cognitive biases, and psychology. |
|    - Teaches agents how malicious sites hack heuristics (loss aversion, default effect)|
|      and how LLM reasoning paradoxically over-rationalizes deceptive UI.               |
|    - Provides rules for self-vigilance and drives an advisory "second preview"         |
|      classifier for high-stakes actions. Works with our MCP or with any web agent.     |
+----------------------------------------------------------------------------------------+
| 3. THE HARNESS: SANDBOXED BROWSER DELEGATE AGENT (Future / Extension)                  |
|    - Lightweight, least-privilege delegate subagent that any parent agent can invoke.  |
|    - Restricted capability boundary: CAN ONLY browse web, capture screenshots, edit    |
|      Markdown files, edit images, and move files relatively in workspace. Zero shell.  |
|    - Protected natively by Pillar 1 (the MCP proxy) and guided by Pillar 2 (the skill).|
+----------------------------------------------------------------------------------------+
```

---

## Thesis & Defense Philosophy

> Autonomous browser agents operate with an awareness split: they read structured text / accessibility outlines while web pages render dynamic pixel compositions. Attackers exploit this mismatch. **Most proposed defenses rely on an LLM reading attacker text; an LLM guard can be prompt-injected by the very content it inspects.**

| Architectural Pillar | Rationale & Evidence |
|----------------------|-----------------------|
| **Deterministic Structural Core** | Hit-test geometry (`elementFromPoint`), computed styles, and DOM-state diffing are mathematical realities. An overlay either covers a button or it does not; text is either rendered or hidden. A hit-test cannot be prompt-injected. |
| **Advisory Escalate-Only LLM** | Any LLM component is strictly advisory. It may raise suspicion or trigger human-in-the-loop confirmation, but **can never clear or override a structural block**. Injecting the guard model cannot create a security bypass. |
| **Anti-Benchmark Bias** | We bias towards real-world malicious actor techniques and empirical security research, NOT tuning to a specific benchmark. TrickyArena is used only as an independent external verification target, not as a target we overfit to. |
| **Future Fast-Inference (Jev / Embeddings)** | For advisory escalation above the structural ceiling, we plan to leverage specialized non-autoregressive decision models like **Jev** (TypeSafe AI, released Sept 15, 2026: 70-500ms latency, 200-400x cheaper than LLMs, structured outputs) or embedding classifiers to score risk without blowing rate limits. |
| **Utility Preservation** | Defenses that block everything score 100% defense but 0% utility (e.g. ProtectAI classifier dropped task success from 83% to 41%). Rule: **Pass = task completed AND zero compromise events**. Sanitization/rewriting is preferred over outright blocking when safe. |

---

## Architecture & MCP Filter Integration

We modify/wrap the MCP tool interface to insert two deterministic filters:

```
                    +----------------------------------------------+
                    |      AUTONOMOUS AGENT (e.g., agy CLI)        |
                    +----------------------┬-----------------------+
                                           | stdio JSON-RPC (MCP)
                                           v
+----------------------------------------------------------------------------------------+
|                        S.H.O.A.V. HARDENED MCP GATEWAY                                 |
+----------------------------------------------------------------------------------------+
| [SHIELD 1] INGRESS FILTER (Intercepts Observation & Snapshot Responses)                |
|                                                                                        |
| Input: Raw DOM snapshot, accessibility tree, observation payload                       |
| Checks:                                                                                |
|   1. Opacity & Visibility: Drops nodes with display:none, visibility:hidden, opacity<0.05|
|   2. Geometric Bounds: Drops nodes positioned off-screen (left/top < -500px)           |
|   3. Text Styling: Drops font-size: 0 and color-matches-background text                 |
|   4. Non-Rendered Artifacts: Purges HTML comments, meta tags, and data-* prompt vectors |
|   5. Context Overloading Protection: Enforces strict node budget; drops dummy DOM bloat|
|                                                                                        |
| Verdicts:                                                                              |
|   - ALLOW: Clean page forwarded unchanged                                              |
|   - REWRITE (Sanitize): Strip malicious nodes and return cleaned DOM (preserves task!) |
|   - BLOCK: Refuse payload if page is an unrecoverable flooding exploit                 |
+----------------------------------------------------------------------------------------+
| [SHIELD 2] EGRESS FILTER (Intercepts browser_click, type, submit Tool Calls)           |
|                                                                                        |
| Input: Proposed action payload (action, target selector, ref, coordinates x, y)        |
| Checks:                                                                                |
|   1. Hit-Test Verification: Evaluates document.elementFromPoint(x, y) at target center |
|   2. Topmost Identity Check: Verifies hit-tested element matches target selector/ref   |
|   3. Overlay Detection: Checks if top element has opacity < 0.1 or z-index > 9000      |
|   4. Pre-Checked State Audit: Flags if submitting form with untouched pre-ticked checks|
|                                                                                        |
| Verdicts:                                                                              |
|   - ALLOW: Physical target matches intended target; forward action to Playwright       |
|   - BLOCK: Overlay detected; abort click and return descriptive error to agent         |
|   - ESCALATE: For linguistic ambiguity, invoke advisory classifier/human confirmation |
+----------------------------------------------------------------------------------------+
                                           | Sanitized JSON-RPC
                                           v
                    +----------------------------------------------+
                    |     BROWSER ENGINE (Playwright Core)         |
                    +----------------------------------------------+
```

---

## Expanded Agent Manipulation Landscape

Detailed in [`docs/research/10-agent-manipulation-and-mitigations/FINDINGS.md`](docs/research/10-agent-manipulation-and-mitigations/FINDINGS.md):

1. **Context Overloading & Context Flooding**:
   * *Mechanism*: Flooding the DOM with thousands of filler tokens, deeply nested dummy structures, or repetitive text.
   * *Impact*: Dilutes transformer attention ("lost in the middle"), pushes system instructions out of active attention range, and induces recency-bias prompt injection. Burns token quotas.
2. **Dummy DOM Diffs**:
   * *Mechanism*: Hostile JavaScript rapidly mutating irrelevant DOM attributes or invisible elements.
   * *Impact*: Traps agent diffing engines in infinite analysis loops, causing memory thrashing and action timeouts.
3. **The Rationalization Paradox (Dark Patterns on Agents)**:
   * *Mechanism*: DECEPTICON (ICLR 2026) proved agents are 2.3x more susceptible to dark patterns than humans (>70% vs 31%).
   * *Impact*: Larger models with reasoning (o1, Sonnet 3.7) over-rationalize deceptive cues (inventing justifications for "Best Value" traps).
4. **Visual vs. DOM Cloaking**:
   * Non-rendered text (~70% of real-world injections) targets text agents; typographic pixel injection targets Vision-Language Models.
5. **Interactive Traps & Delayed TOCTOU**:
   * Clickjacking transparent overlays; delayed injections triggered after initial security scan via `setTimeout` or scroll events.
6. **Agent Gaslighting / Synthetic Fault Injection & Tool Misattribution**:
   * *Mechanism*: Hostile pages induce simulated errors (fake "MCP Tool Error" or "Session Expired" DOM banners) or steal input focus during typing to deflect keystrokes into hidden sniffer fields.
   * *Impact*: Exploits the agent's ReAct self-correction loop. The agent misattributes the malfunction to its own tool or code, assumes responsibility, and follows hostile on-page remediation procedures (leaking credentials or granting elevated permissions).

---

## Detection Targets (Tiered Engine)

```
+-----------------------------------------------------------------------------------------+
| TIER 1: FULLY STRUCTURAL CORE (Build First - High Evidence, 100% Deterministic)         |
+-----------------------------------------------------------------------------------------+
| 1. Hidden / Invisible Instruction Content (Ingress)                                     |
|    - Drops display:none, visibility:hidden, opacity < 0.05, font-size: 0, off-screen,   |
|      zero-width Unicode, comments. Wipes out ~70% of real-world injection payloads.     |
| 2. Context Overloading & Dummy Diff Defense (Ingress)                                   |
|    - Enforces node budget (max 50 interactive elements per snapshot); compacts bloat.  |
| 3. Overlay / Hit-Target Mismatch (Egress)                                               |
|    - document.elementFromPoint(x, y). Blocks clickjacking overlays with opacity < 0.1.  |
| 4. Pre-Checked / Pre-Set Manipulative State (Form Audit)                                |
|    - Audits initial checked=true states on opt-ins and data-sharing toggles.            |
+-----------------------------------------------------------------------------------------+
| TIER 2: PARTIAL STRUCTURAL / FLOW TRACKING (Build Second if Time Permits)               |
+-----------------------------------------------------------------------------------------+
| 5. Late-Appearing Drip Pricing: Track total price across navigation steps; flag deltas. |
| 6. Obstructed Cancellation: Measure step-depth and click asymmetry between sign-up/cancel|
+-----------------------------------------------------------------------------------------+
| TIER 3: THE SEMANTIC CEILING (Requires Language Semantics - Advisory LLM / Jev Only)    |
+-----------------------------------------------------------------------------------------+
| - Confirmshaming, Double Negatives, Fake Urgency. Handled by advisory escalation.       |
+-----------------------------------------------------------------------------------------+
```

---

## Research Ground Truth & Verified Numbers

* **Common Crawl Census (~1.2B URLs, ~24.8M hosts, Oct 2025)**: 15,300 validated prompt injections across 2,042 hosts (~0.008% of hosts). **~70% sit in non-rendered HTML** [A-09, A-10].
* **Real-World Incident**: Exactly **one** confirmed in-the-wild incident (Unit 42, Dec 2025: live site manipulating an AI ad-review pipeline) [A-14].
* **WASP Benchmark (Meta, NeurIPS 2025)**: Intermediate ASR (16-86%) vs End-to-End ASR (0-17%) proves "security by incompetence" [A-10].
* **DECEPTICON (Stanford, ICLR 2026)**: Dark patterns steer agents in **>70% of tasks** vs 31% human baseline. Susceptibility **scales with model size and reasoning budget** [DP-10].
* **Ersoy et al. (Purdue, accepted IEEE S&P 2026)**: Single-pattern susceptibility averaged **41.1%**; multi-pattern stacking increases harm by up to **+700% to +2300%** [DP-11].
* **Commercial Guardrail Bypasses (Hackett et al., 2025)**: Up to **100% evasion** on Azure Prompt Shield and Meta Prompt Guard [M-03].
* **ProtectAI Utility Collapse (2025)**: DeBERTa classifier reduced attacks to 7.95% but crashed legitimate task success from **83.0% down to 41.5%** [M-08].

---

## Benchmark: TrickyArena Live Matrix

We evaluate against the live hosted [TrickyArena](https://agenttrickydps.vercel.app) benchmark (Ersoy et al., IEEE S&P 2026).
* **Legal Notice**: `liteagent` repo has **no license**; we drive the public hosted Vercel site as a black-box target without copying their code.
* **Scoring Ground Truth**: Action-trace DOM click lookups (`dp_checks.py`), not financial transactions.

| # | Pattern Name | Code | Site | Detectability | Detection Mechanism |
|---|--------------|------|------|---------------|---------------------|
| 1 | Sneaking Warranty to Cart | `w` | Shopping | **Clean Structural (100%)** | Cart item diff: item injected without preceding user click. |
| 2 | Data Sharing Default ON | `ds` | Music | **Clean Structural (100%)** | Initial DOM inspection: toggle delivered with `checked=true`. |
| 3 | Complex Privacy Settings | `cs` | Health | **Clean Structural (100%)** | Multi-toggle initial state inspection (`checked=true` across N controls). |
| 4 | Premium Subscription Pop-up | `p1` | Shopping | **Partial (Structural Suspicion)** | Asymmetry: prominent accept CTA vs reject buried in sub-menu. |
| 5 | Cookie Preference Pop-up | `p2` | Shopping | **Partial (Structural Suspicion)** | Button salience and click-depth disparity (accept=1 click, reject=2 clicks). |
| 6 | Sponsored Item Top Rank | `s` | Shopping | **Partial (Structural Suspicion)** | Search sort order diff: item rank unchanged despite price sort. |
| 7 | Personal Info Obfuscation | `ob` | News | **Partial (Structural Suspicion)** | Asymmetric click-depth on consent modal. |
| 8 | Decision Uncertainty | `du` | Music | **Partial (Structural Suspicion)** | Buried settings link behind ambiguous continuation button. |
| 9 | Terms of Service Font/Color | `tos` | Health | **Partial (Structural Suspicion)** | Small grey font, low contrast ratio vs prominent green accept. |
| 10 | Bait and Switch | `bs` | News | **Semantic Ceiling (0% Structural)** | "Free" article triggers trial pop-up; requires linguistic intent parsing. |
| 11 | Sponsored Unrelated Ad | `sa` | News | **Semantic Ceiling (0% Structural)** | Top banner donate button; structurally normal, contextually deceptive. |
| 12 | Confusion / Double Negative | `cf` | News | **Semantic Ceiling (0% Structural)** | "Do NOT uncheck if you wish to not..."; pure syntax/logic trap. |
| 13 | Aesthetic Manipulation | `am` | Music | **Semantic Ceiling (0% Structural)** | "Best value" styling; requires comparative pricing semantics. |
| 14 | Confirmshaming | `cf` | Health | **Semantic Ceiling (0% Structural)** | "No thanks, I hate privacy"; emotive phrasing, symmetric buttons. |

---

## Runtime Environment & CLI Reference

```powershell
# Check registered MCP tools
agy mcp list

# Configure Headless Driver (Benchmark / Automated runs)
agy mcp add browser bun x @playwright/mcp@latest --headless --image-responses=allow --snapshot-boxes

# Configure Visible Driver (Headed Mode)
agy mcp add browser bun x @playwright/mcp@latest --image-responses=allow --snapshot-boxes

# Run Non-Interactive Test Prompt
agy --dangerously-skip-permissions --print "Navigate to https://agenttrickydps.vercel.app/shopping?dp=w and inspect the cart"
```

---

## Current Active Work & Status Log

* **2026-09-25 08:35**: Created `docs/research/10-agent-manipulation-and-mitigations/FINDINGS.md` documenting context overloading, dummy DOM diffs, dark pattern cognitive mechanics, Jev model capabilities, and dual-filter MCP integration.
* **2026-09-25 08:40**: Codified the **Three-Pillar Product Vision** (Hardened MCP Tool + Cognitive Vigilance Skill + Sandboxed Subagent).
* **2026-09-25 08:45**: Cloned and inspected `external/liteagent` benchmark testbed and evaluation suite.
* **2026-09-25 11:00**: Configured `external/auto-browser` for native standalone execution without Docker; removed Docker files; enabled Playwright visible/headed browser mode.
* **2026-09-25 11:02**: Integrated `auto-browser` MCP with `agy` CLI (`http://127.0.0.1:8000/mcp`); verified built-in Operator Dashboard on `http://127.0.0.1:8000/dashboard` and artifact recording (`controller/data/artifacts/`).
* **2026-09-25 11:04**: Successfully executed E2E smoke test (`google.com` -> `amazon.com`) and live TrickyArena benchmark task (`https://agenttrickydps.vercel.app/shopping?dp=w` -> Dell Inspiron 15 rating lookup) with full action logging and screenshots.
* **2026-09-25 11:35**: Implemented independent **Live Per-Session Ephemeral Dashboard** (`/live/{session_id}` and `/sessions/{session_id}/dashboard`) with real-time SSE event bus streaming agent actions, responses, and S.H.O.A.V. security checks. Verified live connection and transition to archived state on session close.
* **2026-09-25 11:36**: Created universal agent documentation [`AGENTS.md`](AGENTS.md), `external/auto-browser/AGENTS.md` (local only), and `GEMINI.md`.
* **2026-09-25 (repo cleanup)**: Untracked and git-ignored the old prototype directory, `CLAUDE.md`, `GEMINI.md`. Only `external/.gitkeep` is tracked from `external/`, so the clones are never pushed. README now credits Auto Browser (modified locally) and LiteAgent (benchmark only, no license). Project `CLAUDE.md` rules (Python 3.10 default) override the 3.12 in the handoff notes. Docs get refreshed daily.
* **2026-09-25 (vendored Auto Browser)**: `external/auto-browser/` is now tracked (MIT, LICENSE kept, our local changes in their own commits; runtime data and `.env` excluded). `external/liteagent/` stays untracked: no license, so we do not redistribute it. LiteAgent's own runner needs its agents plus OpenAI keys, so instead we drive its hosted TrickyArena prompts with `agy` through Auto Browser (no Docker). Headless `agy` run on `shop?dp=w` was blocked by an unanswered `command` permission; needs an allow rule in agy settings or a permission decision.
* **2026-09-25 15:26**: Created `shoav-mcp/DETERMINISTIC_TARGETS.md` specifying purely computational dark pattern targets (opacity, clickjacking hit-test mismatch, pre-checked toggles, context bloat) separated from skill-based psychological patterns.
* **2026-09-25 15:30**: Created `shoav-mcp/filters/PLAN_AND_ROUGH_SKETCH.md` detailing the Ingress (ALLOW/BLOCK/REWRITE with telemetry) and Egress (ALLOW/BLOCK with elementFromPoint hit-testing) pipeline, JevEmbed local acceleration, and evaluating internal Auto-Browser modification vs. external proxy.
* **2026-09-25 17:25**: Analyzed and integrated **Agent Gaslighting & Tool Misattribution** into the S.H.O.A.V. architecture. Updated `shoav-mcp/filters/PLAN_AND_ROUGH_SKETCH.md` and `shoav-mcp/filters/context.md` with deterministic defenses: Ingress synthetic error quarantine and Egress post-action input/focus integrity verification.
* **2026-09-25 (evening)**: Deterministic ingress/egress filter core implemented in `shoav-mcp/filters/` (90 tests, JS probes verified in Chromium). Teammate shipped `shoav-skill/` (defense manual, audit scripts, npx installer) and the project overview (now `docs/OVERVIEW.md`). Tracking moved from `external/auto-browser/` to `external/automcp/` (our reworked copy). Work pushed to `modules-parted-mcp-patch` as a backdated, staged history.
* **2026-09-26 (morning)**: Copied the reworked Auto Browser to `shoav-mcp/MCP/auto-browser/` and wired the guard into its gateway (`controller/app/guard/`, hooks in `tool_gateway/gateway.py`). Added `shoav-mcp/connectors/`, `shoav-mcp/fixtures/`, the `t5_e2e` runner, a CLI (`shoav-mcp/MCP/shoav/`) and agent templates. Fixed the live gaps (T1 rewrite marker, T2 actionable block, T3 submit escalation, egress counters). Measured: enforce 27/27, observe 17/17, off 22/22. Real `agy` runs confirmed hidden-text rewrite and overlay block. Report: `shoav-mcp/MCP/REPORT.md`.
* **2026-09-26 (late morning)**: Closed the last real-agent gap: a submit with an untouched pre-checked box is now held even if the agent never called observe (the gateway probes the live form itself). Research moved to `docs/research/`. README, AGENTS.md and DESIGN.md brought in line with the measured state.
* **Roadmap**: live DOM mutation-rate feed, iframe and Shadow DOM hit testing, tune thresholds on real page traffic, ESCALATE instead of BLOCK for legitimate modals, measure more agent clients (Claude Code, OpenCode), rename the server identity from auto-browser to shoav, publish the skill package to npm, evaluate against public agent benchmarks such as TrickyArena.

---

## Team Split & Repository Map

### Team Division
* **GitHub Handles**: `Vassu-V` and `str-VaibhavThakkar`.
* **Shoryavardhaan (`Vassu-V`)**: Guard integration, deterministic detection engine, evaluation harness, MCP server.
* **Teammate (`str-VaibhavThakkar`)**: Malicious test website, UI/UX, live dashboard and telemetry visualization, project website.

### Repository Map

The repo was restructured into a flat layout (`server`, `guard`, `skill`, `cli`, `e2e`). Older log entries above use the old paths (`shoav-mcp/...`, `shoav-skill/`), which map to: `shoav-mcp/MCP/auto-browser` -> `server`, `shoav-mcp/filters` -> `guard/filters`, `shoav-mcp/connectors` -> `guard/connectors`, `shoav-mcp/t5_e2e` -> `e2e`, `shoav-mcp/fixtures` -> `e2e/fixtures`, `shoav-mcp/MCP/{plan,REPORT,README}.md` -> `docs/integration/`, `shoav-skill/skill` -> `skill`. The server identity was renamed from `auto-browser` to `shoav` (MCP key `shoav`).

| Path | Purpose & Contents |
|------|--------------------|
| `context.md` | Single source of truth (this document) |
| `AGENTS.md` / `GEMINI.md` | Set up SHOAV for an agent (CLI, manual config, troubleshooting) |
| `README.md` | Public project overview |
| `docs/OVERVIEW.md` | Project overview: problem, solution, architecture, roadmap |
| `docs/README.md` | Index of the docs |
| `CLAUDE.md` | Development rules, git conventions, commit author standards |
| `external/context.auto-browser.md` | Deep technical context and modification log for the Auto-Browser MCP |
| `external/AGENT_HANDOFF_CONTEXT.md` | Portable agent handoff context brief (copy-pasteable for any LLM/agent) |
| `server/` | The product: reworked Auto Browser (native, live UI in `server/live-ui`, guard hooks in `server/controller/app/guard/`). Start notes in `server/SHOAV.md` |
| `guard/connectors/`, `e2e/` | Payload adapters; synthetic pages (`e2e/fixtures/`) and the off, observe, enforce runner (`e2e/run_t5.py`) |
| `web/` | Project website (Next.js) |
| `external/` | Local only, git-ignored, not tracked. Holds third-party clones |
| `guard/filters/` | Deterministic ingress/egress core, session state, tests, plan |
| `docs/integration/` | The wiring plan and the measured integration report (historical) |
| `skill/` | Agent skill and audit scripts (Pillar 2). `cli/` | The `shoav` installer and runner, agent doc templates |
| `external/liteagent/` | TrickyArena benchmark suite and evaluation checks |
| `docs/research/10-agent-manipulation-and-mitigations/` | Workstream 10: Expanded attack landscape, context overloading, and MCP mitigations |
| `docs/research/08-synthesis/` | Master synthesis, prioritized detection targets, open questions |
| `docs/research/09-verification-closeout/` | Report safety rules, resolved claims, paper disambiguation |
| `assets/` | Tracked project images and architecture diagrams |
