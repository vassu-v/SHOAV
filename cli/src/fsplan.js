// A write plan: every change is computed first (so --dry-run can print it), then
// applied. Writes are idempotent: identical content is reported "unchanged" and
// not rewritten. Nothing here ever deletes a file.
import fs from 'node:fs';
import path from 'node:path';

export function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

export function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export class MergeConflict extends Error {}

// Merge `patch` into `target` in place. Objects recurse, arrays union (by JSON
// equality, order kept), scalars are set. A container type clash (for example
// mcpServers is an array in the user file) raises MergeConflict so the caller
// leaves the file alone.
export function mergeInto(target, patch, where = '') {
  for (const [key, value] of Object.entries(patch)) {
    const here = where ? `${where}.${key}` : key;
    const cur = target[key];
    if (isPlainObject(value)) {
      if (cur === undefined) target[key] = mergeInto({}, value, here);
      else if (isPlainObject(cur)) mergeInto(cur, value, here);
      else throw new MergeConflict(`"${here}" is not an object`);
    } else if (Array.isArray(value)) {
      if (cur === undefined) target[key] = [...value];
      else if (Array.isArray(cur)) {
        for (const item of value) if (!cur.some((x) => deepEqual(x, item))) cur.push(item);
      } else throw new MergeConflict(`"${here}" is not a list`);
    } else {
      target[key] = value;
    }
  }
  return target;
}

function readText(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
}

function detectEol(text) {
  return text && text.includes('\r\n') ? '\r\n' : '\n';
}

// Plan a JSON merge. `patchFn(existingObj)` returns the patch to merge.
export function planJson(file, patchFn, note) {
  const raw = readText(file);
  const patchForNew = patchFn({});
  if (raw === null) {
    const obj = mergeInto({}, patchForNew);
    return { kind: 'write', path: file, status: 'create', content: `${JSON.stringify(obj, null, 2)}\n`, note, patch: patchForNew };
  }
  const bom = raw.charCodeAt(0) === 0xfeff;
  const body = bom ? raw.slice(1) : raw;
  let parsed;
  try {
    parsed = body.trim() ? JSON.parse(body) : {};
  } catch {
    return { kind: 'manual', path: file, status: 'invalid', reason: 'existing file is not valid JSON (comments or a syntax error); left untouched', patch: patchForNew, note };
  }
  if (!isPlainObject(parsed)) {
    return { kind: 'manual', path: file, status: 'invalid', reason: 'existing file is not a JSON object; left untouched', patch: patchForNew, note };
  }
  const patch = patchFn(parsed);
  const merged = structuredClone(parsed);
  try {
    mergeInto(merged, patch);
  } catch (err) {
    if (err instanceof MergeConflict) {
      return { kind: 'manual', path: file, status: 'invalid', reason: `${err.message} in the existing file; left untouched`, patch, note };
    }
    throw err;
  }
  if (deepEqual(merged, parsed)) return { kind: 'write', path: file, status: 'unchanged', note };
  const eol = detectEol(body);
  const text = JSON.stringify(merged, null, 2).replace(/\n/g, eol) + eol;
  return { kind: 'write', path: file, status: 'update', content: (bom ? '﻿' : '') + text, note };
}

// Plan a whole-file text write (used for files we own entirely, for example a
// .mdc rule). An existing different file is updated.
export function planText(file, content, note) {
  const raw = readText(file);
  if (raw === null) return { kind: 'write', path: file, status: 'create', content, note };
  if (raw === content) return { kind: 'write', path: file, status: 'unchanged', note };
  return { kind: 'write', path: file, status: 'update', content, note };
}

// Plan a text edit: `editFn(existing or null)` returns the new text.
export function planEdit(file, editFn, note) {
  const raw = readText(file);
  const next = editFn(raw);
  if (raw === null) return { kind: 'write', path: file, status: 'create', content: next, note };
  if (next === raw) return { kind: 'write', path: file, status: 'unchanged', note };
  return { kind: 'write', path: file, status: 'update', content: next, note };
}

// Plan copying a directory tree (files only, skipping caches).
const SKIP = new Set(['__pycache__', 'node_modules', '.DS_Store', '.pytest_cache']);
export function listFiles(dir, rel = '') {
  const out = [];
  for (const entry of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    if (SKIP.has(entry.name) || entry.name.endsWith('.pyc')) continue;
    const r = rel ? path.join(rel, entry.name) : entry.name;
    if (entry.isDirectory()) out.push(...listFiles(dir, r));
    else if (entry.isFile()) out.push(r);
  }
  return out.sort();
}

export function planCopy(src, dest, note) {
  const want = fs.readFileSync(src);
  let have = null;
  try { have = fs.readFileSync(dest); } catch (err) { if (err.code !== 'ENOENT') throw err; }
  if (have === null) return { kind: 'copy', src, path: dest, status: 'create', note };
  if (Buffer.compare(want, have) === 0) return { kind: 'copy', src, path: dest, status: 'unchanged', note };
  return { kind: 'copy', src, path: dest, status: 'update', note };
}

export function applyPlan(actions) {
  for (const a of actions) {
    if (a.status !== 'create' && a.status !== 'update') continue;
    fs.mkdirSync(path.dirname(a.path), { recursive: true });
    if (a.kind === 'copy') fs.copyFileSync(a.src, a.path);
    else fs.writeFileSync(a.path, a.content);
  }
}
