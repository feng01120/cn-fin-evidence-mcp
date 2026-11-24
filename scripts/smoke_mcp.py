# -*- coding: utf-8 -*-
"""MCP stdio 冒烟测试：initialize -> tools/list -> get_evidence -> verify_fact。

优先使用已安装的 `fin-evidence` 命令；没有时退回 `python -m fin_evidence.server`。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def send(proc, payload):
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
    proc.stdin.flush()


def read_one(proc, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        if proc.poll() is not None:
            raise RuntimeError('server exited: %s' % (proc.stderr.read()[-2000:]))
    raise TimeoutError('no JSON-RPC response')


def call(proc, msg_id, method, params=None):
    payload = {'jsonrpc': '2.0', 'id': msg_id, 'method': method}
    if params is not None:
        payload['params'] = params
    send(proc, payload)
    return read_one(proc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=str(ROOT / 'data'))
    args = parser.parse_args()
    entry = shutil.which('fin-evidence')
    if entry:
        cmd = [entry, '--data', args.data, 'serve']
        env = dict(os.environ)
    else:
        cmd = [sys.executable, '-m', 'fin_evidence.server']
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        if Path(args.data).exists():
            env['FIN_EVIDENCE_DATA'] = str(Path(args.data).resolve())
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            bufsize=1)
    try:
        init = call(proc, 1, 'initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'release-smoke', 'version': '0.0.1'},
        })
        if 'result' not in init:
            raise RuntimeError('initialize failed: %s' % init)
        send(proc, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = call(proc, 2, 'tools/list')
        names = [t.get('name') for t in tools.get('result', {}).get('tools', [])]
        for expected in ('get_evidence', 'verify_fact', 'get_source_comparison'):
            if expected not in names:
                raise RuntimeError('missing tool: %s' % expected)
        evidence = call(proc, 3, 'tools/call', {
            'name': 'get_evidence',
            'arguments': {'stock_code': '601088', 'period': '2025',
                          'metric': 'total_assets'},
        })
        text = json.dumps(evidence, ensure_ascii=False)
        if '601088-2025-total_assets' not in text or '627761' not in text:
            raise RuntimeError('evidence call did not return the expected fact: %s' % text[:1000])
        restated = call(proc, 4, 'tools/call', {
            'name': 'verify_fact',
            'arguments': {'stock_code': '601088', 'period': '2025',
                          'metric': 'total_assets', 'claimed_value': 903830},
        })
        if 'restatement_match' not in json.dumps(restated, ensure_ascii=False):
            raise RuntimeError('verify_fact did not mark the restated claim')
        print(json.dumps({'tools': names, 'evidence_ok': True, 'restatement_ok': True},
                         ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.kill()


if __name__ == '__main__':
    raise SystemExit(main())
