import { CliError } from './ui.js';

// Accept only a plain http(s) URL whose path ends with /mcp. No credentials,
// query, fragment, whitespace or control characters.
export function validateMcpUrl(input) {
  const raw = String(input ?? '').trim();
  const bad = (why) => new CliError(`invalid --url "${raw.slice(0, 200)}": ${why}. Example: http://127.0.0.1:18500/mcp`, 2);
  if (!raw) throw bad('empty');
  if (/[\s\x00-\x1f\x7f"'<>`\\]/.test(raw)) throw bad('contains spaces, quotes or control characters');
  let u;
  try {
    u = new URL(raw);
  } catch {
    throw bad('not a URL');
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') throw bad('must start with http:// or https://');
  if (u.username || u.password) throw bad('must not contain credentials');
  if (!u.hostname) throw bad('missing host');
  if (u.search || u.hash || raw.includes('?') || raw.includes('#')) throw bad('must not have a query or fragment');
  if (!u.pathname.endsWith('/mcp')) throw bad('path must end with /mcp');
  return u.href;
}
