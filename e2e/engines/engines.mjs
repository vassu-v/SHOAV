// How each agent CLI is driven headless. Flags come from each CLI's own --help
// (claude 2.1.282, agy 1.2.11, opencode 1.18.32, codex-cli 0.144.1).
import fs from 'node:fs';
import path from 'node:path';

export const ENGINES = ['claude', 'agy', 'opencode', 'codex'];
export const ENGINE_INDEX = { claude: 0, agy: 1, opencode: 2, codex: 3 };

export const DEFAULT_MODELS = {
  claude: 'sonnet',
  agy: null, // agy default model
  opencode: 'opencode/nemotron-3.5-lightning-free',
  codex: null, // codex default model
};

// Controller port per engine and guard mode, inside 18570-18579 only.
export function controllerPort(engine, guard) {
  const i = ENGINE_INDEX[engine];
  if (guard === 'enforce') return 18570 + i * 2;
  if (guard === 'off') return 18571 + i * 2;
  if (guard === 'observe') {
    if (i > 1) throw new Error('observe runs are only mapped for claude (18578) and agy (18579)');
    return 18578 + i;
  }
  throw new Error(`bad guard ${guard}`);
}

export function fixturePort(engine) {
  return 18660 + ENGINE_INDEX[engine];
}

const SYSTEM_HINT = 'Use only the shoav MCP browser tools for web pages.';

// Returns { args, outFile?, parse(stdout, stderr, outFileText) -> finalText }.
export function engineCommand(engine, { prompt, model, proj, mcpUrl, maxTurns = 30 }) {
  switch (engine) {
    case 'claude': {
      // No --mcp-config: the MCP must come from the installer's .mcp.json and
      // .claude/settings.json (enabledMcpjsonServers, allow mcp__shoav).
      const args = ['-p', prompt,
        '--output-format', 'json',
        '--max-turns', String(maxTurns),
        '--max-budget-usd', '1.50',
        '--allowedTools', 'mcp__shoav',
        '--disallowedTools', 'WebFetch', 'WebSearch', 'Bash', 'PowerShell',
        '--append-system-prompt', SYSTEM_HINT,
        '--no-session-persistence'];
      if (model) args.push('--model', model);
      return {
        args,
        parse(stdout) {
          try {
            const j = JSON.parse(stdout.trim().split(/\r?\n/).filter(Boolean).pop());
            return { text: String(j.result ?? ''), meta: { is_error: j.is_error, num_turns: j.num_turns, cost_usd: j.total_cost_usd, models: Object.keys(j.modelUsage || {}), denials: j.permission_denials, subtype: j.subtype, terminal_reason: j.terminal_reason } };
          } catch {
            return { text: stdout, meta: { parse: 'failed' } };
          }
        },
      };
    }
    case 'agy': {
      const args = ['-p', prompt, '--dangerously-skip-permissions', '--output-format', 'text', '--disable-slash-commands'];
      if (model) args.push('--model', model);
      return { args, parse: (stdout) => ({ text: stdout, meta: {} }) };
    }
    case 'opencode': {
      const args = ['run', '--format', 'json', '--dir', proj];
      if (model) args.push('-m', model);
      args.push(prompt);
      return {
        args,
        parse(stdout) {
          const texts = [];
          const tools = [];
          let errors = [];
          for (const line of stdout.split(/\r?\n/)) {
            if (!line.trim().startsWith('{')) continue;
            let e;
            try { e = JSON.parse(line); } catch { continue; }
            const part = e.part || {};
            if (e.type === 'text' && typeof part.text === 'string') texts.push(part.text);
            if (e.type === 'tool_use' || part.type === 'tool') tools.push(part.tool || e.tool || '?');
            if (e.type === 'error') errors.push(JSON.stringify(e.error || e).slice(0, 300));
          }
          return { text: texts.join('\n'), meta: { tools, errors } };
        },
      };
    }
    case 'codex': {
      const outFile = path.join(proj, '.codex-last-message.txt');
      // The installer does not register codex MCP at project scope (it prints a
      // `codex mcp add` command that edits ~/.codex). The harness never edits
      // global config, so it passes the server as a per-run -c override.
      const args = ['exec', '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never',
        '-c', `mcp_servers.shoav.url="${mcpUrl}"`,
        '-o', outFile];
      if (model) args.push('-m', model);
      args.push(prompt);
      return {
        args,
        outFile,
        parse(stdout, stderr) {
          let text = '';
          try { text = fs.readFileSync(outFile, 'utf8'); } catch { text = stdout; }
          return { text, meta: { stderr_tail: stderr.slice(-800) } };
        },
      };
    }
    default:
      throw new Error(`unknown engine ${engine}`);
  }
}

// The engine's own MCP listing command, run in the project dir after install.
export function listCommand(engine, mcpUrl) {
  switch (engine) {
    case 'claude': return [['mcp', 'list']];
    case 'agy': return [['mcp', 'list']];
    case 'opencode': return [['mcp', 'list']];
    case 'codex': return [['mcp', 'list'], ['-c', `mcp_servers.shoav.url="${mcpUrl}"`, 'mcp', 'list']];
    default: return [];
  }
}
