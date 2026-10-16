#!/usr/bin/env node
'use strict';
const {spawn, spawnSync} = require('node:child_process');
const path = require('node:path');

function resolvePythonLauncher() {
  if (process.env.DREAMPIA_PYTHON && process.env.DREAMPIA_PYTHON.trim()) {
    return {cmd: process.env.DREAMPIA_PYTHON.trim(), prefixArgs: []};
  }
  const candidates = [
    {cmd: 'python3', prefixArgs: []},
    {cmd: 'python', prefixArgs: []},
    {cmd: 'py', prefixArgs: ['-3']},
  ];
  for (const cand of candidates) {
    const probe = spawnSync(
      cand.cmd,
      [...cand.prefixArgs, '-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'],
      {stdio: 'ignore'}
    );
    if (!probe.error && probe.status === 0) {
      return cand;
    }
  }
  return {cmd: 'python3', prefixArgs: []};
}

const launcher = resolvePythonLauncher();
const args = process.argv.slice(2);
const workflow = args[0] === 'workflow';
const target = path.join(__dirname, '..', 'harness', workflow ? 'workflow_runner.py' : 'team_cli.py');
const child = spawn(launcher.cmd, [...launcher.prefixArgs, target, ...(workflow ? args.slice(1) : args)], {stdio:'inherit'});
child.on('error', () => { console.error('dreampia requires Python >=3.9; set DREAMPIA_PYTHON to an installed interpreter.'); process.exitCode=2; });
child.on('exit', (code, signal) => { process.exitCode = signal ? 130 : code; });
for (const signal of ['SIGINT','SIGTERM']) process.on(signal, () => { if (!child.killed) child.kill(signal); });

