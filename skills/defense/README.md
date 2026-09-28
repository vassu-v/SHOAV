<div align="center">

<table align="center">
  <tr>
    <td align="left" valign="middle">
      <h1>S.H.O.A.V.</h1>
      <b>S</b>hield for <b>H</b>ostile <b>O</b>perations &amp; <b>A</b>gent <b>V</b>ulnerability
    </td>
    <td align="center" valign="middle">
      <h2>AGENT<br>SKILL</h2>
    </td>
  </tr>
</table>

<br>

![Type](https://img.shields.io/badge/type-agent_skill-2563eb?style=flat-square)
![Core](https://img.shields.io/badge/core-deterministic-16a34a?style=flat-square)
![Status](https://img.shields.io/badge/status-alpha,_active_development-f59e0b?style=flat-square)

<br>

</div>

## The problem

Human users rely on spatial awareness and intuition to avoid sketchy pop-ups, fake
download buttons, bait-and-switch checkboxes, and hidden subscription traps.

Autonomous web-browsing agents read the web mechanically, relying on raw DOM trees,
accessibility trees, or screen coordinates. Malicious sites exploit this blind spot
using agent-targeted dark patterns and UI traps to hijack automated workflows.

## What this is

This folder packages the S.H.O.A.V. defensive engine into a portable agent skill.

It equips any multimodal or DOM-driven agent with mathematical invariants (WCAG 2.1
contrast formulas, coordinate hit-testing, zero-default form auditing, and semantic
guilt normalization) to survive adversarial web interfaces.

<br>

## Setup

Install with the S.H.O.A.V. CLI (needs Node 18 or newer). Run it from your project folder:

```bash
# Pick your agent: claude | opencode | agy | codex | cursor
npx github:vassu-v/SHOAV install --what skill --agent claude

# Or, from a clone of this repo
node cli/bin/shoav.js install --what skill --agent claude
```

Flags: `--scope project|user` (project folder or your home folder), `--dir <path>` (custom
destination), `--dry-run` (show what would be written), `--yes` (skip prompts).

Manual fallback: copy this `skill/` folder to the place your agent reads skills from.

| Agent | Destination |
| :--- | :--- |
| Claude Code | `<project>/.claude/skills/shoav/` |
| OpenCode | `<project>/.opencode/skills/shoav/` |
| Cursor | `<project>/.cursor/skills/shoav/` |
| Antigravity CLI (`agy`), Codex | `<project>/.agents/skills/shoav/` |
| `agy` at user scope | `~/.gemini/config/skills/shoav/` |

```bash
# macOS / Linux
mkdir -p .claude/skills && cp -r skill .claude/skills/shoav
```
```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force .claude\skills | Out-Null; Copy-Item -Recurse skill .claude\skills\shoav
```

Copy the whole folder, not just `SKILL.md`, so `scripts/` comes along. Check the copy with
`sh scripts/selftest.sh` (needs `node` and `python3`).

<br>

## Using with any agent

**With the S.H.O.A.V. MCP (recommended).** The guard enforces these checks on every browser
action (MCP server key `shoav`, default URL `http://127.0.0.1:18500/mcp`, tools named
`browser_*`). The skill then explains what the guard blocks and how to recover.

**Antigravity CLI (`agy`) and Gemini CLI** auto-discover the skill in `~/.gemini/config/skills/`.
```bash
agy "Use the browser to shop for headphones, keeping the shoav skill active."
```

**Claude Code** loads `.claude/skills/shoav/SKILL.md` on its own. **OpenCode, Codex, Cursor** read
`.agents/skills/shoav/SKILL.md`. If your tool has no skill support, point its rules file
(`CLAUDE.md`, `AGENTS.md`, `.cursorrules`) at the installed `SKILL.md`.

**Agents that keep their own browser (Playwright, Puppeteer, Browser-Use).** Load `SKILL.md`
into the system prompt. Only if you have no guard and no page evaluator, use the fallback scripts
in `scripts/`:
- `audit_telemetry.js`, `inspect_zindex_overlays.js`, `calculate_contrast.js` are browser scripts.
  Evaluate their text in the page, for example `page.evaluate(fs.readFileSync('audit_telemetry.js', 'utf8'))`.
- `cart_invariants_auditor.py` and `semantic_normalizer.py` are plain Python, see the usage table in `SKILL.md` section 4.

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
