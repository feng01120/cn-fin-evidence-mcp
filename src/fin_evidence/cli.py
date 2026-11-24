# -*- coding: utf-8 -*-
"""命令行入口：构建数据集、检查结果、启动 MCP Server。"""

import argparse
import json
import os
from pathlib import Path

from .extract import build_dataset, snippet_hit_rate
from .mapping import METRICS, REQUIRED_METRICS
from .models import Company
from .ratios import compute_ratios, run_checks
from .store import list_datasets, load_dataset, save_dataset


def cmd_build(args):
    company = Company(code=args.code, name=args.name, short_name=args.short_name or args.name)
    facts, rows, meta = build_dataset(
        args.pdf, company, args.period,
        report_date=args.report_date or ('%s-12-31' % args.period),
        announce_date=args.announce_date or '',
        source_url=args.source_url or None,
    )
    ratios = compute_ratios(company, args.period, facts)
    checks = run_checks(facts)
    passed = sum(1 for c in checks if c.status == 'pass')
    failed = sum(1 for c in checks if c.status == 'fail')
    expected = [m.key for m in METRICS if m.key in REQUIRED_METRICS]
    present = [f.metric for f in facts if f.value is not None]
    metric_cov = round(len(set(present) & set(expected)) / max(1, len(expected)), 4)
    snippet_rate = snippet_hit_rate(args.pdf, facts)
    meta.coverage = {
        'metric_coverage': metric_cov,
        'fact_count': len(facts),
        'expected_metrics': len(expected),
        'snippet_hit_rate': snippet_rate,
        'check_pass_rate': round(passed / len(checks), 4) if checks else 0.0,
        'check_fail': failed,
        'missing_required': sorted(set(expected) - set(present)),
    }
    meta.coverage['score'] = round((metric_cov + snippet_rate + meta.coverage['check_pass_rate']) / 3, 4)
    meta.coverage_score = meta.coverage['score']
    if failed or metric_cov < 0.8 or snippet_rate < 0.95:
        meta.quality_gate = 'fail'
    elif metric_cov < 0.95:
        meta.quality_gate = 'warning'
    else:
        meta.quality_gate = 'pass'
    out = save_dataset(Path(args.data), facts, rows, meta, ratios, checks)
    fails = [c for c in checks if c.status == 'fail']
    print(json.dumps({
        'dataset': str(out), 'facts': len(facts), 'rows': len(rows), 'ratios': len(ratios),
        'checks': {'pass': sum(1 for c in checks if c.status == 'pass'),
                   'warning': sum(1 for c in checks if c.status == 'warning'),
                   'fail': len(fails)},
        'coverage': meta.coverage,
        'missing_metrics': [m.name for m in METRICS if m.key not in set(present)],
        'quality_gate': meta.quality_gate,
        'failed_checks': [{'check': c.check, 'detail': c.detail, 'diff': c.diff} for c in fails],
    }, ensure_ascii=False, indent=2))
    return 0 if meta.quality_gate in ('pass', 'warning') and not fails else 1


def cmd_inspect(args):
    ds = load_dataset(Path(args.data), args.code, args.period)
    for f in ds['facts']:
        print('%-28s %-22s %18s  第%s页  %s' % (
            f['metric'], f['metric_name'],
            ('%.2f' % f['value']) if f['value'] is not None else '缺失',
            f['page'], f['snippet'][:60]))
    print('\n--- 比率 ---')
    for r in ds['ratios']:
        print('%-22s %10s %s' % (r['name'], ('%.2f' % r['value']) if r['value'] is not None else '缺失', r['unit']))
    print('\n--- 校验 ---')
    for c in ds['checks']:
        print('[%s] %s: %s' % (c['status'], c['check'], c['detail']))


def cmd_list(args):
    print(json.dumps(list_datasets(Path(args.data)), ensure_ascii=False, indent=2))


def cmd_demo(args):
    from .demo import main as demo_main
    return demo_main()


def cmd_serve(args):
    data_path = Path(args.data)
    if data_path.exists():
        os.environ['FIN_EVIDENCE_DATA'] = str(data_path.resolve())
    from .server import main
    main()


def main():
    ap = argparse.ArgumentParser(prog='fin-evidence', description='A 股财报证据链 MCP')
    ap.add_argument('--data', default='data', help='数据集目录，默认 ./data')
    sub = ap.add_subparsers(dest='cmd', required=True)

    b = sub.add_parser('build', help='从年报 PDF 构建数据集')
    b.add_argument('--pdf', required=True)
    b.add_argument('--code', required=True)
    b.add_argument('--name', required=True)
    b.add_argument('--short-name', default='')
    b.add_argument('--period', required=True)
    b.add_argument('--report-date', default='', help='报告期末，如 2025-12-31；默认 <period>-12-31')
    b.add_argument('--announce-date', default='', help='公告披露日，如 2026-04-17')
    b.add_argument('--source-url', default='', help='年报原始链接')
    b.set_defaults(func=cmd_build)

    i = sub.add_parser('inspect', help='查看已构建的数据')
    i.add_argument('--code', required=True)
    i.add_argument('--period', required=True)
    i.set_defaults(func=cmd_inspect)

    l = sub.add_parser('list', help='列出数据集')
    l.set_defaults(func=cmd_list)

    d = sub.add_parser('demo', help='30 秒证据链演示（无需 PDF）')
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser('serve', help='启动 MCP Server（stdio）')
    s.set_defaults(func=cmd_serve)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == '__main__':
    raise SystemExit(main())
