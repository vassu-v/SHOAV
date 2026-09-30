// Ported from the old python CLI tests (test_cli.py), plus HTTP-level tests of
// `shoav status` and `shoav events` against a local fake controller.
import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import {
  filterGuardEvents, formatEventsTable, isGuardEvent, parseSidArg, sessionIdOf, timelineUrl,
} from '../src/events.js';
import { runCli, tempEnv } from './helpers.js';

function guardEvent(seq = 3, verdict = 'BLOCK', stage = 'egress', mode = 'enforce') {
  return {
    type: 'guard', event: 'verdict', call_id: 'call-1', session_id: 'sess-1', seq,
    ts: '2026-09-25T00:00:00Z', stage, tool: 'browser.execute_action', verdict, mode,
    enforced: true, reason: 'overlay at target', findings: [], target: { element_id: 'op-s1' },
  };
}
const toolEvent = (seq = 1) => ({ type: 'tool', event: 'end', call_id: 'call-1', seq, status: 'ok' });

function realCreateSessionResponse(sid = '08f6f408427d') {
  const merged = {
    _notice: 'live session',
    live_view: { session_id: sid, url: `http://127.0.0.1:3200/s/${sid}`, banner: `session ${sid}` },
    id: sid, name: `session-${sid}`, status: 'active', current_url: 'http://127.0.0.1:18634/flood.html',
  };
  return {
    content: [{ type: 'text', text: JSON.stringify(merged) }, { type: 'text', text: `session ${sid}` }],
    structuredContent: merged,
    isError: false,
  };
}

test('guard predicates', () => {
  assert.equal(isGuardEvent(guardEvent()), true);
  assert.equal(isGuardEvent(toolEvent()), false);
  assert.equal(isGuardEvent({ event: 'verdict', verdict: 'REWRITE', stage: 'ingress' }), true);
  assert.equal(isGuardEvent('nope'), false);
  assert.equal(isGuardEvent({ guard: {} }), false);
  assert.equal(isGuardEvent({ guard: { verdict: 'ALLOW' } }), true);
});

test('filter by verdict, stage and mode (case insensitive)', () => {
  const events = [guardEvent(1, 'BLOCK', 'egress'), guardEvent(2, 'REWRITE', 'ingress')];
  assert.equal(filterGuardEvents(events).length, 2);
  assert.deepEqual(filterGuardEvents(events, { verdict: 'block' }).map((e) => e.seq), [1]);
  assert.deepEqual(filterGuardEvents(events, { stage: 'INGRESS' }).map((e) => e.seq), [2]);
  const modes = [guardEvent(1, 'BLOCK', 'egress', 'enforce'), guardEvent(2, 'BLOCK', 'egress', 'observe')];
  assert.equal(filterGuardEvents(modes, { mode: 'observe' }).length, 1);
  assert.deepEqual(filterGuardEvents(null), []);
});

test('session id parsing shapes', () => {
  assert.equal(sessionIdOf(realCreateSessionResponse('08f6f408427d')), '08f6f408427d');
  assert.equal(sessionIdOf({ content: [{ type: 'text', text: 'banner' }], structuredContent: { live_view: { session_id: 'abc123def456' } } }), 'abc123def456');
  assert.equal(sessionIdOf({ content: [{ type: 'text', text: JSON.stringify({ id: '08f6f408427d', name: 'x' }) }], isError: false }), '08f6f408427d');
  assert.equal(sessionIdOf({ structuredContent: { id: 'sid-9' }, content: [] }), 'sid-9');
  assert.equal(sessionIdOf({ jsonrpc: '2.0', result: realCreateSessionResponse('rpc-1') }), 'rpc-1');
  assert.equal(sessionIdOf({ result: { content: [{ type: 'text', text: '{"id":"rpc-txt"}' }] } }), 'rpc-txt');
  assert.equal(sessionIdOf({ content: [], structuredContent: {} }), null);
  assert.equal(sessionIdOf({}), null);
  assert.equal(sessionIdOf('x'), null);
});

test('parseSidArg accepts id, live view URL and pasted JSON', () => {
  assert.equal(parseSidArg('sess-1'), 'sess-1');
  assert.equal(parseSidArg('http://127.0.0.1:3200/s/08f6f408427d'), '08f6f408427d');
  assert.equal(parseSidArg(JSON.stringify(realCreateSessionResponse('abc'))), 'abc');
  assert.throws(() => parseSidArg('{not json'), /does not parse/);
  assert.throws(() => parseSidArg('{"x":1}'), /no session id/);
  assert.throws(() => parseSidArg('../../etc'), /invalid session id/);
  assert.throws(() => parseSidArg('http://127.0.0.1:3200/other'), /live view link/);
});

test('timeline url path and query', () => {
  const u = timelineUrl('http://127.0.0.1:18501/', 'sess-9', 5, 7);
  assert.ok(u.startsWith('http://127.0.0.1:18501/live-api/sessions/sess-9/timeline?'));
  assert.match(u, /after_seq=5/);
  assert.match(u, /limit=7/);
});

test('table formatting', () => {
  assert.equal(formatEventsTable([]), 'no guard events');
  const out = formatEventsTable([guardEvent(3, 'BLOCK')]);
  const [head, row] = out.split('\n');
  assert.match(head, /^SEQ\s+TIME\s+STAGE\s+VERDICT/);
  assert.match(row, /^3\s+00:00:00\s+egress\s+BLOCK\s+enforce\s+yes\s+execute_action\s+overlay at target$/);
});

// ---- fake controller ---------------------------------------------------------

async function fakeController(routes) {
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push(req.url);
    const path = req.url.split('?')[0];
    const body = routes[path];
    if (body === undefined) { res.writeHead(404, { 'content-type': 'application/json' }); res.end('{"detail":"nf"}'); return; }
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  return { port: server.address().port, seen, close: () => new Promise((r) => server.close(r)) };
}

test('status: friendly message when down', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const fake = await fakeController({});
  const port = fake.port;
  await fake.close(); // port now closed
  const r = await runCli(['status', '--port', String(port)], t.env);
  assert.equal(r.code, 1);
  assert.match(r.stdout, new RegExp(`not running on port ${port}.*shoav start --port ${port}`));
});

test('status: prints mode, counters and session count', async (tt) => {
  const t = tempEnv();
  const fake = await fakeController({
    '/healthz': { status: 'ok' },
    '/live-api/guard': { mode: 'enforce', version: '1', counters: { allow: 5, rewrite: 2, block: 1, escalate: 0 } },
    '/live-api/sessions': { sessions: [{ id: 'a' }, { id: 'b' }] },
  });
  tt.after(async () => { await fake.close(); t.cleanup(); });
  const r = await runCli(['status', '--port', String(fake.port)], t.env);
  assert.equal(r.code, 0, r.stderr);
  assert.match(r.stdout, /guard mode\s+enforce/);
  assert.match(r.stdout, /allow 5\s+rewrite 2\s+block 1\s+escalate 0/);
  assert.match(r.stdout, /sessions\s+2/);
  const j = await runCli(['status', '--port', String(fake.port), '--json'], t.env);
  assert.equal(JSON.parse(j.stdout).guard.mode, 'enforce');
  assert.ok(fake.seen.includes('/live-api/guard'));
});

test('events: guard only, filters, query and json', async (tt) => {
  const t = tempEnv();
  const fake = await fakeController({
    '/healthz': { status: 'ok' },
    '/live-api/sessions/sess-1/timeline': { events: [toolEvent(1), guardEvent(2), guardEvent(3, 'REWRITE', 'ingress')] },
    '/live-api/sessions/empty/timeline': { events: [] },
  });
  tt.after(async () => { await fake.close(); t.cleanup(); });
  const port = String(fake.port);
  const j = await runCli(['events', 'sess-1', '--port', port, '--json'], t.env);
  assert.equal(j.code, 0, j.stderr);
  const out = JSON.parse(j.stdout);
  assert.equal(out.session_id, 'sess-1');
  assert.equal(out.guard_events.length, 2);
  const f = await runCli(['events', 'http://127.0.0.1:3200/s/sess-1', '--port', port, '--json', '--verdict', 'REWRITE', '--after-seq', '5', '--limit', '7'], t.env);
  assert.deepEqual(JSON.parse(f.stdout).guard_events.map((e) => e.seq), [3]);
  assert.ok(fake.seen.some((u) => u.includes('after_seq=5') && u.includes('limit=7')));
  const table = await runCli(['events', 'sess-1', '--port', port], t.env);
  assert.match(table.stdout, /BLOCK/);
  assert.match(table.stdout, /REWRITE/);
  const empty = await runCli(['events', 'empty', '--port', port], t.env);
  assert.match(empty.stdout, /no guard events/);
  const missing = await runCli(['events', 'nope', '--port', port], t.env);
  assert.equal(missing.code, 1);
  assert.match(missing.stderr, /not found/);
});

test('open prints the live view link for a session', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const r = await runCli(['open', 'abc123', '--no-browser', '--port', '1'], t.env);
  assert.equal(r.code, 0, r.stderr);
  assert.match(r.stdout, /http:\/\/127\.0\.0\.1:3200\/s\/abc123/);
});
