# Skills

Two agent skills ship with S.H.O.A.V. The `shoav` CLI installs them; you can also copy them by hand.

| Folder | Installed as | What it is | Who needs it |
|---|---|---|---|
| [`guide/`](guide/SKILL.md) | `shoav-guide` | How to start and drive the SHOAV MCP: the mental model, `shoav start`/`status`/`doctor`, the observe and act loop with exact arguments, what to do on REWRITE, ESCALATE and BLOCK, tested recipes and a tool reference per profile | Every agent that browses through the SHOAV MCP, and humans learning it |
| [`defense/`](defense/README.md) | `shoav` | The defence manual and audit scripts: how to spot dark patterns and hostile page content. Advice only, nothing is enforced | Agents that keep their own browser, and MCP users who want help with wording tricks the guard cannot see |

The guide is about the tool, the defence skill is about the web. With the MCP available, use it: it enforces.

## How they are installed

```bash
shoav install --agent claude --what both    # MCP config + shoav-guide + shoav (default)
shoav install --agent claude --what mcp     # MCP config + AGENTS.md block + shoav-guide
shoav install --agent claude --what skill   # shoav-guide + shoav, no MCP config
```

Each agent gets both folders side by side in its usual skills directory, for example
`.claude/skills/shoav-guide/` and `.claude/skills/shoav/`. Only `SKILL.md`, `references/` and `scripts/` are
copied. The full table per agent and scope is in [`../cli/README.md`](../cli/README.md).

By hand: copy `guide/` to `<skills dir>/shoav-guide/` and `defense/` to `<skills dir>/shoav/`.

Check the defence scripts with `sh defense/scripts/selftest.sh` (needs `node` and Python).
