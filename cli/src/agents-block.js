// The "Browsing with SHOAV" block written into AGENTS.md (or an agent's own
// instruction file) between fixed markers, replaced in place on re-install.
import { UI_BASE } from './paths.js';

export const START = '<!-- shoav:start -->';
export const END = '<!-- shoav:end -->';

const GUARD_TEXT = {
  off: 'off (no checks; start with `shoav start --guard enforce` to turn protection on)',
  observe: 'observe (verdicts are logged, results are not changed)',
  enforce: 'enforce (hostile content is rewritten, risky actions are blocked)',
};

export function agentsBlock({ url, guard }) {
  const lines = [
    START,
    '<!-- Added by `shoav install`. This block is replaced on the next install; edit outside the markers. -->',
    '## Browsing with SHOAV',
    '',
    'Use the `shoav` MCP server tools (`browser_create_session`, `browser_observe`, `browser_snapshot`,',
    '`browser_execute_action`, and the other `browser_*` tools) for ALL web browsing. Do not use any',
    'built-in browser, web fetch, or curl to read or act on web pages.',
    '',
    `- MCP server: \`shoav\` at ${url} (Streamable HTTP)`,
    `- Guard mode: ${GUARD_TEXT[guard] || guard}`,
    '',
    'Reading guard verdicts:',
    '- ALLOW: the result is unchanged.',
    '- REWRITE: continue on the cleaned content. The leading `_shoav` note says what was removed; do not try to recover it.',
    '- BLOCK or ESCALATE: the result has `isError: true`. Do NOT retry the same click or action.',
    '  Re-observe the page with `browser_observe` and pick a different, safe step, or stop and ask a human.',
    '',
    `Watch a session live: ${UI_BASE}/s/<session id> (the id comes from \`browser_create_session\`).`,
    'Give the user this link when a session starts.',
    '',
    'If the tools are missing or failing, run `shoav status` to check the server and `shoav start` to start it.',
    END,
  ];
  return lines.join('\n');
}

// Insert or replace the block. Keeps the file's line endings.
export function upsertBlock(existing, block) {
  const text = existing ?? '';
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const b = block.replace(/\r?\n/g, eol);
  const s = text.indexOf(START);
  const e = s >= 0 ? text.indexOf(END, s) : -1;
  if (s >= 0 && e >= 0) {
    return text.slice(0, s) + b + text.slice(e + END.length);
  }
  if (!text.trim()) return b + eol;
  const sep = text.endsWith(eol + eol) ? '' : text.endsWith(eol) ? eol : eol + eol;
  return text + sep + b + eol;
}

// Ensure a CLAUDE.md imports AGENTS.md exactly once.
export function ensureImportLine(existing, line = '@AGENTS.md') {
  if (existing === null || existing === undefined || !existing.trim()) return `${line}\n`;
  const re = new RegExp(`^\\s*${line.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`, 'm');
  if (re.test(existing)) return existing;
  const eol = existing.includes('\r\n') ? '\r\n' : '\n';
  const sep = existing.endsWith(eol + eol) ? '' : existing.endsWith(eol) ? eol : eol + eol;
  return existing + sep + line + eol;
}
