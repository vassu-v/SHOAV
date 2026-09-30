// Shared helpers for the engine harness: process running, HTTP, fixture server.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, '..', '..');
export const FIXTURES = path.join(REPO, 'e2e', 'fixtures');
// SHOAV_ROOT lets the harness dogfood a pinned copy of the product (for example
// `git archive HEAD` unpacked in a temp dir) while the working tree is being edited.
export const SHOAV_ROOT = path.resolve(process.env.SHOAV_ROOT || REPO);
export const SHOAV_JS = path.join(SHOAV_ROOT, 'cli', 'bin', 'shoav.js');
export const isWin = process.platform === 'win32';

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Resolve an engine binary to a real executable (npm .cmd shims point at an .exe).
export function resolveBin(name) {
  const r = spawnSync(isWin ? 'where' : 'which', [name], { encoding: 'utf8', windowsHide: true });
  const hits = (r.stdout || '').split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (!isWin) return hits[0] || null;
  const exe = hits.find((h) => h.toLowerCase().endsWith('.exe'));
  if (exe) return exe;
  const cmd = hits.find((h) => h.toLowerCase().endsWith('.cmd'));
  if (cmd) {
    const txt = fs.readFileSync(cmd, 'utf8');
    const m = txt.match(/"%dp0%\\([^"]+\.exe)"/i);
    if (m) {
      const p = path.join(path.dirname(cmd), m[1]);
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

export function killTree(pid) {
  if (!pid) return;
  if (isWin) spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  else { try { process.kill(-pid, 'SIGKILL'); } catch { try { process.kill(pid, 'SIGKILL'); } catch { /* gone */ } } }
}

// Run a command with a timeout; kill the whole tree on timeout.
export function run(cmd, args, { cwd, env, timeoutMs = 60000, input } = {}) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    let child;
    try {
      child = spawn(cmd, args, { cwd, env, windowsHide: true, detached: !isWin, stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (err) {
      resolve({ code: null, stdout: '', stderr: String(err), timedOut: false, ms: 0, error: String(err) });
      return;
    }
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    if (input !== undefined) child.stdin.end(input); else child.stdin.end();
    const timer = setTimeout(() => { timedOut = true; killTree(child.pid); }, timeoutMs);
    child.on('error', (err) => { stderr += `\n[spawn error] ${err.message}`; });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut, ms: Date.now() - t0 });
    });
  });
}

function request(method, url, body, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const req = http.request(url, {
      method,
      headers: { Accept: 'application/json', ...(data ? { 'Content-Type': 'application/json', 'Content-Length': data.length } : {}) },
    }, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { buf += c; });
      res.on('end', () => {
        let json = null;
        try { json = buf.trim() ? JSON.parse(buf) : {}; } catch { /* not json */ }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const err = new Error(`HTTP ${res.statusCode} ${url}`);
          err.status = res.statusCode;
          err.body = buf.slice(0, 500);
          return reject(err);
        }
        resolve(json ?? { raw: buf });
      });
    });
    req.setTimeout(timeout, () => req.destroy(new Error(`timeout ${url}`)));
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

export const getJson = (url, t) => request('GET', url, undefined, t);
export const postJson = (url, body, t) => request('POST', url, body, t);

export async function healthy(base) {
  try { return (await getJson(`${base}/healthz`, 2000)).status === 'ok'; } catch { return false; }
}

export async function callTool(base, name, args) {
  return postJson(`${base}/mcp/tools/call`, { name, arguments: args }, 90000);
}

// Static server for e2e/fixtures on 127.0.0.1:<port>.
export function serveFixtures(port) {
  const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css' };
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x');
    const name = path.basename(decodeURIComponent(u.pathname)) || 'index.html';
    const file = path.join(FIXTURES, name);
    if (!file.startsWith(FIXTURES) || !fs.existsSync(file)) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

// Environment for child engines: drop variables that make a nested Claude Code
// think it runs inside another session.
export function engineEnv(extra = {}) {
  const env = { ...process.env };
  for (const k of Object.keys(env)) {
    if (k.startsWith('CLAUDE')) delete env[k];
  }
  return { ...env, NO_COLOR: '1', ...extra };
}
