// Entry for `node --test cli/test`. Node 18/20 treat a directory argument as a
// directory and run every *.test.js on their own (argv[1] is then this file and
// this module does nothing). Node 21+ resolve the argument as a module, which
// lands here, so load every *.test.js from this folder.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const entry = process.argv[1] ? path.resolve(process.argv[1]) : '';

if (entry !== fileURLToPath(import.meta.url)) {
  for (const f of fs.readdirSync(here).filter((n) => n.endsWith('.test.js')).sort()) {
    await import(pathToFileURL(path.join(here, f)).href);
  }
}
