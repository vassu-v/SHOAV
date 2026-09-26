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

`shoav-skill` packages the S.H.O.A.V. defensive engine into a portable agent skill.

It equips any multimodal or DOM-driven agent with mathematical invariants (WCAG 2.1
contrast formulas, coordinate hit-testing, zero-default form auditing, and semantic
guilt normalization) to survive adversarial web interfaces.

<br>

## Setup

Install the skill into your agent's skills directory:

```bash
# Direct via npx (installs to ~/.gemini/config/skills/SHOAV_SKILLforAGENTS)
npx shoav-skill

# Or target Claude Code / Cursor
npx shoav-skill --target claude
npx shoav-skill --target cursor
```

Or copy the `skill/` folder manually into:
- **Antigravity CLI / IDE**: `~/.gemini/config/skills/SHOAV_SKILLforAGENTS/`
- **Claude Code**: `.claude/skills/SHOAV_SKILLforAGENTS/`
- **Cursor / Windsurf**: `.cursor/skills/SHOAV_SKILLforAGENTS/`

<br>

## Using with any agent

**Antigravity CLI (`agy`) & Gemini CLI**  
Auto-discovered when placed in `~/.gemini/config/skills/SHOAV_SKILLforAGENTS`.
```bash
agy "Use the browser to shop for headphones, keeping SHOAV_SKILLforAGENTS active."
```

**Claude Code, Cursor, & Windsurf**  
Reference the installed skill path in your project's `CLAUDE.md`, `.cursorrules`, or system instructions:
```markdown
Follow the defense protocols and 5-point verification checklist in:
- Claude Code: `.claude/skills/SHOAV_SKILLforAGENTS/SKILL.md`
- Cursor / Windsurf: `.cursor/skills/SHOAV_SKILLforAGENTS/SKILL.md`
(or `skill/SKILL.md` if copied directly into project root).
```

**Custom browser agents (Playwright, Puppeteer, Browser-Use)**  
- **Prompt level:** Load `skill/SKILL.md` into the agent's system prompt before navigation tasks.
- **Runtime hooks:** Execute the scripts in `skill/scripts/` (`audit_telemetry.js`, `inspect_zindex_overlays.js`, `cart_invariants_auditor.py`) to audit page overlays, contrast, and cart totals before dispatching clicks.

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
