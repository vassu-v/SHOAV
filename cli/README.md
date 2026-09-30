# shoav CLI

Installer and runner for S.H.O.A.V. (AI Bodyguard for agents that browse). One
Node command, no runtime dependencies. It writes your agent's MCP config and skills,
and starts, stops and inspects the guarded browser server.

## Requirements

- Node.js 18 or newer
- Python 3.11 or newer for `shoav start` (found as `py -3`, `python` or `python3`,
  or set `SHOAV_PYTHON` to its path)
- About 1 GB of disk for the venv and Chromium (first `shoav start` only)
- npm, only for `shoav start --ui`

## Usage

```
shoav                      guided install (same as shoav install)
shoav install --agent claude,opencode --yes
shoav start                start the server on 127.0.0.1:18500 (guard enforce)
shoav status               health, guard mode, verdict counters, session count
shoav events <session id>  guard timeline of one session
shoav open [session id]    print and open the live view link
shoav stop                 stop what shoav start launched
shoav doctor               check the setup, non-zero exit on failures
shoav <command> --help
```

### install flags

| Flag | Default | Meaning |
|---|---|---|
| `--what skill\|mcp\|both` | `both` | `skill`: both skills, no MCP config. `mcp`: MCP config, AGENTS.md block and the guide skill. `both`: everything (recommended) |
| `--agent <list>` | prompt | `claude,opencode,agy,codex,cursor,generic`; required when not in a terminal |
| `--scope project\|user` | `project` | write under `--dir` or under your home dir |
| `--dir <path>` | current dir | project root |
| `--url <url>` | `http://127.0.0.1:18500/mcp` | must be http(s) and end with `/mcp` |
| `--guard off\|observe\|enforce` | `enforce` | mode written into the AGENTS.md block |
| `--yes`, `-y` | | no prompts |
| `--dry-run` | | print exactly what would be written, write nothing |

Every write is idempotent (a second run changes nothing), JSON files are merged
(other keys kept), a file that is not valid JSON is never touched (the snippet to
add by hand is printed and the exit code is 3), and nothing is ever deleted.

### start flags

`--guard off|observe|enforce` (default enforce), `--port <n>` (default 18500),
`--headless`, `--ui` (build and serve the live view on port 3200), `--yes` (do not ask
before downloading Chromium). `stop`, `status`, `events` and `open` take `--port` too.

## What each agent target writes

With `--what mcp` or `both`, a "Browsing with SHOAV" block is also added to
`AGENTS.md` between `<!-- shoav:start -->` and `<!-- shoav:end -->` (replaced on re-install).

| Agent | Project scope (`--dir`) | User scope (home) |
|---|---|---|
| claude | `.mcp.json`, `.claude/settings.json` (allows `mcp__shoav`), `AGENTS.md`, `CLAUDE.md` with `@AGENTS.md`, skills in `.claude/skills/` | prints `claude mcp add --transport http --scope user shoav <url>` (never edits `~/.claude.json`), block in `~/.claude/CLAUDE.md`, skills in `~/.claude/skills/` |
| opencode | `opencode.json` (`mcp.shoav`, type remote), `AGENTS.md`, skills in `.opencode/skills/` | `~/.config/opencode/opencode.json`, `AGENTS.md` and `skills/` there |
| agy | `.agents/mcp_config.json`, `AGENTS.md`, skills in `.agents/skills/` | `~/.gemini/config/mcp_config.json`, block in `~/.gemini/GEMINI.md`, skills in `~/.gemini/config/skills/` |
| codex (best effort) | `AGENTS.md`, prints `codex mcp add shoav --url <url>`, skills in `.agents/skills/` | writes `~/.codex/config.toml` only if it does not exist (else prints the block), `~/.codex/AGENTS.md`, skills in `~/.codex/skills/` |
| cursor | `.cursor/mcp.json`, `AGENTS.md`, skills in `.cursor/skills/`, rule `.cursor/rules/shoav.mdc` | `~/.cursor/mcp.json`, skills in `~/.cursor/skills/` |
| generic | `AGENTS.md`, printed JSON snippet, skills in `skills/` | printed snippet, skills in `~/.shoav/skills/` |

"skills in `<dir>`" means two folders inside it:

| Installed folder | Source | Copied files | Installed by |
|---|---|---|---|
| `shoav-guide/` | `skills/guide/` | `SKILL.md`, `references/` | `--what mcp`, `skill` and `both` |
| `shoav/` | `skills/defense/` | `SKILL.md`, `scripts/` | `--what skill` and `both` |

`README.md` files are not copied. See [`../skills/README.md`](../skills/README.md).

## Where things live

`SHOAV_HOME` (default `~/.shoav`) holds `venv/` and `data/<port>/` with
`controller.log`, `controller.pid`, `ui.log`, `ui.pid` and the server's data.
It also holds `live-ui/`, a copy of the live view that `--ui` builds when the package
sits inside `node_modules` (npx, `npm install -g`) or is read-only, since Next.js will
not compile sources inside `node_modules`. A clone builds `server/live-ui` in place.
Chromium goes to Playwright's normal cache (`PLAYWRIGHT_BROWSERS_PATH` is honoured).

## Troubleshooting

- `Python 3.11 or newer not found`: install it, or `SHOAV_PYTHON=/path/to/python3.12 shoav start`.
- `creating the venv failed` on Debian or Ubuntu: `sudo apt install python3-venv`.
- `port 18500 is in use by something that is not a healthy SHOAV server`: use
  `shoav start --port 18600` and `shoav install --url http://127.0.0.1:18600/mcp`.
- Controller did not become healthy: the last log lines are printed; the full log is
  `~/.shoav/data/<port>/controller.log`.
- Agent does not see the tools: restart the agent after install; for Claude Code
  approve the `shoav` server from `.mcp.json` when asked; run `shoav doctor`.
- Live view link does not open: the UI is separate, start it with `shoav start --ui`.
- `live view UI build failed`: the controller and MCP still run. Build the UI from a
  clone instead: `cd server/live-ui && npm install && npm run build && npm start`.
- `skip ... not valid JSON`: your config has comments or a syntax error; add the
  printed snippet by hand.

## Tests

`npm test` (runs `node --test cli/test`). Tests use temp dirs and a fake controller;
they never write to the repo or your home.
