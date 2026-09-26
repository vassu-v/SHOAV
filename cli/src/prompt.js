// Tiny line-based prompts (no raw mode, works in any TTY).
import readline from 'node:readline';
import { c } from './ui.js';

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

export async function confirm(question, def = true) {
  const a = (await ask(`${question} ${def ? '[Y/n]' : '[y/N]'} `)).toLowerCase();
  if (!a) return def;
  return a === 'y' || a === 'yes';
}

// Single choice. options: [{value,label}]; returns value.
export async function choose(question, options, defIndex = 0) {
  process.stdout.write(`${question}\n`);
  options.forEach((o, i) => process.stdout.write(`  ${i + 1}) ${o.label}${i === defIndex ? c.dim(' (default)') : ''}\n`));
  for (;;) {
    const a = await ask(`Choose 1-${options.length}: `);
    if (!a) return options[defIndex].value;
    const n = Number(a);
    if (Number.isInteger(n) && n >= 1 && n <= options.length) return options[n - 1].value;
    process.stdout.write('Please type a number from the list.\n');
  }
}

// Multi choice: comma separated numbers. Returns array of values.
export async function chooseMany(question, options) {
  process.stdout.write(`${question}\n`);
  options.forEach((o, i) => process.stdout.write(`  ${i + 1}) ${o.label}\n`));
  for (;;) {
    const a = await ask('Choose one or more, comma separated (for example 1,3): ');
    const picks = a.split(/[\s,]+/).filter(Boolean).map(Number);
    if (picks.length && picks.every((n) => Number.isInteger(n) && n >= 1 && n <= options.length)) {
      return [...new Set(picks)].map((n) => options[n - 1].value);
    }
    process.stdout.write('Please type numbers from the list.\n');
  }
}
