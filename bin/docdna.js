#!/usr/bin/env node
'use strict';

// Installs the docdna skill into supported coding-agent skill directories.
// Thin Node wrapper around install.sh so `npx @hxp-tools/docdna` works.

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const INSTALLER = path.join(ROOT, 'install.sh');
const PKG = require('../package.json');

const COLORS = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  cyan: '\x1b[36m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
};

function c(color, text) {
  return COLORS[color] + text + COLORS.reset;
}

function usage() {
  console.log(`
${c('bold', 'docdna')} ${c('dim', 'v' + PKG.version)}
Decide which documents a codebase owes. Citations or gaps. No third state.

${c('bold', 'Usage')}
  npx @hxp-tools/docdna@latest [all|claude|codex|cursor|windsurf]
  npx @hxp-tools/docdna@latest --help

${c('bold', 'Targets')}
  all        Install every registry-supported target (default)
  claude     Claude Code  (~/.claude/skills/docdna)
  codex      Codex        (~/.codex/skills/docdna)
  cursor     Cursor       (~/.cursor/skills/docdna)
  windsurf   Windsurf     (~/.codeium/windsurf/skills/docdna)

${c('bold', 'After install')}
  Restart your coding agent, then ask:
    survey the documentation for this repo

${c('bold', 'Requirements')}
  Python 3.8+ on a POSIX host. Windows is not supported.
`);
}

function main(argv) {
  const args = argv.slice(2);
  if (args.includes('--help') || args.includes('-h')) {
    usage();
    return 0;
  }
  if (args.includes('--version') || args.includes('-v')) {
    console.log(PKG.version);
    return 0;
  }

  if (process.platform === 'win32') {
    console.error(c('red', 'docdna does not support Windows.'));
    console.error('Python does not expose equivalent race-safe filesystem primitives there.');
    return 2;
  }

  if (!fs.existsSync(INSTALLER)) {
    console.error(c('red', 'install.sh missing from package.'));
    return 2;
  }

  const target = args[0] || 'all';
  console.log(c('cyan', 'docdna') + ' ' + c('dim', 'v' + PKG.version));
  console.log(c('dim', 'Installing skill into: ' + target));
  console.log('');

  const result = spawnSync('sh', [INSTALLER, target], {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
  });

  if (result.error) {
    console.error(c('red', String(result.error.message || result.error)));
    return 1;
  }
  if (result.status === 0) {
    console.log('');
    console.log(c('green', 'Next: restart your agent, then ask it to survey the documentation.'));
    console.log(c('dim', 'Docs: ' + (PKG.homepage || 'https://github.com/hannsxpeter/docdna')));
  }
  return result.status == null ? 1 : result.status;
}

process.exitCode = main(process.argv);
