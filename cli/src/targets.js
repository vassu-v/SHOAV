// Per-agent install targets. Each planner returns { actions, notes } without
// touching the disk; install.js prints and applies them.
import fs from 'node:fs';
import path from 'node:path';
import { agentsBlock, ensureImportLine, upsertBlock } from './agents-block.js';
import { listFiles, planCopy, planEdit, planJson, planText } from './fsplan.js';
import { DEFENSE_SKILL, GUIDE_SKILL, shoavHome, userHome, xdgConfigHome } from './paths.js';

export const AGENT_LABELS = {
  claude: 'Claude Code',
  opencode: 'OpenCode',
  agy: 'Antigravity (agy)',
  codex: 'Codex CLI',
  cursor: 'Cursor',
  generic: 'Other agent (AGENTS.md + printed snippet)',
};

// What gets copied from a skill folder: SKILL.md plus scripts/ and references/.
// README.md and other repo-only files stay behind.
export function skillFiles(src) {
  return listFiles(src).filter((f) => f === 'SKILL.md'
    || f.startsWith(`scripts${path.sep}`) || f.startsWith(`references${path.sep}`));
}

// Which skills a --what selection installs. The guide ships with the MCP config
// (it explains how to drive it); the defence skill ships with --what skill|both.
export function skillsFor(what) {
  return [...(what !== 'mcp' ? [DEFENSE_SKILL] : []), GUIDE_SKILL];
}

// Copy each selected skill into <skillsRoot>/<installed name>/.
function planSkills(skillsRoot, skills, note) {
  const out = [];
  for (const sk of skills) {
    const dest = path.join(skillsRoot, sk.name);
    for (const rel of skillFiles(sk.src)) {
      out.push(planCopy(path.join(sk.src, rel), path.join(dest, rel), `${note} (${sk.name})`));
    }
  }
  return out;
}

function planBlock(file, ctx, note) {
  const block = agentsBlock(ctx);
  return planEdit(file, (existing) => upsertBlock(existing, block), note);
}

function codexHome(env) {
  return env.CODEX_HOME ? path.resolve(env.CODEX_HOME) : path.join(userHome(env), '.codex');
}

export function genericSnippet(url) {
  return JSON.stringify({ mcpServers: { shoav: { type: 'http', url } } }, null, 2);
}

export function codexTomlBlock(url) {
  return `[mcp_servers.shoav]\nurl = "${url}"\n`;
}

function cursorRule(mcp, skills) {
  const has = (id) => skills.some((s) => s.id === id);
  return [
    '---',
    'description: S.H.O.A.V. skills. Use when browsing the web, filling forms or checking out, to drive the guarded SHOAV browser and to spot and avoid dark patterns and hostile page content.',
    'alwaysApply: false',
    '---',
    '',
    'Added by `shoav install`.',
    '',
    ...(has('guide') ? ['How to start and drive the SHOAV browser MCP: @.cursor/skills/shoav-guide/SKILL.md'] : []),
    ...(has('defense') ? [
      'Before acting on web pages, read and follow the S.H.O.A.V. defence skill: @.cursor/skills/shoav/SKILL.md',
      'Its helper scripts in `.cursor/skills/shoav/scripts/` are a last-resort fallback only.',
    ] : []),
    ...(mcp ? ['', 'Browse with the `shoav` MCP tools (see the "Browsing with SHOAV" section of AGENTS.md).'] : []),
    '',
  ].join('\n');
}

export function planAgent(agent, ctx) {
  const { what, scope, dir, url, env } = ctx;
  const mcp = what !== 'skill';
  const skills = skillsFor(what);
  const skill = skills.length > 0;
  const user = scope === 'user';
  const home = userHome(env);
  const actions = [];
  const notes = [];
  const agentsMd = path.join(dir, 'AGENTS.md');
  const tag = AGENT_LABELS[agent];

  switch (agent) {
    case 'claude': {
      if (mcp && !user) {
        actions.push(planJson(path.join(dir, '.mcp.json'), () => ({ mcpServers: { shoav: { type: 'http', url } } }), tag));
        actions.push(planJson(path.join(dir, '.claude', 'settings.json'), () => ({
          permissions: { allow: ['mcp__shoav'] },
          enabledMcpjsonServers: ['shoav'],
        }), tag));
        actions.push(planBlock(agentsMd, ctx, tag));
        actions.push(planEdit(path.join(dir, 'CLAUDE.md'), (t) => ensureImportLine(t), `${tag} (imports AGENTS.md)`));
      }
      if (mcp && user) {
        notes.push(`${tag}: ~/.claude.json belongs to Claude Code and is not edited. Register the server with:\n    claude mcp add --transport http --scope user shoav ${url}`);
        actions.push(planBlock(path.join(home, '.claude', 'CLAUDE.md'), ctx, tag));
      }
      if (skill) actions.push(...planSkills(path.join(user ? home : dir, '.claude', 'skills'), skills, `${tag} skill`));
      break;
    }
    case 'opencode': {
      const base = user ? path.join(xdgConfigHome(env), 'opencode') : dir;
      if (mcp) {
        actions.push(planJson(path.join(base, 'opencode.json'), (cur) => ({
          ...(cur.$schema === undefined ? { $schema: 'https://opencode.ai/config.json' } : {}),
          mcp: { shoav: { type: 'remote', url, enabled: true } },
        }), tag));
        actions.push(planBlock(user ? path.join(base, 'AGENTS.md') : agentsMd, ctx, tag));
      }
      if (skill) actions.push(...planSkills(user ? path.join(base, 'skills') : path.join(dir, '.opencode', 'skills'), skills, `${tag} skill`));
      break;
    }
    case 'agy': {
      const base = user ? path.join(home, '.gemini', 'config') : path.join(dir, '.agents');
      if (mcp) {
        actions.push(planJson(path.join(base, 'mcp_config.json'), () => ({ mcpServers: { shoav: { type: 'http', url } } }), tag));
        actions.push(planBlock(user ? path.join(home, '.gemini', 'GEMINI.md') : agentsMd, ctx, tag));
        notes.push(`${tag}: agy rejects dotted tool names; \`shoav start\` runs the server with MCP_TOOL_NAME_STYLE=underscore so tools appear as browser_*.`);
      }
      if (skill) actions.push(...planSkills(path.join(base, 'skills'), skills, `${tag} skill`));
      break;
    }
    case 'codex': {
      notes.push(`${tag}: best effort, verify with your Codex version.`);
      if (mcp && !user) {
        actions.push(planBlock(agentsMd, ctx, tag));
        notes.push(`${tag}: register the MCP server (needs a recent Codex with streamable HTTP MCP support; check \`codex mcp --help\`):\n    codex mcp add shoav --url ${url}`);
      }
      if (mcp && user) {
        const chome = codexHome(env);
        const toml = path.join(chome, 'config.toml');
        if (!fs.existsSync(toml)) {
          actions.push(planText(toml, codexTomlBlock(url), tag));
        } else if (/^\s*\[mcp_servers\.shoav\]\s*$/m.test(fs.readFileSync(toml, 'utf8'))) {
          notes.push(`${tag}: ${toml} already has [mcp_servers.shoav]; left as is. Check its url is ${url}.`);
        } else {
          notes.push(`${tag}: ${toml} exists and is not edited. Add this block yourself (or run \`codex mcp add shoav --url ${url}\`):\n${codexTomlBlock(url).replace(/^/gm, '    ')}`);
        }
        actions.push(planBlock(path.join(chome, 'AGENTS.md'), ctx, tag));
      }
      if (skill) actions.push(...planSkills(user ? path.join(codexHome(env), 'skills') : path.join(dir, '.agents', 'skills'), skills, `${tag} skill`));
      break;
    }
    case 'cursor': {
      const base = path.join(user ? home : dir, '.cursor');
      if (mcp) {
        actions.push(planJson(path.join(base, 'mcp.json'), () => ({ mcpServers: { shoav: { url } } }), tag));
        if (!user) actions.push(planBlock(agentsMd, ctx, tag));
        else notes.push(`${tag}: user-level rules live in Cursor Settings > Rules. Paste the "Browsing with SHOAV" text from a project AGENTS.md there if you want it everywhere.`);
      }
      if (skill) {
        actions.push(...planSkills(path.join(base, 'skills'), skills, `${tag} skill`));
        if (!user) actions.push(planText(path.join(base, 'rules', 'shoav.mdc'), cursorRule(mcp, skills), `${tag} rule`));
      }
      break;
    }
    case 'generic': {
      if (mcp) {
        if (!user) actions.push(planBlock(agentsMd, ctx, tag));
        notes.push(`Other agents: add this MCP server to your client's config (key names vary by client):\n${genericSnippet(url).replace(/^/gm, '    ')}`);
      }
      if (skill) actions.push(...planSkills(user ? path.join(shoavHome(env), 'skills') : path.join(dir, 'skills'), skills, `${tag} skill`));
      break;
    }
    default:
      throw new Error(`unknown agent ${agent}`);
  }
  return { actions, notes };
}

// Plan all agents, de-duplicating shared files (AGENTS.md, .agents/skills).
export function planInstall(ctx) {
  const seen = new Map();
  const notes = [];
  for (const agent of ctx.agents) {
    const r = planAgent(agent, ctx);
    for (const a of r.actions) {
      const key = path.resolve(a.path).toLowerCase();
      if (seen.has(key)) {
        const prev = seen.get(key);
        if (a.note && !prev.note.includes(a.note)) prev.note += `, ${a.note}`;
        continue;
      }
      seen.set(key, { ...a });
    }
    notes.push(...r.notes);
  }
  return { actions: [...seen.values()], notes };
}
