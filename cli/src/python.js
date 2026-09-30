// Python discovery, the private venv, requirements and Chromium checks.
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { CONTROLLER_DIR, venvDir, venvPython } from './paths.js';

export const MIN_PY = [3, 11];

function versionOk(v) {
  const [maj, min] = v.split('.').map(Number);
  return maj > MIN_PY[0] || (maj === MIN_PY[0] && min >= MIN_PY[1]);
}

export function pythonCandidates(env = process.env) {
  const list = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  if (env.SHOAV_PYTHON) list.unshift([env.SHOAV_PYTHON, []]);
  return list;
}

// Returns { cmd, args, version } for the first Python >= 3.11, or { error, seen }.
export function findPython(env = process.env) {
  const seen = [];
  for (const [cmd, pre] of pythonCandidates(env)) {
    const r = spawnSync(cmd, [...pre, '-c', 'import sys;print("%d.%d.%d" % sys.version_info[:3])'], {
      encoding: 'utf8', timeout: 20000, windowsHide: true, env,
    });
    if (r.status !== 0 || !r.stdout) continue;
    const version = r.stdout.trim().split(/\s+/).pop();
    if (!/^\d+\.\d+\.\d+$/.test(version)) continue;
    seen.push(`${[cmd, ...pre].join(' ')} = ${version}`);
    if (versionOk(version)) return { cmd, args: pre, version };
  }
  return { error: `Python ${MIN_PY.join('.')} or newer not found`, seen };
}

export function venvExists(env = process.env) {
  return fs.existsSync(venvPython(env));
}

export function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { stdio: 'inherit', windowsHide: true, ...opts });
}

export function createVenv(py, env = process.env) {
  fs.mkdirSync(path.dirname(venvDir(env)), { recursive: true });
  const r = run(py.cmd, [...py.args, '-m', 'venv', venvDir(env)], { env });
  return r.status === 0;
}

function requirementsHash() {
  const file = path.join(CONTROLLER_DIR, 'requirements.txt');
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function markerPath(env) {
  return path.join(venvDir(env), '.shoav-requirements.sha256');
}

export function requirementsCurrent(env = process.env) {
  try {
    return fs.readFileSync(markerPath(env), 'utf8').trim() === requirementsHash();
  } catch {
    return false;
  }
}

export function installRequirements(env = process.env) {
  const req = path.join(CONTROLLER_DIR, 'requirements.txt');
  const r = run(venvPython(env), ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', req], { env });
  if (r.status !== 0) return false;
  fs.writeFileSync(markerPath(env), `${requirementsHash()}\n`);
  return true;
}

const CHROMIUM_PROBE = [
  'import os, sys',
  'from playwright.sync_api import sync_playwright',
  'with sync_playwright() as p:',
  '    exe = p.chromium.executable_path',
  'print(exe)',
  'sys.exit(0 if exe and os.path.exists(exe) else 3)',
].join('\n');

// { ok, path?, reason? }
export function chromiumStatus(env = process.env) {
  if (!venvExists(env)) return { ok: false, reason: 'venv missing' };
  const r = spawnSync(venvPython(env), ['-c', CHROMIUM_PROBE], { encoding: 'utf8', timeout: 60000, windowsHide: true, env });
  const out = (r.stdout || '').trim();
  if (r.status === 0) return { ok: true, path: out };
  if (r.status === 3) return { ok: false, reason: `not downloaded (expected ${out})` };
  return { ok: false, reason: (r.stderr || '').trim().split('\n').pop() || 'playwright not importable' };
}

export function installChromium(env = process.env) {
  return run(venvPython(env), ['-m', 'playwright', 'install', 'chromium'], { env }).status === 0;
}
