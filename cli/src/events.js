// Guard timeline helpers, ported from the old Python CLI (cli.py) with the
// same session id parsing shapes and event filters.
import { getJson } from './http.js';
import { CliError } from './ui.js';

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const str = (v) => (typeof v === 'string' && v.trim() ? v.trim() : null);

function sidFromDict(candidate) {
  if (!isObj(candidate)) return null;
  for (const k of ['session_id', 'id', 'sid']) if (str(candidate[k])) return str(candidate[k]);
  for (const nk of ['live_view', 'result', 'session', 'data']) {
    const nested = candidate[nk];
    if (!isObj(nested)) continue;
    for (const k of ['session_id', 'id', 'sid']) if (str(nested[k])) return str(nested[k]);
    if (nk === 'result' && isObj(nested.live_view)) {
      for (const k of ['session_id', 'id', 'sid']) if (str(nested.live_view[k])) return str(nested.live_view[k]);
    }
  }
  return null;
}

function tryJson(text) {
  if (typeof text !== 'string' || !text.trim().startsWith('{')) return null;
  try { return JSON.parse(text); } catch { return null; }
}

function textBlocks(resp) {
  if (!isObj(resp) || !Array.isArray(resp.content)) return [];
  return resp.content.filter((b) => isObj(b) && typeof b.text === 'string').map((b) => b.text);
}

// Session id from a create_session tool response (gateway, JSON-RPC or text shapes).
export function sessionIdOf(resp) {
  if (!isObj(resp)) return null;
  let sid = sidFromDict(isObj(resp.structuredContent) ? resp.structuredContent : {});
  if (sid) return sid;
  if (isObj(resp.result)) {
    const r = resp.result;
    sid = sidFromDict(isObj(r.structuredContent) ? r.structuredContent : {}) || sidFromDict(r);
    if (sid) return sid;
    for (const t of textBlocks(r)) { sid = sidFromDict(tryJson(t)); if (sid) return sid; }
  }
  sid = sidFromDict(resp);
  if (sid) return sid;
  for (const t of textBlocks(resp)) { sid = sidFromDict(tryJson(t)); if (sid) return sid; }
  return null;
}

// Accept a bare id, a live view URL (.../s/<id>) or a pasted JSON response.
export function parseSidArg(arg) {
  const raw = String(arg ?? '').trim();
  if (!raw) return null;
  let sid = raw;
  if (raw.startsWith('{')) {
    let parsed;
    try { parsed = JSON.parse(raw); } catch { throw new CliError('session argument looks like JSON but does not parse', 2); }
    sid = sessionIdOf(parsed);
    if (!sid) throw new CliError('no session id found in the JSON you passed', 2);
  } else {
    const m = raw.match(/\/s\/([^/?#\s]+)/);
    if (/^https?:\/\//i.test(raw)) {
      if (!m) throw new CliError('URL does not look like a live view link (.../s/<session id>)', 2);
      sid = decodeURIComponent(m[1]);
    }
  }
  if (!/^[A-Za-z0-9._-]{1,128}$/.test(sid)) throw new CliError(`invalid session id "${sid.slice(0, 80)}"`, 2);
  return sid;
}

export function isGuardEvent(e) {
  if (!isObj(e)) return false;
  if (e.type === 'guard') return true;
  if (e.event === 'verdict' && 'verdict' in e) return true;
  return isObj(e.guard) && Object.keys(e.guard).length > 0;
}

export function filterGuardEvents(events, { verdict, stage, mode } = {}) {
  let out = (Array.isArray(events) ? events : []).filter(isGuardEvent);
  if (verdict != null) { const w = verdict.trim().toUpperCase(); out = out.filter((e) => String(e.verdict ?? '').toUpperCase() === w); }
  if (stage != null) { const w = stage.trim().toLowerCase(); out = out.filter((e) => String(e.stage ?? '').toLowerCase() === w); }
  if (mode != null) { const w = mode.trim().toLowerCase(); out = out.filter((e) => String(e.mode ?? '').toLowerCase() === w); }
  return out;
}

export function timelineUrl(base, sid, afterSeq = 0, limit = 100) {
  const q = new URLSearchParams({ after_seq: String(afterSeq), limit: String(limit) });
  return `${base.replace(/\/+$/, '')}/live-api/sessions/${encodeURIComponent(sid)}/timeline?${q}`;
}

export async function fetchTimeline(base, sid, afterSeq, limit) {
  return getJson(timelineUrl(base, sid, afterSeq, limit), { timeout: 15000 });
}

function cell(v, width) {
  const s = v === undefined || v === null ? '' : String(v).replace(/\s+/g, ' ');
  return s.length > width ? `${s.slice(0, width - 3)}...` : s.padEnd(width);
}

function timeOf(ts) {
  if (typeof ts !== 'string') return '';
  const m = ts.match(/T(\d{2}:\d{2}:\d{2})/);
  return m ? m[1] : ts.slice(0, 8);
}

export function formatEventsTable(events) {
  if (!events.length) return 'no guard events';
  const cols = [['SEQ', 5], ['TIME', 9], ['STAGE', 8], ['VERDICT', 9], ['MODE', 8], ['ENF', 4], ['TOOL', 26], ['REASON', 60]];
  const lines = [cols.map(([h, w]) => cell(h, w)).join(' ').trimEnd()];
  for (const e of events) {
    const tool = String(e.tool ?? '').replace(/^browser[._]/, '');
    const enf = e.enforced === true ? 'yes' : e.enforced === false ? 'no' : '?';
    const row = [e.seq ?? '?', timeOf(e.ts), e.stage ?? '?', e.verdict ?? '?', e.mode ?? '?', enf, tool || '?', String(e.reason ?? '').slice(0, 120)];
    lines.push(row.map((v, i) => cell(v, cols[i][1])).join(' ').trimEnd());
  }
  return lines.join('\n');
}
