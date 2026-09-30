import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseAgents, parseArgs, parseChoice, parsePort } from '../src/args.js';
import { validateMcpUrl } from '../src/validate.js';

test('no command means install', () => {
  const p = parseArgs(['--agent', 'claude', '--yes']);
  assert.equal(p.command, 'install');
  assert.deepEqual(p.flags, { agent: 'claude', yes: true });
});

test('flag=value, -y alias and boolean flags', () => {
  const p = parseArgs(['install', '--what=mcp', '-y', '--dry-run', '--dir', 'x y']);
  assert.deepEqual(p.flags, { what: 'mcp', yes: true, 'dry-run': true, dir: 'x y' });
});

test('help and version', () => {
  assert.equal(parseArgs(['--help']).help, true);
  assert.equal(parseArgs(['-v']).version, true);
  const h = parseArgs(['start', '--help']);
  assert.equal(h.help, true);
  assert.equal(h.command, 'start');
  const h2 = parseArgs(['help', 'events']);
  assert.equal(h2.help, true);
  assert.equal(h2.command, 'events');
});

test('events takes one positional, extra positional is an error', () => {
  const p = parseArgs(['events', 'sess-1', '--verdict', 'BLOCK', '--json']);
  assert.deepEqual(p.positionals, ['sess-1']);
  assert.equal(p.flags.verdict, 'BLOCK');
  assert.throws(() => parseArgs(['events', 'a', 'b']), /unexpected argument/);
});

test('unknown command, unknown flag, missing value', () => {
  assert.throws(() => parseArgs(['frobnicate']), /unknown command/);
  assert.throws(() => parseArgs(['status', '--agent', 'x']), /unknown flag --agent/);
  assert.throws(() => parseArgs(['install', '--dir']), /needs a value/);
  assert.throws(() => parseArgs(['install', '--dir', '--yes']), /needs a value/);
  assert.throws(() => parseArgs(['start', '--headless=maybe']), /does not take a value/);
});

test('parsePort', () => {
  assert.equal(parsePort(undefined, 18500), 18500);
  assert.equal(parsePort('18551', 1), 18551);
  for (const bad of ['0', '65536', 'abc', '12.5', '-1', '']) assert.throws(() => parsePort(bad, 1), /invalid --port/);
});

test('parseChoice', () => {
  assert.equal(parseChoice('guard', undefined, ['off', 'enforce'], 'enforce'), 'enforce');
  assert.equal(parseChoice('guard', 'OFF', ['off', 'enforce'], 'enforce'), 'off');
  assert.throws(() => parseChoice('guard', 'loud', ['off'], 'off'), /invalid --guard/);
});

test('parseAgents with aliases, dedupe and all', () => {
  assert.deepEqual(parseAgents('claude, Antigravity,agy'), ['claude', 'agy']);
  assert.deepEqual(parseAgents('all'), ['claude', 'opencode', 'agy', 'codex', 'cursor']);
  assert.throws(() => parseAgents('vim'), /unknown agent/);
  assert.throws(() => parseAgents(','), /at least one/);
});

test('url validation accepts http(s) ending in /mcp', () => {
  assert.equal(validateMcpUrl('http://127.0.0.1:18500/mcp'), 'http://127.0.0.1:18500/mcp');
  assert.equal(validateMcpUrl(' https://example.test/a/mcp '), 'https://example.test/a/mcp');
  assert.equal(validateMcpUrl('http://localhost:9000/mcp'), 'http://localhost:9000/mcp');
});

test('url validation rejects weird input', () => {
  const bad = [
    '', 'not a url', 'ftp://127.0.0.1/mcp', 'file:///etc/mcp', 'javascript:alert(1)//mcp',
    'http://127.0.0.1:18500/', 'http://127.0.0.1:18500/mcp/', 'http://127.0.0.1:18500/mcpx',
    'http://user:pw@127.0.0.1/mcp', 'http://127.0.0.1/mcp?x=1', 'http://127.0.0.1/mcp#a',
    'http://127.0.0.1/m cp/mcp', 'http://127.0.0.1/"/mcp', 'http://127.0.0.1/\n/mcp',
  ];
  for (const u of bad) assert.throws(() => validateMcpUrl(u), /invalid --url/, u);
});
