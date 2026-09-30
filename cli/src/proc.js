// Cross-platform process helpers for the pid files that `shoav start` writes.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';

export function readPid(file) {
  try {
    const n = Number(fs.readFileSync(file, 'utf8').trim());
    return Number.isInteger(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

export function isAlive(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err.code === 'EPERM';
  }
}

// Lowercased image name of a pid, or null when it is not running.
export function processName(pid) {
  if (!isAlive(pid)) return null;
  if (process.platform === 'win32') {
    const r = spawnSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], { encoding: 'utf8', windowsHide: true });
    const m = (r.stdout || '').match(/^"([^"]+)","(\d+)"/m);
    return m && Number(m[2]) === pid ? m[1].toLowerCase() : null;
  }
  const r = spawnSync('ps', ['-p', String(pid), '-o', 'comm='], { encoding: 'utf8' });
  const name = (r.stdout || '').trim();
  return name ? name.toLowerCase() : null;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Kill a process and its children. The process was started detached, so on
// POSIX it leads its own process group.
export async function killTree(pid) {
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  } else {
    try { process.kill(-pid, 'SIGTERM'); } catch { try { process.kill(pid, 'SIGTERM'); } catch { /* gone */ } }
    for (let i = 0; i < 40 && isAlive(pid); i++) await sleep(200);
    if (isAlive(pid)) {
      try { process.kill(-pid, 'SIGKILL'); } catch { try { process.kill(pid, 'SIGKILL'); } catch { /* gone */ } }
    }
  }
  for (let i = 0; i < 25 && isAlive(pid); i++) await sleep(200);
  return !isAlive(pid);
}
