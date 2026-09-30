import fs from 'node:fs';
import path from 'node:path';
import { parsePort } from './args.js';
import { START } from './agents-block.js';
import { isHealthy, portInUse } from './http.js';
import { DEFAULT_PORT, controllerUrl, venvDir } from './paths.js';
import { chromiumStatus, findPython, MIN_PY, venvExists } from './python.js';
import { c, log, printBanner } from './ui.js';

const CONFIGS = [
  ['.mcp.json', (j) => j?.mcpServers?.shoav, 'Claude Code'],
  ['opencode.json', (j) => j?.mcp?.shoav, 'OpenCode'],
  [path.join('.agents', 'mcp_config.json'), (j) => j?.mcpServers?.shoav, 'Antigravity'],
  [path.join('.cursor', 'mcp.json'), (j) => j?.mcpServers?.shoav, 'Cursor'],
];

export async function runDoctor(parsed, { env = process.env, cwd = process.cwd() } = {}) {
  printBanner();
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  const dir = path.resolve(cwd, parsed.flags.dir ?? '.');
  let failures = 0;
  const pass = (m) => log.ok(m);
  const fail = (m, hint) => { failures++; log.fail(`${m}${hint ? `\n       fix: ${hint}` : ''}`); };
  const warn = (m, hint) => log.warn(`${m}${hint ? `\n       hint: ${hint}` : ''}`);

  const [maj] = process.versions.node.split('.').map(Number);
  if (maj >= 18) pass(`node ${process.versions.node}`);
  else fail(`node ${process.versions.node} is too old`, 'install Node.js 18 or newer');

  const py = findPython(env);
  if (py.error) fail(`${py.error}${py.seen.length ? ` (found ${py.seen.join(', ')})` : ''}`, `install Python ${MIN_PY.join('.')}+ or set SHOAV_PYTHON`);
  else pass(`python ${py.version} (${[py.cmd, ...py.args].join(' ')})`);

  if (venvExists(env)) {
    pass(`venv at ${venvDir(env)}`);
    const ch = chromiumStatus(env);
    if (ch.ok) pass(`chromium ${ch.path}`);
    else fail(`chromium not ready: ${ch.reason}`, 'run shoav start --yes (downloads it)');
  } else {
    fail(`venv missing at ${venvDir(env)}`, 'run shoav start (creates it on first run)');
  }

  const base = controllerUrl(port);
  if (await isHealthy(base)) pass(`port ${port}: SHOAV is running (${base}/mcp)`);
  else if (await portInUse(port)) fail(`port ${port} is used by something that is not SHOAV`, `stop that program or use shoav start --port <other> and install --url http://127.0.0.1:<other>/mcp`);
  else pass(`port ${port} is free (server not running; shoav start)`);

  const found = [];
  for (const [rel, pick, label] of CONFIGS) {
    const file = path.join(dir, rel);
    if (!fs.existsSync(file)) continue;
    try {
      const raw = fs.readFileSync(file, 'utf8').replace(/^﻿/, '');
      if (pick(JSON.parse(raw))) found.push(`${label} (${rel})`);
      else warn(`${rel} exists but has no shoav server`, `shoav install --agent ... --dir ${dir}`);
    } catch {
      warn(`${rel} is not valid JSON`, 'fix it by hand; shoav install will not edit it');
    }
  }
  const agentsMd = path.join(dir, 'AGENTS.md');
  if (fs.existsSync(agentsMd) && fs.readFileSync(agentsMd, 'utf8').includes(START)) found.push('AGENTS.md block');
  if (found.length) pass(`configs in ${dir}: ${found.join(', ')}`);
  else warn(`no SHOAV configs found in ${dir}`, 'run shoav install --agent <name> (or pass --dir)');

  log.info();
  log.info(failures ? c.red(`${failures} check(s) failed.`) : c.green('All checks passed.'));
  return failures ? 1 : 0;
}
