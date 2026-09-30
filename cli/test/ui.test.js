// Live view UI build location and start-summary messaging.
// Regression for `npx github:vassu-v/SHOAV start --ui`: the package lands under
// ..._npx/<hash>/node_modules/shoav, and Next.js will not compile app sources
// inside node_modules (Turbopack panics, webpack reports "Module parse failed").
import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';
import { UI_MANUAL_HINT, insideNodeModules, liveViewNote, uiCopyReason } from '../src/server.js';

const NPX_WIN = 'C:\\Users\\u\\AppData\\Local\\npm-cache\\_npx\\bfdd30e389b6fc7d\\node_modules\\shoav\\server\\live-ui';
const NPX_POSIX = '/home/u/.npm/_npx/bfdd30e389b6fc7d/node_modules/shoav/server/live-ui';
const GLOBAL_POSIX = '/usr/local/lib/node_modules/shoav/server/live-ui';
const CLONE = path.join(path.sep, 'src', 'SHOAV', 'server', 'live-ui');

const always = () => true;
const never = () => false;

test('insideNodeModules spots npx and global installs, not a clone', () => {
  if (process.platform === 'win32') assert.equal(insideNodeModules(NPX_WIN), true);
  assert.equal(insideNodeModules(NPX_POSIX), true);
  assert.equal(insideNodeModules(GLOBAL_POSIX), true);
  assert.equal(insideNodeModules(CLONE), false);
  // A folder that merely contains the word is not node_modules.
  assert.equal(insideNodeModules(path.join(path.sep, 'src', 'my_node_modules_notes', 'live-ui')), false);
});

test('uiCopyReason forces a copy under node_modules even when writable', () => {
  assert.match(uiCopyReason(NPX_POSIX, always), /node_modules/);
  assert.match(uiCopyReason(GLOBAL_POSIX, never), /node_modules/);
  assert.match(uiCopyReason(CLONE, never), /read-only/);
  assert.equal(uiCopyReason(CLONE, always), null);
});

test('liveViewNote does not tell the user to add --ui when --ui was passed and failed', () => {
  assert.equal(liveViewNote({ requested: true, up: true }), '');
  assert.equal(liveViewNote({ requested: false, up: true }), '');
  const failed = liveViewNote({ requested: true, up: false });
  assert.doesNotMatch(failed, /add --ui/);
  assert.match(failed, /failed/);
  assert.match(liveViewNote({ requested: false, up: false }), /add --ui/);
});

test('UI failure hint gives a working manual fallback', () => {
  assert.match(UI_MANUAL_HINT, /git clone https:\/\/github\.com\/vassu-v\/SHOAV/);
  assert.match(UI_MANUAL_HINT, /server\/live-ui && npm install && npm run build && npm start/);
});
