#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const sourceSkillDir = path.resolve(__dirname, '..', 'skill');

const homedir = os.homedir();
const cwd = process.cwd();

const TARGET_PRESETS = {
  antigravity: path.join(homedir, '.gemini', 'config', 'skills', 'SHOAV_SKILLforAGENTS'),
  agy: path.join(homedir, '.gemini', 'config', 'skills', 'SHOAV_SKILLforAGENTS'),
  claude: path.join(cwd, '.claude', 'skills', 'SHOAV_SKILLforAGENTS'),
  cursor: path.join(cwd, '.cursor', 'skills', 'SHOAV_SKILLforAGENTS'),
  local: path.join(cwd, 'skills', 'SHOAV_SKILLforAGENTS'),
};

function printHelp() {
  console.log(`
\x1b[36mS.H.O.A.V. Skill Installer\x1b[0m
Shield for Hostile Operations & Agent Vulnerability

Usage:
  npx shoav-skill [command] [options]

Commands:
  install (default)   Install the skill into your agent's skills directory

Options:
  --target <agent>    Target agent preset:
                        - antigravity / agy (default: ~/.gemini/config/skills/SHOAV_SKILLforAGENTS)
                        - claude            (./.claude/skills/SHOAV_SKILLforAGENTS)
                        - cursor            (./.cursor/skills/SHOAV_SKILLforAGENTS)
                        - local             (./skills/SHOAV_SKILLforAGENTS)
  --dir <path>        Custom destination directory
  --help, -h          Show this help message
`);
}

function copyRecursiveSync(src, dest) {
  const exists = fs.existsSync(src);
  const stats = exists && fs.statSync(src);
  const isDirectory = exists && stats.isDirectory();
  if (isDirectory) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    fs.readdirSync(src).forEach((childItemName) => {
      copyRecursiveSync(path.join(src, childItemName), path.join(dest, childItemName));
    });
  } else {
    fs.copyFileSync(src, dest);
  }
}

function run() {
  const args = process.argv.slice(2);

  if (args.includes('--help') || args.includes('-h')) {
    printHelp();
    process.exit(0);
  }

  let targetPreset = 'antigravity';
  let customDir = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--target' && args[i + 1]) {
      targetPreset = args[i + 1].toLowerCase();
      i++;
    } else if (args[i] === '--dir' && args[i + 1]) {
      customDir = args[i + 1];
      i++;
    }
  }

  if (!customDir && !TARGET_PRESETS[targetPreset]) {
    console.error(`\x1b[31m✖ Unknown target preset: "${targetPreset}".\x1b[0m`);
    console.error(`Supported presets: ${Object.keys(TARGET_PRESETS).join(', ')}`);
    process.exit(1);
  }

  let destDir = customDir
    ? path.resolve(cwd, customDir)
    : TARGET_PRESETS[targetPreset];

  console.log(`\n\x1b[34m[S.H.O.A.V.]\x1b[0m Installing agent skill...`);
  console.log(`  Source:      ${sourceSkillDir}`);
  console.log(`  Destination: ${destDir}`);

  try {
    copyRecursiveSync(sourceSkillDir, destDir);
    console.log(`\x1b[32m✔ Successfully installed S.H.O.A.V. skill to:\x1b[0m\n  ${destDir}\n`);
    console.log(`Your autonomous agent can now access SHOAV_SKILLforAGENTS.`);
  } catch (err) {
    console.error(`\x1b[31m✖ Failed to copy skill files:\x1b[0m`, err.message);
    process.exit(1);
  }
}

run();
