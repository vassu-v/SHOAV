import fs from 'node:fs';
import path from 'node:path';
import { parseArgs } from './args.js';
import { runDoctor } from './doctor.js';
import { HELP } from './help.js';
import { runInstall } from './install.js';
import { PKG_ROOT } from './paths.js';
import { runEvents, runOpen, runStart, runStatus, runStop } from './server.js';

export function version() {
  return JSON.parse(fs.readFileSync(path.join(PKG_ROOT, 'package.json'), 'utf8')).version;
}

const RUN = {
  install: runInstall,
  start: runStart,
  stop: runStop,
  status: runStatus,
  events: runEvents,
  open: runOpen,
  doctor: runDoctor,
};

export async function main(argv) {
  const [major] = process.versions.node.split('.').map(Number);
  if (major < 18) {
    process.stderr.write(`shoav needs Node.js 18 or newer (this is ${process.versions.node}).\n`);
    return 1;
  }
  const parsed = parseArgs(argv);
  if (parsed.version) {
    process.stdout.write(`${version()}\n`);
    return 0;
  }
  if (parsed.help) {
    const explicit = argv.find((a) => RUN[a]);
    process.stdout.write(explicit ? HELP[explicit] : HELP.main);
    return 0;
  }
  return RUN[parsed.command](parsed);
}
