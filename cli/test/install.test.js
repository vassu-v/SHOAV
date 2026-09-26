import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { END, START, agentsBlock, ensureImportLine, upsertBlock } from '../src/agents-block.js';
import { mergeInto } from '../src/fsplan.js';
import { readJson, runCli, snapshot, tempEnv } from './helpers.js';

const URL = 'http://127.0.0.1:18500/mcp';
const ALL = 'claude,opencode,agy,codex,cursor,generic';

function install(t, extra = []) {
  return runCli(['install', '--what', 'both', '--agent', ALL, '--dir', t.project, '--yes', ...extra], t.env);
}

test('mergeInto keeps keys, unions arrays, flags container clashes', () => {
  const target = { a: 1, o: { x: 1 }, list: ['a'] };
  mergeInto(target, { o: { y: 2 }, list: ['a', 'b'], n: 3 });
  assert.deepEqual(target, { a: 1, o: { x: 1, y: 2 }, list: ['a', 'b'], n: 3 });
  assert.throws(() => mergeInto({ mcpServers: [] }, { mcpServers: { shoav: {} } }), /not an object/);
});

test('every project target writes its files', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const r = await install(t);
  assert.equal(r.code, 0, r.stderr);
  const p = (...s) => path.join(t.project, ...s);
  assert.deepEqual(readJson(p('.mcp.json')), { mcpServers: { shoav: { type: 'http', url: URL } } });
  const settings = readJson(p('.claude', 'settings.json'));
  assert.ok(settings.permissions.allow.includes('mcp__shoav'));
  assert.equal(fs.readFileSync(p('CLAUDE.md'), 'utf8'), '@AGENTS.md\n');
  assert.ok(fs.existsSync(p('.claude', 'skills', 'shoav', 'SKILL.md')));
  assert.ok(fs.existsSync(p('.claude', 'skills', 'shoav', 'scripts', 'semantic_normalizer.py')));
  assert.ok(!fs.existsSync(p('.claude', 'skills', 'shoav', 'README.md')), 'only SKILL.md and scripts are copied');
  assert.deepEqual(readJson(p('opencode.json')), {
    $schema: 'https://opencode.ai/config.json',
    mcp: { shoav: { type: 'remote', url: URL, enabled: true } },
  });
  assert.deepEqual(readJson(p('.agents', 'mcp_config.json')), { mcpServers: { shoav: { type: 'http', url: URL } } });
  assert.ok(fs.existsSync(p('.agents', 'skills', 'shoav', 'SKILL.md')));
  assert.deepEqual(readJson(p('.cursor', 'mcp.json')), { mcpServers: { shoav: { url: URL } } });
  assert.match(fs.readFileSync(p('.cursor', 'rules', 'shoav.mdc'), 'utf8'), /@\.cursor\/skills\/shoav\/SKILL\.md/);
  assert.ok(fs.existsSync(p('skills', 'shoav', 'SKILL.md')), 'generic skill');
  const agents = fs.readFileSync(p('AGENTS.md'), 'utf8');
  assert.equal(agents.split(START).length, 2, 'one block');
  assert.ok(agents.split('\n').length < 40);
  assert.match(agents, /Added by `shoav install`/);
  assert.match(agents, /Guard mode: enforce/);
  assert.match(r.stdout, /codex mcp add shoav --url http:\/\/127\.0\.0\.1:18500\/mcp/);
  assert.match(r.stdout, /best effort, verify with your Codex version/);
  assert.match(r.stdout, /"mcpServers"/, 'generic snippet printed');
  assert.match(r.stdout, /created\s+\.mcp\.json/);
  assert.ok(!fs.existsSync(path.join(t.home, '.claude')), 'project scope does not touch home');
});

test('second run is byte-identical and reports nothing written', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  assert.equal((await install(t)).code, 0);
  const first = snapshot(t.root);
  const r = await install(t);
  assert.equal(r.code, 0);
  assert.deepEqual(snapshot(t.root), first);
  assert.doesNotMatch(r.stdout, /\b(created|updated)\b/);
  assert.match(r.stdout, /already up to date/);
});

test('merges into existing JSON and keeps unrelated keys', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const mcp = path.join(t.project, '.mcp.json');
  fs.writeFileSync(mcp, JSON.stringify({ mcpServers: { other: { command: 'x' }, shoav: { type: 'http', url: 'http://old/mcp', headers: { A: 'b' } } }, extra: true }));
  fs.mkdirSync(path.join(t.project, '.claude'));
  fs.writeFileSync(path.join(t.project, '.claude', 'settings.json'), JSON.stringify({ permissions: { allow: ['Bash(ls)'], deny: ['Read(.env)'] }, model: 'x' }));
  fs.writeFileSync(path.join(t.project, 'opencode.json'), JSON.stringify({ $schema: 'custom', theme: 'dark' }));
  const r = await runCli(['install', '--what', 'mcp', '--agent', 'claude,opencode', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 0, r.stderr);
  assert.deepEqual(readJson(mcp), {
    mcpServers: { other: { command: 'x' }, shoav: { type: 'http', url: URL, headers: { A: 'b' } } },
    extra: true,
  });
  const s = readJson(path.join(t.project, '.claude', 'settings.json'));
  assert.deepEqual(s.permissions, { allow: ['Bash(ls)', 'mcp__shoav'], deny: ['Read(.env)'] });
  assert.equal(s.model, 'x');
  const o = readJson(path.join(t.project, 'opencode.json'));
  assert.equal(o.$schema, 'custom');
  assert.equal(o.theme, 'dark');
  assert.equal(o.mcp.shoav.url, URL);
  assert.match(r.stdout, /updated\s+\.mcp\.json/);
  assert.ok(!fs.existsSync(path.join(t.project, '.claude', 'skills')), '--what mcp installs no skill');
});

test('invalid JSON is left untouched and reported', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const file = path.join(t.project, 'opencode.json');
  const bad = '{\n  // comment\n  "mcp": {}\n}\n';
  fs.writeFileSync(file, bad);
  const r = await runCli(['install', '--what', 'mcp', '--agent', 'opencode', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 3);
  assert.equal(fs.readFileSync(file, 'utf8'), bad);
  assert.match(r.stdout, /skip\s+opencode\.json/);
  assert.match(r.stdout, /"remote"/, 'prints what to add');
});

test('BOM and CRLF files are merged without losing them', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  fs.mkdirSync(path.join(t.project, '.agents'));
  const file = path.join(t.project, '.agents', 'mcp_config.json');
  fs.writeFileSync(file, '﻿{\r\n  "mcpServers": {\r\n    "auto-browser": { "type": "http", "url": "http://127.0.0.1:18500/mcp" }\r\n  }\r\n}\r\n');
  const r = await runCli(['install', '--what', 'mcp', '--agent', 'agy', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 0, r.stderr);
  const raw = fs.readFileSync(file, 'utf8');
  assert.ok(raw.startsWith('﻿'));
  assert.ok(raw.includes('\r\n'));
  const j = readJson(file);
  assert.ok(j.mcpServers['auto-browser'], 'old key kept (never delete)');
  assert.equal(j.mcpServers.shoav.url, URL);
});

test('dry run writes nothing and prints the content', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const before = snapshot(t.root);
  const r = await install(t, ['--dry-run']);
  assert.equal(r.code, 0, r.stderr);
  assert.deepEqual(snapshot(t.root), before);
  assert.match(r.stdout, /would create\s+\.mcp\.json/);
  assert.match(r.stdout, /"mcp__shoav"/);
  assert.match(r.stdout, /shoav:start/);
});

test('AGENTS.md block is replaced, not duplicated, and outside text is kept', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const file = path.join(t.project, 'AGENTS.md');
  fs.writeFileSync(file, `# My rules\n\nBe nice.\n\n${START}\nold stuff http://old/mcp\n${END}\n\n## Footer\n`);
  fs.writeFileSync(path.join(t.project, 'CLAUDE.md'), '# Claude\n\n@AGENTS.md\n');
  const r = await runCli(['install', '--what', 'mcp', '--agent', 'claude,codex', '--dir', t.project, '--guard', 'observe', '--url', 'http://127.0.0.1:18551/mcp', '--yes'], t.env);
  assert.equal(r.code, 0, r.stderr);
  const text = fs.readFileSync(file, 'utf8');
  assert.equal(text.split(START).length, 2);
  assert.ok(text.startsWith('# My rules\n\nBe nice.\n\n<!-- shoav:start -->'));
  assert.ok(text.endsWith(`${END}\n\n## Footer\n`));
  assert.doesNotMatch(text, /old stuff/);
  assert.match(text, /18551\/mcp/);
  assert.match(text, /Guard mode: observe/);
  assert.equal(fs.readFileSync(path.join(t.project, 'CLAUDE.md'), 'utf8'), '# Claude\n\n@AGENTS.md\n', 'import not added twice');
});

test('upsertBlock and ensureImportLine unit behaviour', () => {
  const block = agentsBlock({ url: URL, guard: 'enforce' });
  const once = upsertBlock('# Title\n', block);
  assert.equal(upsertBlock(once, block), once);
  assert.equal(upsertBlock(null, block), `${block}\n`);
  const crlf = upsertBlock('a\r\n', block);
  assert.ok(!/[^\r]\n/.test(crlf), 'keeps CRLF');
  assert.equal(ensureImportLine(null), '@AGENTS.md\n');
  assert.equal(ensureImportLine('x'), 'x\n\n@AGENTS.md\n');
  assert.equal(ensureImportLine('x\n  @AGENTS.md  \n'), 'x\n  @AGENTS.md  \n');
});

test('user scope: claude prints the command, skills go under home, codex config only when absent', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const r = await runCli(['install', '--scope', 'user', '--what', 'both', '--agent', 'claude,opencode,agy,codex,cursor', '--yes'], t.env, { cwd: t.project });
  assert.equal(r.code, 0, r.stderr);
  const h = (...s) => path.join(t.home, ...s);
  assert.match(r.stdout, /claude mcp add --transport http --scope user shoav http:\/\/127\.0\.0\.1:18500\/mcp/);
  assert.ok(!fs.existsSync(h('.claude.json')), '~/.claude.json never edited');
  assert.ok(fs.existsSync(h('.claude', 'skills', 'shoav', 'SKILL.md')));
  assert.match(fs.readFileSync(h('.claude', 'CLAUDE.md'), 'utf8'), /Browsing with SHOAV/);
  assert.equal(readJson(h('.config', 'opencode', 'opencode.json')).mcp.shoav.type, 'remote');
  assert.ok(fs.existsSync(h('.gemini', 'config', 'skills', 'shoav', 'SKILL.md')));
  assert.equal(readJson(h('.gemini', 'config', 'mcp_config.json')).mcpServers.shoav.url, URL);
  assert.equal(fs.readFileSync(h('.codex', 'config.toml'), 'utf8'), `[mcp_servers.shoav]\nurl = "${URL}"\n`);
  assert.equal(readJson(h('.cursor', 'mcp.json')).mcpServers.shoav.url, URL);
  assert.deepEqual(fs.readdirSync(t.project), [], 'user scope does not write the project');

  // Existing codex config: printed, not edited.
  const toml = h('.codex', 'config.toml');
  fs.writeFileSync(toml, 'model = "x"\n');
  const r2 = await runCli(['install', '--scope', 'user', '--what', 'mcp', '--agent', 'codex', '--yes'], t.env, { cwd: t.project });
  assert.equal(r2.code, 0);
  assert.equal(fs.readFileSync(toml, 'utf8'), 'model = "x"\n');
  assert.match(r2.stdout, /\[mcp_servers\.shoav\]/);
});

test('--what skill only copies skills, no configs', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const r = await runCli(['install', '--what', 'skill', '--agent', 'claude,cursor', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 0, r.stderr);
  assert.ok(!fs.existsSync(path.join(t.project, '.mcp.json')));
  assert.ok(!fs.existsSync(path.join(t.project, 'AGENTS.md')));
  assert.ok(fs.existsSync(path.join(t.project, '.cursor', 'rules', 'shoav.mdc')));
  assert.ok(fs.existsSync(path.join(t.project, '.claude', 'skills', 'shoav', 'SKILL.md')));
});

test('changed skill source file is updated, extra user files are kept', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const dest = path.join(t.project, '.claude', 'skills', 'shoav');
  fs.mkdirSync(dest, { recursive: true });
  fs.writeFileSync(path.join(dest, 'SKILL.md'), 'stale');
  fs.writeFileSync(path.join(dest, 'mine.txt'), 'keep me');
  const r = await runCli(['install', '--what', 'skill', '--agent', 'claude', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 0);
  assert.notEqual(fs.readFileSync(path.join(dest, 'SKILL.md'), 'utf8'), 'stale');
  assert.equal(fs.readFileSync(path.join(dest, 'mine.txt'), 'utf8'), 'keep me');
  assert.match(r.stdout, /updated\s+\.claude\/skills\/shoav\/SKILL\.md/);
});

test('non-interactive install without --agent fails with a hint; bad url rejected', async (tt) => {
  const t = tempEnv();
  tt.after(t.cleanup);
  const r = await runCli(['install', '--dir', t.project, '--yes'], t.env);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /--agent/);
  const r2 = await runCli(['install', '--agent', 'claude', '--dir', t.project, '--url', 'ftp://x/mcp', '--yes'], t.env);
  assert.equal(r2.code, 2);
  assert.match(r2.stderr, /invalid --url/);
  assert.deepEqual(fs.readdirSync(t.project), []);
});
