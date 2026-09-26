// Path conventions. Every home-relative path goes through userHome()/shoavHome()
// so tests can point HOME, USERPROFILE and SHOAV_HOME at temp dirs.
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const SKILL_SRC = path.join(PKG_ROOT, 'skill');
export const SERVER_DIR = path.join(PKG_ROOT, 'server');
export const CONTROLLER_DIR = path.join(SERVER_DIR, 'controller');
export const LIVE_UI_DIR = path.join(SERVER_DIR, 'live-ui');
export const GUARD_DIR = path.join(PKG_ROOT, 'guard');

export const DEFAULT_PORT = 18500;
export const DEFAULT_MCP_URL = `http://127.0.0.1:${DEFAULT_PORT}/mcp`;
export const UI_PORT = 3200;
export const UI_BASE = `http://127.0.0.1:${UI_PORT}`;

export function userHome(env = process.env) {
  const pick = process.platform === 'win32'
    ? env.USERPROFILE || env.HOME
    : env.HOME || env.USERPROFILE;
  return path.resolve(pick || os.homedir());
}

export function shoavHome(env = process.env) {
  return env.SHOAV_HOME ? path.resolve(env.SHOAV_HOME) : path.join(userHome(env), '.shoav');
}

export function xdgConfigHome(env = process.env) {
  return env.XDG_CONFIG_HOME ? path.resolve(env.XDG_CONFIG_HOME) : path.join(userHome(env), '.config');
}

export function dataDir(port, env = process.env) {
  return path.join(shoavHome(env), 'data', String(port));
}

export function venvDir(env = process.env) {
  return path.join(shoavHome(env), 'venv');
}

export function venvPython(env = process.env) {
  return process.platform === 'win32'
    ? path.join(venvDir(env), 'Scripts', 'python.exe')
    : path.join(venvDir(env), 'bin', 'python');
}

export function controllerUrl(port) {
  return `http://127.0.0.1:${port}`;
}

export function liveViewUrl(sid) {
  return sid ? `${UI_BASE}/s/${encodeURIComponent(sid)}` : `${UI_BASE}/`;
}
