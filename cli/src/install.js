import fs from 'node:fs';
import path from 'node:path';
import { AGENTS, parseAgents, parseChoice } from './args.js';
import { applyPlan } from './fsplan.js';
import { DEFAULT_MCP_URL, userHome } from './paths.js';
import { choose, chooseMany, confirm } from './prompt.js';
import { AGENT_LABELS, planInstall } from './targets.js';
import { c, CliError, log, printBanner } from './ui.js';
import { validateMcpUrl } from './validate.js';

export function resolveInstallOptions(flags, env = process.env, cwd = process.cwd()) {
  const dir = path.resolve(cwd, flags.dir ?? '.');
  if (fs.existsSync(dir) && !fs.statSync(dir).isDirectory()) throw new CliError(`--dir ${dir} is not a directory`, 2);
  return {
    what: parseChoice('what', flags.what, ['skill', 'mcp', 'both'], undefined),
    agents: flags.agent !== undefined ? parseAgents(flags.agent) : undefined,
    scope: parseChoice('scope', flags.scope, ['project', 'user'], 'project'),
    dir,
    url: validateMcpUrl(flags.url ?? DEFAULT_MCP_URL),
    guard: parseChoice('guard', flags.guard, ['off', 'observe', 'enforce'], 'enforce'),
    yes: Boolean(flags.yes),
    dryRun: Boolean(flags['dry-run']),
    env,
  };
}

export function displayPath(p, opts) {
  const rel = path.relative(opts.dir, p);
  if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) return rel.split(path.sep).join('/');
  const home = userHome(opts.env);
  const hrel = path.relative(home, p);
  if (hrel && !hrel.startsWith('..') && !path.isAbsolute(hrel)) return `~/${hrel.split(path.sep).join('/')}`;
  return p;
}

function indent(text, pad = '      ') {
  return text.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n').map((l) => pad + l).join('\n');
}

export function reportPlan(plan, opts, write = (s) => process.stdout.write(s)) {
  const dry = opts.dryRun;
  let unchanged = 0;
  let changed = 0;
  let manual = 0;
  for (const a of plan.actions) {
    const shown = displayPath(a.path, opts);
    if (a.kind === 'manual') {
      manual++;
      write(`${c.yellow('skip')}      ${shown}  ${c.dim(`(${a.reason})`)}\n`);
      write(`          Add this yourself (merge into the existing content):\n${indent(JSON.stringify(a.patch, null, 2), '          ')}\n`);
      continue;
    }
    if (a.status === 'unchanged') { unchanged++; continue; }
    changed++;
    const verb = dry ? `would ${a.status}` : a.status === 'create' ? 'created' : 'updated';
    write(`${c.green(verb.padEnd(12))} ${shown}  ${c.dim(a.note || '')}\n`);
    if (dry) {
      if (a.kind === 'copy') write(c.dim(`      copy of ${a.src}\n`));
      else write(`${c.dim(indent(a.content))}\n`);
    }
  }
  if (unchanged) write(c.dim(`${unchanged} file(s) already up to date, not touched.\n`));
  if (!changed && !manual && !unchanged) write(c.dim('Nothing to write for this selection.\n'));
  return { changed, unchanged, manual };
}

export async function runInstall(parsed, { env = process.env, isTTY = Boolean(process.stdin.isTTY && process.stdout.isTTY) } = {}) {
  const opts = resolveInstallOptions(parsed.flags, env);
  printBanner();
  const interactive = isTTY && !opts.yes;

  if (!opts.what) {
    opts.what = interactive
      ? await choose('What should be installed?', [
        { value: 'both', label: 'MCP server config + both skills (guide and defence) (Recommended)' },
        { value: 'mcp', label: 'MCP server config + guide skill' },
        { value: 'skill', label: 'Skills only (guide and defence), no MCP config' },
      ], 0)
      : 'both';
  }
  if (!opts.agents) {
    if (!interactive) {
      throw new CliError(`no agent chosen. Pass --agent with one or more of: ${AGENTS.join(',')} (for example --agent claude,opencode).`, 2);
    }
    opts.agents = await chooseMany('Which agents do you use?', AGENTS.map((a) => ({ value: a, label: a === 'codex' ? 'Codex CLI (best effort)' : AGENT_LABELS[a] })));
  }

  log.info(`${c.bold('Install')}: ${({ both: 'MCP config + guide and defence skills', mcp: 'MCP config + guide skill', skill: 'guide and defence skills' })[opts.what]}  ${c.bold('agents')}: ${opts.agents.join(', ')}  ${c.bold('scope')}: ${opts.scope}`);
  log.info(`${c.bold('Target')}: ${opts.scope === 'project' ? opts.dir : userHome(env)}  ${c.bold('MCP url')}: ${opts.url}  ${c.bold('guard')}: ${opts.guard}`);
  if (opts.dryRun) log.info(c.yellow('Dry run: nothing will be written.'));
  log.info();

  const plan = planInstall(opts);
  const pending = plan.actions.filter((a) => a.status === 'create' || a.status === 'update');

  if (!opts.dryRun && interactive && pending.length) {
    reportPlan(plan, { ...opts, dryRun: true });
    log.info();
    if (!(await confirm(`Write ${pending.length} file(s)?`, true))) {
      log.info('Nothing written.');
      return 1;
    }
  }
  if (!opts.dryRun) applyPlan(plan.actions);
  const summary = reportPlan(plan, opts);

  if (plan.notes.length) {
    log.info();
    for (const n of plan.notes) log.info(`${c.cyan('note')} ${n}`);
  }

  log.info();
  log.info(c.bold('Next steps'));
  if (opts.what !== 'skill') {
    log.info(`  1. shoav start            start the guarded browser server (guard ${opts.guard}): shoav start --guard ${opts.guard}`);
    log.info('  2. shoav status           check it is up and see guard counters');
    log.info('  3. shoav open             open the live view to watch the agent browse');
    log.info('  Restart your agent so it picks up the new MCP config.');
  } else {
    log.info('  Restart your agent so it loads the skills.');
  }
  return summary.manual ? 3 : 0;
}
