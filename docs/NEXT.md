# Next steps

What is done, what is being verified, and what comes next. This file is the working plan for the current polish pass.
The long term roadmap is in the [README](../README.md#roadmap).

## Where things stand

| Area | State |
|---|---|
| Guard core (`guard/`) | Done. Four traps, four verdicts, measured on synthetic pages |
| MCP server (`server/`) | Working, rebranded to `shoav`, live view included |
| Installer and runner (`cli/`) | Built, 33 tests, verified on Windows. Linux not yet run |
| Defence skill (`skills/defense/`) | Audited, 13 script bugs fixed, selftest added |
| Guide skill (`skills/guide/`) | In progress. Teaches an agent, and a human, how to start and use SHOAV |
| Real agent runs (`e2e/engines/`) | In progress. `agy`, Claude Code, OpenCode, Codex driving the MCP |
| Tool coverage (`e2e/tools_smoke.py`) | In progress. Every advertised tool, good calls and bad calls |

## The polish pass, in parallel

Three independent tracks, each with its own ports and files so they can run at the same time.

1. **Engines.** Drive the MCP with real agent CLIs, not only direct HTTP calls. For each engine the installer sets
   up a fresh project folder, the engine runs a task headless, and the harness scores it from the live timeline.
   Pass means the task completed and there were zero compromise events. Each attack task is also run with the guard
   off, so the contrast is visible. OpenCode is run with a free model to show that any model can drive it.
   Results: [`integration/ENGINES.md`](integration/ENGINES.md).
2. **Guide skill.** A skill that removes the guesswork: what SHOAV is, how to start it, the standard loop, the real tool
   list, and recipes for everyday tasks such as finding the install command for a package on a docs page. The
   installer puts it next to the defence skill for every agent.
3. **Tool coverage.** Call every tool the MCP advertises with valid and invalid input, over REST and over real MCP
   JSON-RPC. A failing call must fail cleanly: `isError` set, a message that says what to do next, no traceback, no
   internal paths. Results: [`integration/TOOLS.md`](integration/TOOLS.md).

## Gates before the pull request

- Guard tests, controller tests, CLI tests and the skill selftest all pass.
- The direct matrix stays at enforce 27/27, observe 17/17, off 22/22.
- Each engine run is recorded with its real outcome. Runs that could not be made are listed with the reason, not hidden.
- Docs match the code: every command in the README and `AGENTS.md` was run.
- No secrets, no local data, no machine paths in the diff.

## After the pull request merges

- Check `npx github:vassu-v/SHOAV` and `npm install -g github:vassu-v/SHOAV` from a clean folder. They cannot be tested until the code is on GitHub.
- Run the installer and `shoav start` on Linux and macOS. Chromium on Linux needs system libraries, so this is a real test, not a formality.
- Verify the OpenCode, Codex and Cursor config shapes against each tool's own listing command.
- Add a root LICENSE (MIT, with the upstream Auto Browser credit).
- Prune `server/` of upstream folders we do not use (examples, benchmarks, ops), with the test suite as the safety net.

## Product roadmap

Live DOM mutation feed, iframe and Shadow DOM hit testing, threshold tuning on real traffic, ESCALATE for legitimate
modals, more measured clients, npm publish. Details in the README.
