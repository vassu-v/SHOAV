// Shared test helpers. Every test works in a fresh temp dir; HOME, USERPROFILE,
// SHOAV_HOME and XDG_CONFIG_HOME point inside it so nothing touches the real home.
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const BIN = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'bin', 'shoav.js');

export function tempEnv() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'shoav-test-'));
  const home = path.join(root, 'home');
  const project = path.join(root, 'project');
  fs.mkdirSync(home, { recursive: true });
  fs.mkdirSync(project, { recursive: true });
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    SHOAV_HOME: path.join(home, '.shoav'),
    XDG_CONFIG_HOME: path.join(home, '.config'),
    NO_COLOR: '1',
    SHOAV_NO_BROWSER: '1',
  };
  delete env.CODEX_HOME;
  return { root, home, project, env, cleanup: () => fs.rmSync(root, { recursive: true, force: true }) };
}

export function runCli(args, env, opts = {}) {
  return new Promise((resolve) => {
    execFile(process.execPath, [BIN, ...args], { env, cwd: opts.cwd, timeout: 30000 }, (err, stdout, stderr) => {
      resolve({ code: err ? (typeof err.code === 'number' ? err.code : 1) : 0, stdout, stderr });
    });
  });
}

// Map of relative path -> file bytes (as base64) for a whole tree.
export function snapshot(dir) {
  const out = {};
  const walk = (rel) => {
    for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
      const r = path.join(rel, e.name);
      if (e.isDirectory()) walk(r);
      else out[r.split(path.sep).join('/')] = fs.readFileSync(path.join(dir, r)).toString('base64');
    }
  };
  if (fs.existsSync(dir)) walk('');
  return out;
}

export function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^﻿/, ''));
}
