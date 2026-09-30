# Integration plan and report (historical)

These two files record how the guard was wired into the browser MCP server, and what was measured afterwards. They are kept
as a record. Paths inside them use the layout from before the restructure (`shoav-mcp/...`), see the map below.

| File | What it is |
|---|---|
| [`plan.md`](plan.md) | The wiring plan: where the guard hooks into the tool gateway and the test matrix |
| [`REPORT.md`](REPORT.md) | The measured result (2026-09-26): enforce 27/27, observe 17/17, off 22/22 checks on synthetic pages, plus the real `agy` run |

The current docs are the root [`README.md`](../../README.md) and [`AGENTS.md`](../../AGENTS.md). For how to start the server see
[`server/SHOAV.md`](../../server/SHOAV.md).

Old path to current path:

| Old | Current |
|---|---|
| `shoav-mcp/MCP/auto-browser` | `server/` |
| `shoav-mcp/filters` | `guard/filters/` |
| `shoav-mcp/connectors` | `guard/connectors/` |
| `shoav-mcp/t5_e2e` | `e2e/` |
| `shoav-mcp/fixtures` | `e2e/fixtures/` |
| `shoav-mcp/MCP/agent-template` | removed, replaced by `AGENTS.md` and `e2e/ACCEPTANCE.md` |
| `shoav-mcp/MCP/mcp-test` | `e2e/claude-harness/` |
| `shoav-skill/skill` | `skills/defense/` (was `skill/` until the skills split) |

The MCP server key was `auto-browser` at the time and is now `shoav`. Tool names are unchanged (`browser_*`).
