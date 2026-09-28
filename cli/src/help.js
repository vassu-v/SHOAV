export const HELP = {
  main: `shoav: AI Bodyguard for agents that browse

Usage: shoav [command] [flags]

Commands:
  install            guided install of the MCP config and/or agent skills (default)
  start              start the guarded browser server in the background
  stop               stop what shoav start launched
  status             show server health, guard mode, verdict counters, sessions
  events <sid>       print the guard timeline of a session
  open [sid]         print and open the live view link
  doctor             check node, python, venv, chromium, port and configs

Global flags:
  -h, --help         help (also: shoav <command> --help)
  -v, --version      print the version

Examples:
  shoav install --agent claude,opencode --yes
  shoav start --guard enforce
  shoav status
`,
  install: `Usage: shoav [install] [flags]

Writes MCP client config and/or the SHOAV agent skills for your agents:
shoav-guide (how to drive the MCP) and shoav (the defence skill).
Existing JSON files are merged (other keys kept); invalid JSON is never touched.
Running it twice changes nothing. Nothing is ever deleted.

Flags:
  --what skill|mcp|both     skill: both skills; mcp: MCP config + guide skill;
                            both: everything (default, recommended)
  --agent <list>            comma list of: claude, opencode, agy, codex, cursor, generic
                            (prompted when omitted in a terminal)
  --scope project|user      project writes under --dir, user under your home (default project)
  --dir <path>              project root (default current directory)
  --url <mcp url>           MCP endpoint (default http://127.0.0.1:18500/mcp)
  --guard off|observe|enforce
                            guard mode noted in AGENTS.md (default enforce)
  -y, --yes                 no prompts
  --dry-run                 print exactly what would be written, write nothing

Exit codes: 0 ok, 2 bad usage, 3 some file was invalid and must be edited by hand.
`,
  start: `Usage: shoav start [flags]

Starts the controller detached, waits for /healthz and prints the MCP url.
First run creates a venv in $SHOAV_HOME/venv (default ~/.shoav/venv), installs
the Python requirements and asks to download Chromium.

Flags:
  --guard off|observe|enforce   guard mode (default enforce)
  --port <n>                    controller port (default 18500)
  --headless                    run Chromium without a window
  --ui                          also build and serve the live view UI on port 3200
  -y, --yes                     do not ask before downloading Chromium
`,
  stop: `Usage: shoav stop [--port <n>]

Stops the controller (and the live view UI) that shoav start launched on that port.
`,
  status: `Usage: shoav status [--port <n>] [--json]

Shows health, guard mode, verdict counters (allow, rewrite, block, escalate) and
the session count. Exit code 1 when the server is down.
`,
  events: `Usage: shoav events <session id> [flags]

Prints the guard verdicts from a session timeline. <session id> may also be a
live view link (http://127.0.0.1:3200/s/<id>) or a pasted create_session JSON result.

Flags:
  --port <n>          controller port (default 18500)
  --verdict <v>       ALLOW, REWRITE, BLOCK or ESCALATE
  --stage <s>         ingress or egress
  --mode <m>          observe or enforce
  --after-seq <n>     only events after this sequence number (default 0)
  --limit <n>         page size (default 100)
  --json              raw JSON
`,
  open: `Usage: shoav open [session id] [--port <n>] [--no-browser]

Prints the live view link (latest session when no id is given) and opens it.
`,
  doctor: `Usage: shoav doctor [--dir <path>] [--port <n>]

Checks node, python >= 3.11, the venv, Chromium, the port and configs in --dir.
Exit code 1 when a check fails.
`,
};
