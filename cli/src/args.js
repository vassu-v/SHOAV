// Minimal argv parser with per-command flag specs. Unknown flags are errors.
import { CliError } from './ui.js';

export const COMMANDS = {
  install: {
    positionals: 0,
    flags: {
      what: 'string', agent: 'string', scope: 'string', dir: 'string', url: 'string',
      guard: 'string', yes: 'boolean', 'dry-run': 'boolean',
    },
  },
  start: {
    positionals: 0,
    flags: { guard: 'string', port: 'string', headless: 'boolean', ui: 'boolean', yes: 'boolean' },
  },
  stop: { positionals: 0, flags: { port: 'string' } },
  status: { positionals: 0, flags: { port: 'string', json: 'boolean' } },
  events: {
    positionals: 1,
    flags: {
      port: 'string', json: 'boolean', verdict: 'string', stage: 'string', mode: 'string',
      'after-seq': 'string', limit: 'string',
    },
  },
  open: { positionals: 1, flags: { port: 'string', 'no-browser': 'boolean' } },
  doctor: { positionals: 0, flags: { dir: 'string', port: 'string' } },
};

const ALIASES = { y: 'yes', h: 'help', v: 'version' };

export function parseArgs(argv) {
  const out = { command: null, positionals: [], flags: {}, help: false, version: false };
  let i = 0;
  if (argv[0] === 'help') {
    out.help = true;
    if (argv[1] && COMMANDS[argv[1]]) out.command = argv[1];
    return out;
  }
  if (argv.length && !argv[0].startsWith('-')) {
    if (!COMMANDS[argv[0]]) throw new CliError(`unknown command "${argv[0]}". Run shoav --help.`, 2);
    out.command = argv[0];
    i = 1;
  }
  const spec = COMMANDS[out.command || 'install'];
  for (; i < argv.length; i++) {
    const tok = argv[i];
    if (tok === '--') { out.positionals.push(...argv.slice(i + 1)); break; }
    if (!tok.startsWith('-') || tok === '-') { out.positionals.push(tok); continue; }
    let name = tok.replace(/^--?/, '');
    let value;
    const eq = name.indexOf('=');
    if (eq >= 0) { value = name.slice(eq + 1); name = name.slice(0, eq); }
    if (!tok.startsWith('--')) name = ALIASES[name] || name;
    if (name === 'help') { out.help = true; continue; }
    if (name === 'version') { out.version = true; continue; }
    const type = spec.flags[name];
    if (!type) throw new CliError(`unknown flag --${name} for "shoav ${out.command || 'install'}". Run shoav ${out.command || 'install'} --help.`, 2);
    if (type === 'boolean') {
      if (value !== undefined && !['true', 'false', '1', '0'].includes(value)) {
        throw new CliError(`--${name} does not take a value`, 2);
      }
      out.flags[name] = value === undefined ? true : value === 'true' || value === '1';
    } else {
      if (value === undefined) {
        value = argv[i + 1];
        if (value === undefined || (value.startsWith('--') && value.length > 2)) {
          throw new CliError(`--${name} needs a value`, 2);
        }
        i++;
      }
      out.flags[name] = value;
    }
  }
  if (!out.help && !out.version && out.positionals.length > spec.positionals) {
    throw new CliError(`unexpected argument "${out.positionals[spec.positionals]}"`, 2);
  }
  if (!out.command) out.command = 'install';
  return out;
}

export function parsePort(value, fallback) {
  if (value === undefined || value === null || value === true) return fallback;
  const s = String(value).trim();
  if (!/^\d{1,5}$/.test(s)) throw new CliError(`invalid --port "${value}" (expected 1-65535)`, 2);
  const n = Number(s);
  if (n < 1 || n > 65535) throw new CliError(`invalid --port "${value}" (expected 1-65535)`, 2);
  return n;
}

export function parseChoice(name, value, choices, fallback) {
  if (value === undefined) return fallback;
  const v = String(value).trim().toLowerCase();
  if (!choices.includes(v)) throw new CliError(`invalid --${name} "${value}" (expected ${choices.join('|')})`, 2);
  return v;
}

export const AGENTS = ['claude', 'opencode', 'agy', 'codex', 'cursor', 'generic'];
const AGENT_ALIASES = {
  'claude-code': 'claude', claudecode: 'claude',
  antigravity: 'agy', gemini: 'agy',
  'open-code': 'opencode',
  other: 'generic', local: 'generic',
};

export function parseAgents(value) {
  const parts = String(value).split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (!parts.length) throw new CliError('--agent needs at least one agent', 2);
  const out = [];
  for (const p of parts) {
    if (p === 'all') { for (const a of AGENTS) if (a !== 'generic' && !out.includes(a)) out.push(a); continue; }
    const a = AGENT_ALIASES[p] || p;
    if (!AGENTS.includes(a)) throw new CliError(`unknown agent "${p}" (expected ${AGENTS.join(', ')})`, 2);
    if (!out.includes(a)) out.push(a);
  }
  return out;
}
