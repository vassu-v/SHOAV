// Terminal output helpers: colors (NO_COLOR aware), banner, small log helpers.

export const TAGLINE = 'AI Bodyguard for agents that browse';

export function colorEnabled(stream = process.stdout, env = process.env) {
  if (env.NO_COLOR !== undefined && env.NO_COLOR !== '') return false;
  if (env.FORCE_COLOR && env.FORCE_COLOR !== '0') return true;
  return Boolean(stream && stream.isTTY);
}

function wrap(code) {
  return (text) => (colorEnabled() ? `\x1b[${code}m${text}\x1b[0m` : String(text));
}

export const c = {
  bold: wrap('1'),
  dim: wrap('2'),
  red: wrap('31'),
  green: wrap('32'),
  yellow: wrap('33'),
  blue: wrap('34'),
  cyan: wrap('36'),
};

const BANNER_LINES = [
  '  ____  _   _  ___    _    __     __',
  ' / ___|| | | |/ _ \\  / \\   \\ \\   / /',
  ' \\___ \\| |_| | | | |/ _ \\   \\ \\ / / ',
  '  ___) |  _  | |_| / ___ \\   \\ V /  ',
  ' |____/|_| |_|\\___/_/   \\_\\   \\_/   ',
];

export function banner() {
  return `${c.cyan(BANNER_LINES.join('\n'))}\n ${c.bold('S.H.O.A.V.')}  ${c.dim(TAGLINE)}\n`;
}

export function printBanner() {
  process.stdout.write(`${banner()}\n`);
}

export const log = {
  info: (msg = '') => process.stdout.write(`${msg}\n`),
  step: (msg) => process.stdout.write(`${c.blue('>')} ${msg}\n`),
  ok: (msg) => process.stdout.write(`${c.green('ok')}   ${msg}\n`),
  warn: (msg) => process.stdout.write(`${c.yellow('warn')} ${msg}\n`),
  fail: (msg) => process.stdout.write(`${c.red('fail')} ${msg}\n`),
  error: (msg) => process.stderr.write(`${c.red('error:')} ${msg}\n`),
};

export class CliError extends Error {
  constructor(message, code = 1) {
    super(message);
    this.exitCode = code;
  }
}
