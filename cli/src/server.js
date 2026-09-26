// start, stop, status, events, open.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { parseChoice, parsePort } from './args.js';
import { fetchTimeline, filterGuardEvents, formatEventsTable, parseSidArg } from './events.js';
import { listFiles } from './fsplan.js';
import { getJson, isHealthy, portInUse } from './http.js';
import {
  CONTROLLER_DIR, DEFAULT_PORT, GUARD_DIR, LIVE_UI_DIR, UI_BASE, UI_PORT,
  controllerUrl, dataDir, liveViewUrl, shoavHome, venvPython,
} from './paths.js';
import { isAlive, killTree, processName, readPid } from './proc.js';
import { confirm } from './prompt.js';
import {
  chromiumStatus, createVenv, findPython, installChromium, installRequirements, requirementsCurrent, venvExists,
} from './python.js';
import { c, CliError, log, printBanner } from './ui.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isWin = process.platform === 'win32';

export function controllerEnv({ port, guard, headless, env = process.env }) {
  const d = dataDir(port, env);
  const j = (...p) => path.join(d, ...p);
  return {
    ARTIFACT_ROOT: j('artifacts'), UPLOAD_ROOT: j('uploads'), AUTH_ROOT: j('auth'),
    APPROVAL_ROOT: j('approvals'), AUDIT_ROOT: j('audit'), WITNESS_ROOT: j('witness'),
    SESSION_STORE_ROOT: j('sessions'), JOB_STORE_ROOT: j('jobs'), HARNESS_ROOT: j('harness'),
    MEMORY_ROOT: j('memory'), STATE_DB_PATH: j('state.db'),
    MCP_SESSION_STORE_PATH: j('mcp', 'sessions.json'), CRON_STORE_PATH: j('crons.json'),
    // A file that never exists, so the controller launches Chromium itself.
    BROWSER_WS_ENDPOINT_FILE: j('no-browser-node.txt'),
    API_BIND_SCOPE: 'loopback', OCR_ENABLED: 'false', ALLOWED_HOSTS: '*',
    HEADLESS: headless ? 'true' : 'false',
    LIVE_UI_BASE_URL: UI_BASE,
    LIVE_UI_ORIGINS: `${UI_BASE},http://localhost:${UI_PORT}`,
    SHOAV_GUARD_MODE: guard,
    SHOAV_FILTERS_PATH: GUARD_DIR,
    // agy rejects dots in tool names; calls accept either spelling.
    MCP_TOOL_NAME_STYLE: 'underscore',
    PYTHONUNBUFFERED: '1',
  };
}

function tail(file, n = 25) {
  try {
    return fs.readFileSync(file, 'utf8').split(/\r?\n/).slice(-n).join('\n');
  } catch {
    return '(no log)';
  }
}

function pidFiles(port, env) {
  const d = dataDir(port, env);
  return { dir: d, controller: path.join(d, 'controller.pid'), ui: path.join(d, 'ui.pid'), log: path.join(d, 'controller.log'), uiLog: path.join(d, 'ui.log') };
}

async function ensureRuntime({ yes, env }) {
  const interactive = Boolean(process.stdin.isTTY && process.stdout.isTTY);
  if (!venvExists(env)) {
    const py = findPython(env);
    if (py.error) {
      throw new CliError(`${py.error}${py.seen.length ? ` (found: ${py.seen.join(', ')})` : ''}. Install Python 3.11+ from https://www.python.org/downloads/ or set SHOAV_PYTHON to its path, then retry.`);
    }
    log.step(`Creating Python venv with ${[py.cmd, ...py.args].join(' ')} (${py.version}) at ${path.dirname(venvPython(env))}`);
    if (!createVenv(py, env)) throw new CliError('creating the venv failed (on Debian/Ubuntu: sudo apt install python3-venv)');
  }
  if (!requirementsCurrent(env)) {
    log.step('Installing controller requirements into the venv (first run can take a few minutes)');
    if (!installRequirements(env)) throw new CliError('pip install failed; see the output above');
  }
  const chrome = chromiumStatus(env);
  if (!chrome.ok) {
    log.step(`Chromium for Playwright is missing (${chrome.reason}).`);
    let go = yes;
    if (!go) {
      if (!interactive) throw new CliError('Chromium is not installed. Re-run with --yes to download it (about 150 MB).');
      go = await confirm('Download Chromium now (about 150 MB)?', true);
    }
    if (!go) throw new CliError('Chromium is required. Run shoav start --yes to download it.');
    if (!installChromium(env)) throw new CliError('playwright install chromium failed; see the output above');
  }
}

export async function runStart(parsed, { env = process.env } = {}) {
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  const guard = parseChoice('guard', parsed.flags.guard, ['off', 'observe', 'enforce'], 'enforce');
  const headless = Boolean(parsed.flags.headless);
  const yes = Boolean(parsed.flags.yes);
  printBanner();
  const base = controllerUrl(port);
  const files = pidFiles(port, env);

  let shownGuard = guard;
  if (await isHealthy(base)) {
    log.ok(`SHOAV is already running on port ${port}.`);
    try {
      const g = await getJson(`${base}/live-api/guard`);
      if (g.mode) shownGuard = g.mode;
      if (parsed.flags.guard && g.mode && g.mode !== guard) {
        log.warn(`it runs with guard ${g.mode}; to change it: shoav stop${port === DEFAULT_PORT ? '' : ` --port ${port}`} then shoav start --guard ${guard}`);
      }
    } catch { /* keep the requested mode */ }
  } else {
    if (await portInUse(port)) {
      throw new CliError(`port ${port} is in use by something that is not a healthy SHOAV server. Pick another with --port.`);
    }
    if (!fs.existsSync(path.join(CONTROLLER_DIR, 'app', 'main.py'))) {
      throw new CliError(`server code not found at ${CONTROLLER_DIR}`);
    }
    await ensureRuntime({ yes, env });
    fs.mkdirSync(files.dir, { recursive: true });
    fs.mkdirSync(path.join(files.dir, 'mcp'), { recursive: true });
    const childEnv = { ...env, ...controllerEnv({ port, guard, headless, env }) };
    const fd = fs.openSync(files.log, 'a');
    log.step(`Starting controller on port ${port} (guard ${guard}${headless ? ', headless' : ''})`);
    const child = spawn(venvPython(env), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)], {
      cwd: CONTROLLER_DIR, env: childEnv, detached: true, stdio: ['ignore', fd, fd], windowsHide: true,
    });
    let exited = null;
    child.on('exit', (code) => { exited = code ?? -1; });
    child.on('error', (err) => { exited = err.message; });
    child.unref();
    fs.closeSync(fd);
    fs.writeFileSync(files.controller, `${child.pid}\n`);
    const deadline = Date.now() + 120000;
    let up = false;
    while (Date.now() < deadline) {
      if (await isHealthy(base)) { up = true; break; }
      if (exited !== null) break;
      await sleep(500);
    }
    if (!up) {
      if (exited === null && child.pid) await killTree(child.pid);
      throw new CliError(`controller did not become healthy (${exited !== null ? `exited: ${exited}` : 'timed out after 120 s'}). Last log lines from ${files.log}:\n${tail(files.log)}`);
    }
    log.ok(`controller up (pid ${child.pid}, log ${files.log})`);
  }

  let uiUp = await portInUse(UI_PORT);
  if (parsed.flags.ui) uiUp = await startUi({ port, env, files });

  log.info();
  log.info(`${c.bold('MCP url')}    ${base}/mcp`);
  log.info(`${c.bold('Live view')}  ${UI_BASE}/s/<session id>${uiUp ? '' : c.dim('  (UI not running; add --ui to serve it)')}`);
  log.info(`${c.bold('Guard')}      ${shownGuard}`);
  log.info();
  log.info(`${c.bold('Next')}: point your agent at the MCP url (shoav install), then ask it to browse.`);
  log.info('      shoav status to check, shoav open <session id> to watch, shoav stop to stop.');
  return 0;
}

// ---- live view UI ---------------------------------------------------------

const UI_SOURCES = ['app', 'components', 'hooks', 'lib', 'public'];
const UI_ROOT_FILES = ['package.json', 'package-lock.json', 'next.config.ts', 'tsconfig.json', 'postcss.config.mjs', 'components.json'];

function newestSourceMtime(dir) {
  let newest = 0;
  for (const sub of UI_SOURCES) {
    const p = path.join(dir, sub);
    if (!fs.existsSync(p)) continue;
    for (const f of listFiles(p)) newest = Math.max(newest, fs.statSync(path.join(p, f)).mtimeMs);
  }
  for (const f of UI_ROOT_FILES) {
    const p = path.join(dir, f);
    if (fs.existsSync(p)) newest = Math.max(newest, fs.statSync(p).mtimeMs);
  }
  return newest;
}

export function uiBuildNeeded(dir, controller) {
  const buildId = path.join(dir, '.next', 'BUILD_ID');
  const stamp = path.join(dir, '.next', 'shoav-controller-url');
  if (!fs.existsSync(buildId)) return true;
  let stamped = null;
  try { stamped = fs.readFileSync(stamp, 'utf8'); } catch { /* none */ }
  if (stamped !== null && stamped !== controller) return true;
  if (stamped === null && controller !== controllerUrl(DEFAULT_PORT)) return true;
  return fs.statSync(buildId).mtimeMs < newestSourceMtime(dir);
}

function writable(dir) {
  try {
    fs.accessSync(dir, fs.constants.W_OK);
    const probe = path.join(dir, `.shoav-write-probe-${process.pid}`);
    fs.writeFileSync(probe, '');
    fs.unlinkSync(probe);
    return true;
  } catch {
    return false;
  }
}

function copyUiSources(src, dest) {
  for (const f of listFiles(src)) {
    const top = f.split(path.sep)[0];
    if (top === '.next' || top === 'node_modules' || top === 'qa') continue;
    const to = path.join(dest, f);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    const a = fs.readFileSync(path.join(src, f));
    let b = null;
    try { b = fs.readFileSync(to); } catch { /* new */ }
    if (!b || Buffer.compare(a, b) !== 0) fs.writeFileSync(to, a);
  }
}

function npm(args, opts) {
  // npm is a .cmd on Windows, which needs a shell. Arguments are fixed strings.
  return spawnSync(isWin ? 'npm.cmd' : 'npm', args, { stdio: 'inherit', shell: isWin, windowsHide: true, ...opts });
}

async function startUi({ port, env, files }) {
  const existing = readPid(files.ui);
  if (existing && isAlive(existing) && (await portInUse(UI_PORT))) {
    log.ok(`live view UI already running (pid ${existing})`);
    return true;
  }
  if (await portInUse(UI_PORT)) {
    log.warn(`port ${UI_PORT} is busy with something shoav did not start; not starting the UI.`);
    return true;
  }
  if (npm(['--version'], { stdio: 'ignore' }).status !== 0) {
    log.warn('npm not found; skipping the live view UI. Install Node.js with npm to use --ui.');
    return false;
  }
  let dir = LIVE_UI_DIR;
  if (!writable(dir)) {
    dir = path.join(shoavHome(env), 'live-ui');
    log.step(`Copying the live view UI to ${dir} (package dir is read-only)`);
    copyUiSources(LIVE_UI_DIR, dir);
  }
  const controller = controllerUrl(port);
  const buildEnv = { ...env, NEXT_PUBLIC_CONTROLLER_URL: controller };
  if (!fs.existsSync(path.join(dir, 'node_modules', 'next'))) {
    log.step('Installing live view UI dependencies (npm install)');
    if (npm(['install', '--no-audit', '--no-fund'], { cwd: dir, env: buildEnv }).status !== 0) {
      log.warn('npm install failed; continuing without the UI.');
      return false;
    }
  }
  if (uiBuildNeeded(dir, controller)) {
    log.step('Building the live view UI (npm run build)');
    if (npm(['run', 'build'], { cwd: dir, env: buildEnv }).status !== 0) {
      log.warn('UI build failed; continuing without the UI.');
      return false;
    }
    fs.writeFileSync(path.join(dir, '.next', 'shoav-controller-url'), controller);
  } else {
    log.ok('live view UI build is up to date');
  }
  const fd = fs.openSync(files.uiLog, 'a');
  const child = spawn(process.execPath, ['scripts/start.mjs'], {
    cwd: dir, env: { ...buildEnv, PORT: String(UI_PORT) }, detached: true, stdio: ['ignore', fd, fd], windowsHide: true,
  });
  child.unref();
  fs.closeSync(fd);
  fs.writeFileSync(files.ui, `${child.pid}\n`);
  for (let i = 0; i < 60; i++) {
    if (await portInUse(UI_PORT)) { log.ok(`live view UI up at ${UI_BASE} (pid ${child.pid})`); return true; }
    await sleep(500);
  }
  log.warn(`live view UI did not open port ${UI_PORT} in 30 s; see ${files.uiLog}`);
  return false;
}

// ---- stop -----------------------------------------------------------------

async function stopOne(file, label, expect) {
  const pid = readPid(file);
  if (!pid) return false;
  const name = processName(pid);
  if (!name) {
    log.info(c.dim(`${label}: pid ${pid} is not running (stale pid file removed)`));
    try { fs.unlinkSync(file); } catch { /* ignore */ }
    return false;
  }
  if (!expect.some((e) => name.includes(e))) {
    log.warn(`${label}: pid ${pid} is now "${name}", not ours; not killing it. Removed the stale pid file.`);
    try { fs.unlinkSync(file); } catch { /* ignore */ }
    return false;
  }
  const ok = await killTree(pid);
  if (ok) {
    try { fs.unlinkSync(file); } catch { /* ignore */ }
    log.ok(`stopped ${label} (pid ${pid})`);
  } else {
    log.fail(`could not stop ${label} (pid ${pid})`);
  }
  return ok;
}

export async function runStop(parsed, { env = process.env } = {}) {
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  const files = pidFiles(port, env);
  const a = await stopOne(files.controller, 'controller', ['python']);
  const b = await stopOne(files.ui, 'live view UI', ['node']);
  if (!a && !b) {
    if (await isHealthy(controllerUrl(port))) {
      log.warn(`A SHOAV server answers on port ${port} but shoav start did not launch it (no pid file under ${files.dir}). Stop it where you started it.`);
      return 1;
    }
    log.info(`Nothing to stop on port ${port}.`);
    return 0;
  }
  for (let i = 0; i < 20 && (await portInUse(port)); i++) await sleep(250);
  if (await portInUse(port)) {
    log.warn(`port ${port} is still in use.`);
    return 1;
  }
  log.ok(`port ${port} is free`);
  return 0;
}

// ---- status / events / open ----------------------------------------------

function downMessage(port) {
  return `SHOAV is not running on port ${port}. Start it with: shoav start${port === DEFAULT_PORT ? '' : ` --port ${port}`}`;
}

export const COUNTER_KEYS = ['allow', 'rewrite', 'block', 'escalate'];

export async function runStatus(parsed) {
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  const base = controllerUrl(port);
  if (!(await isHealthy(base))) {
    if (parsed.flags.json) process.stdout.write(`${JSON.stringify({ up: false, port }, null, 2)}\n`);
    else log.info(downMessage(port));
    return 1;
  }
  let guard = {};
  let sessions = [];
  const errors = [];
  try { guard = await getJson(`${base}/live-api/guard`); } catch (err) { errors.push(`guard: ${err.message}`); }
  try {
    const s = await getJson(`${base}/live-api/sessions`);
    sessions = Array.isArray(s.sessions) ? s.sessions : [];
  } catch (err) { errors.push(`sessions: ${err.message}`); }
  const uiUp = await portInUse(UI_PORT);
  if (parsed.flags.json) {
    process.stdout.write(`${JSON.stringify({ up: true, port, mcp_url: `${base}/mcp`, guard, sessions: sessions.length, live_view_ui: uiUp, errors }, null, 2)}\n`);
    return 0;
  }
  const counters = guard.counters && typeof guard.counters === 'object' ? guard.counters : {};
  log.info(`${c.green('up')}  SHOAV on port ${port}`);
  log.info(`  MCP url      ${base}/mcp`);
  log.info(`  guard mode   ${guard.mode ?? 'unknown'}${guard.version ? c.dim(` (version ${guard.version})`) : ''}`);
  log.info(`  verdicts     ${COUNTER_KEYS.map((k) => `${k} ${counters[k] ?? 0}`).join('  ')}`);
  log.info(`  sessions     ${sessions.length}`);
  log.info(`  live view    ${UI_BASE}${uiUp ? '' : c.dim('  (UI not running: shoav start --ui)')}`);
  for (const e of errors) log.warn(e);
  return 0;
}

export async function runEvents(parsed) {
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  const base = controllerUrl(port);
  const sid = parseSidArg(parsed.positionals[0]);
  if (!sid) throw new CliError('usage: shoav events <session id>', 2);
  const intFlag = (name, def, min) => {
    const v = parsed.flags[name];
    if (v === undefined) return def;
    if (!/^\d+$/.test(String(v)) || Number(v) < min) throw new CliError(`invalid --${name} "${v}"`, 2);
    return Number(v);
  };
  const afterSeq = intFlag('after-seq', 0, 0);
  const limit = intFlag('limit', 100, 1);
  let data;
  try {
    data = await fetchTimeline(base, sid, afterSeq, limit);
  } catch (err) {
    if (err.status === 404) throw new CliError(`session ${sid} not found on port ${port}. List sessions with shoav status.`);
    if (!(await isHealthy(base))) throw new CliError(downMessage(port));
    throw new CliError(`could not read the timeline: ${err.message}`);
  }
  const events = Array.isArray(data.events) ? data.events : [];
  const guards = filterGuardEvents(events, { verdict: parsed.flags.verdict, stage: parsed.flags.stage, mode: parsed.flags.mode });
  if (parsed.flags.json) {
    process.stdout.write(`${JSON.stringify({ session_id: sid, guard_events: guards }, null, 2)}\n`);
  } else {
    log.info(`Guard timeline for session ${sid}  ${c.dim(liveViewUrl(sid))}`);
    log.info(formatEventsTable(guards));
  }
  return 0;
}

export function openInBrowser(url) {
  if (!/^https?:\/\/[A-Za-z0-9.:[\]/_%-]+$/.test(url)) return false;
  try {
    const [cmd, args] = isWin ? ['cmd', ['/c', 'start', '""', url]]
      : process.platform === 'darwin' ? ['open', [url]] : ['xdg-open', [url]];
    const child = spawn(cmd, args, { detached: true, stdio: 'ignore', windowsHide: true, windowsVerbatimArguments: isWin });
    child.on('error', () => {});
    child.unref();
    return true;
  } catch {
    return false;
  }
}

export async function runOpen(parsed, { env = process.env } = {}) {
  const port = parsePort(parsed.flags.port, DEFAULT_PORT);
  let sid = parsed.positionals[0] ? parseSidArg(parsed.positionals[0]) : null;
  if (!sid && (await isHealthy(controllerUrl(port)))) {
    try {
      const s = await getJson(`${controllerUrl(port)}/live-api/sessions`);
      const list = Array.isArray(s.sessions) ? s.sessions : [];
      const last = list[list.length - 1];
      if (last) sid = last.id || last.session_id || null;
    } catch { /* fall back to the index page */ }
  }
  const url = liveViewUrl(sid);
  log.info(url);
  if (!(await portInUse(UI_PORT))) log.warn(`the live view UI is not running on port ${UI_PORT}. Start it with: shoav start --ui`);
  if (!parsed.flags['no-browser'] && !env.SHOAV_NO_BROWSER) openInBrowser(url);
  return 0;
}
