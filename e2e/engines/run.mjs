#!/usr/bin/env node
// Real agent CLIs against a SHOAV controller that the shoav CLI installs and starts.
// node e2e/engines/run.mjs --engine agy|claude|opencode|codex|all --task <name|all> --guard enforce|off|observe
//   [--model X] [--timeout 300] [--out <dir>] [--work <dir>] [--repeat N] [--keep] [--stop]
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ENGINES, DEFAULT_MODELS, controllerPort, engineCommand, fixturePort, listCommand } from './engines.mjs';
import { HERE, SHOAV_JS, SHOAV_ROOT, callTool, engineEnv, getJson, healthy, resolveBin, run, serveFixtures } from './lib.mjs';
import { NEEDS_PAGE_STATE, TASKS, promptFor, score } from './tasks.mjs';

function parseArgs(argv) {
  const f = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const k = a.slice(2);
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) f[k] = true; else { f[k] = v; i++; }
  }
  return f;
}

const flags = parseArgs(process.argv.slice(2));
const listOf = (v, all) => (!v || v === 'all' ? all : String(v).split(',').map((s) => s.trim()).filter(Boolean));
const engines = listOf(flags.engine, ENGINES);
const tasks = listOf(flags.task, TASKS);
const guards = listOf(flags.guard || 'enforce', ['enforce', 'off']);
const timeoutMs = Number(flags.timeout || 300) * 1000;
const repeat = Number(flags.repeat || 1);
const outDir = path.resolve(flags.out || path.join(HERE, 'results'));
const work = path.resolve(flags.work || process.env.SHOAV_ENGINES_WORK || path.join(os.tmpdir(), 'shoav-engines'));
const shoavHome = path.resolve(process.env.SHOAV_HOME || path.join(work, 'shoav_home'));
for (const e of engines) if (!ENGINES.includes(e)) { console.error(`unknown engine ${e}`); process.exit(2); }
for (const t of tasks) if (!TASKS.includes(t)) { console.error(`unknown task ${t}`); process.exit(2); }
fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(work, { recursive: true });

const cliEnv = { ...process.env, SHOAV_HOME: shoavHome, SHOAV_NO_BROWSER: '1' };
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

// ---- controllers (serialised: they share one venv) -------------------------
let startChain = Promise.resolve();
const started = new Set();
function ensureController(port, guard) {
  const p = startChain.then(async () => {
    const base = `http://127.0.0.1:${port}`;
    if (await healthy(base)) {
      const g = await getJson(`${base}/live-api/guard`).catch(() => ({}));
      if (g.mode && g.mode !== guard) throw new Error(`controller on ${port} runs guard ${g.mode}, wanted ${guard}; stop it first`);
      return { base, start: { reused: true } };
    }
    log(`shoav start --port ${port} --guard ${guard}`);
    const r = await run(process.execPath, [SHOAV_JS, 'start', '--port', String(port), '--headless', '--guard', guard, '--yes'], { env: cliEnv, timeoutMs: 15 * 60000 });
    if (r.code !== 0) throw new Error(`shoav start failed (${r.code}): ${(r.stdout + r.stderr).slice(-1500)}`);
    started.add(port);
    return { base, start: { reused: false, code: r.code, ms: r.ms } };
  });
  startChain = p.catch(() => {});
  return p;
}

async function stopController(port) {
  const r = await run(process.execPath, [SHOAV_JS, 'stop', '--port', String(port)], { env: cliEnv, timeoutMs: 60000 });
  log(`shoav stop --port ${port} -> ${r.code}`);
}

async function sessionIds(base) {
  const s = await getJson(`${base}/live-api/sessions`).catch(() => ({ sessions: [] }));
  return (s.sessions || []);
}

async function closeLive(base) {
  for (const s of await sessionIds(base)) {
    if (s.state === 'live') await callTool(base, 'browser_close_session', { session_id: s.id }).catch(() => {});
  }
}

async function timeline(base, sid) {
  const events = [];
  let after = 0;
  for (let i = 0; i < 50; i++) {
    const t = await getJson(`${base}/live-api/sessions/${sid}/timeline?after_seq=${after}&limit=500`).catch(() => null);
    if (!t) break;
    events.push(...(t.events || []));
    if (!t.has_more) break;
    after = t.last_seq;
  }
  return events;
}

function textOf(resp) {
  return (resp?.content || []).map((b) => b.text || '').join('\n') + JSON.stringify(resp?.structuredContent || {});
}

// ---- one run ---------------------------------------------------------------
async function runOne({ engine, task, guard, model, bin, fixBase, rep }) {
  const port = controllerPort(engine, guard);
  const mcpUrl = `http://127.0.0.1:${port}/mcp`;
  const id = `${engine}-${guard}-${task}-${Date.now().toString(36)}${rep ? `-r${rep}` : ''}`;
  const proj = path.join(work, 'proj', id);
  fs.mkdirSync(proj, { recursive: true });
  const rec = { id, engine, task, guard, model: model || '(engine default)', date: new Date().toISOString(), controller_port: port, mcp_url: mcpUrl, project: proj, shoav_root: SHOAV_ROOT, shoav_rev: process.env.SHOAV_REV || null };

  // 1) dogfood the installer
  let inst = await run(process.execPath, [SHOAV_JS, 'install', '--what', 'both', '--agent', engine, '--dir', proj, '--url', mcpUrl, '--guard', guard, '--yes'], { env: cliEnv, timeoutMs: 60000 });
  rec.install = { what: 'both', code: inst.code, tail: (inst.stdout + inst.stderr).replace(/\x1b\[[0-9;]*m/g, '').split(/\r?\n/).filter(Boolean).slice(-6).join('\n') };
  if (inst.code !== 0) {
    const fb = await run(process.execPath, [SHOAV_JS, 'install', '--what', 'mcp', '--agent', engine, '--dir', proj, '--url', mcpUrl, '--guard', guard, '--yes'], { env: cliEnv, timeoutMs: 60000 });
    rec.install_fallback = { what: 'mcp', code: fb.code };
  }
  rec.installed_files = listTree(proj);

  // 2) the engine's own MCP listing
  const { base } = await ensureController(port, guard);
  rec.guard_mode_live = (await getJson(`${base}/live-api/guard`).catch(() => ({}))).mode;
  rec.mcp_list = [];
  for (const args of listCommand(engine, mcpUrl)) {
    const r = await run(bin, args, { cwd: proj, env: engineEnv(), timeoutMs: 90000 });
    const out = (r.stdout + r.stderr).replace(/\x1b\[[0-9;]*m/g, '');
    rec.mcp_list.push({ cmd: `${engine} ${args.join(' ')}`, code: r.code, timedOut: r.timedOut, shoav_line: out.split(/\r?\n/).filter((l) => /shoav/i.test(l)).slice(0, 3).join(' | ') || null, out: out.slice(0, 1500) });
  }

  // 3) run the engine
  await closeLive(base);
  const before = new Set((await sessionIds(base)).map((s) => s.id));
  const g0 = await getJson(`${base}/live-api/guard`).catch(() => ({}));
  const prompt = promptFor(task, fixBase);
  const spec = engineCommand(engine, { prompt, model, proj, mcpUrl });
  log(`[${id}] running ${engine} (${guard}) ...`);
  const r = await run(bin, spec.args, { cwd: proj, env: engineEnv(), timeoutMs });
  const parsed = spec.parse(r.stdout, r.stderr);
  rec.prompt = prompt;
  rec.exit = { code: r.code, timedOut: r.timedOut, ms: r.ms };
  rec.final_text = parsed.text.slice(-4000);
  rec.engine_meta = parsed.meta;
  rec.stdout_tail = r.stdout.slice(-3000);
  rec.stderr_tail = r.stderr.slice(-2000);

  // 4) evidence from the controller
  const after = await sessionIds(base);
  const mine = after.filter((s) => !before.has(s.id));
  const events = [];
  for (const s of mine) events.push(...(await timeline(base, s.id)));
  const g1 = await getJson(`${base}/live-api/guard`).catch(() => ({}));
  const delta = {};
  for (const k of ['allow', 'rewrite', 'block', 'escalate']) delta[k] = (g1.counters?.[k] ?? 0) - (g0.counters?.[k] ?? 0);
  let pageState = '';
  if (NEEDS_PAGE_STATE.has(task)) {
    for (const s of mine.filter((x) => x.state === 'live')) {
      const snap = await callTool(base, 'browser_snapshot', { session_id: s.id }).catch((e) => ({ error: String(e) }));
      pageState += textOf(snap);
    }
  }
  await closeLive(base);
  rec.sessions = mine.map((s) => ({ id: s.id, state: s.state, url: s.current_url, tool_calls: s.tool_calls, client: s.client }));
  rec.guard_delta = delta;
  rec.page_state_probe = pageState ? pageState.slice(0, 20000) : null;
  rec.score = score(task, guard, parsed.text, { events, sessions: mine, pageState, guardDelta: delta });
  rec.events = events;
  const file = path.join(outDir, `${id}.json`);
  fs.writeFileSync(file, JSON.stringify(rec, null, 2));
  log(`[${id}] ${rec.score.pass ? 'PASS' : 'FAIL'} exit=${r.code}${r.timedOut ? ' TIMEOUT' : ''} sessions=${mine.map((s) => s.id).join(',') || '-'} verdicts=${rec.score.verdicts_seen.join(',') || '-'} result=${rec.score.result ?? '-'} compromise=${rec.score.compromise.join('; ') || '-'}`);
  return rec;
}

function listTree(dir, base = dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== 'scripts') listTree(p, base, out); else out.push(path.relative(base, p).split(path.sep).join('/') + '/'); } else out.push(path.relative(base, p).split(path.sep).join('/'));
  }
  return out;
}

async function main() {
  if (flags.stop) {
    for (let p = 18570; p <= 18579; p++) await stopController(p);
    return;
  }
  const servers = [];
  const all = [];
  try {
    await Promise.all(engines.map(async (engine) => {
      const bin = resolveBin(engine);
      if (!bin) {
        for (const guard of guards) for (const task of tasks) {
          const rec = { id: `${engine}-${guard}-${task}-notrun`, engine, task, guard, date: new Date().toISOString(), not_run: `${engine} binary not found on PATH` };
          fs.writeFileSync(path.join(outDir, `${rec.id}.json`), JSON.stringify(rec, null, 2));
          all.push(rec);
        }
        return;
      }
      const fp = fixturePort(engine);
      servers.push(await serveFixtures(fp));
      const fixBase = `http://127.0.0.1:${fp}`;
      const model = flags.model || DEFAULT_MODELS[engine];
      for (const guard of guards) {
        for (const task of tasks) {
          for (let rep = 0; rep < repeat; rep++) {
            try {
              all.push(await runOne({ engine, task, guard, model, bin, fixBase, rep: repeat > 1 ? rep + 1 : 0 }));
            } catch (err) {
              log(`[${engine}/${guard}/${task}] harness error: ${err.message}`);
              const rec = { id: `${engine}-${guard}-${task}-err-${Date.now().toString(36)}`, engine, task, guard, date: new Date().toISOString(), not_run: `harness error: ${err.message.slice(0, 500)}` };
              fs.writeFileSync(path.join(outDir, `${rec.id}.json`), JSON.stringify(rec, null, 2));
              all.push(rec);
            }
          }
        }
      }
    }));
  } finally {
    for (const s of servers) s.close();
    if (!flags.keep) for (const p of started) await stopController(p);
  }
  console.log('\nengine    guard    task          pass  result');
  for (const r of all) console.log(`${r.engine.padEnd(9)} ${r.guard.padEnd(8)} ${r.task.padEnd(13)} ${r.not_run ? 'N/A ' : r.score.pass ? 'PASS' : 'FAIL'}  ${r.not_run || r.score.result || ''}`);
}

main().catch((err) => { console.error(err); process.exit(1); });
