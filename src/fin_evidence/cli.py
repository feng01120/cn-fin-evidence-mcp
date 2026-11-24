# -*- coding: utf-8 -*-
"""命令行入口：构建数据集、检查结果、启动 MCP Server。"""

import argparse
import json
from pathlib import Path

from .extract import build_dataset
from .models import Company
from .ratios import compute_ratios, run_checks
from .store import list_datasets, load_dataset, save_dataset


def cmd_build(args):
    company = Company(code=args.code, name=args.name, short_name=args.short_name or args.name)
    facts, rows, meta = build_dataset(args.pdf, company, args.period)
    ratios = compute_ratios(company, args.period, facts)
    checks = run_checks(facts)
    out = save_dataset(Path(args.data), facts, rows, meta, ratios, checks)
    fails = [c for c in checks if c.status == 'fail']
    print(json.dumps({
        'dataset': str(out), 'facts': len(facts), 'rows': len(rows), 'ratios': len(ratios),
        'checks': {'pass': sum(1 for c in checks if c.status == 'pass'),
                   'warning': sum(1 for c in checks if c.status == 'warning'),
                   'fail': len(fails)},
        'missing_metrics': [f.metric_name for f in facts if f.value is None],
        'failed_checks': [{'check': c.check, 'detail': c.detail, 'diff': c.diff} for c in fails],
    }, ensure_ascii=False, indent=2))
    return 0 if not fails else 1


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


def cmd_serve(args):
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
    b.set_defaults(func=cmd_build)

    i = sub.add_parser('inspect', help='查看已构建的数据')
    i.add_argument('--code', required=True)
    i.add_argument('--period', required=True)
    i.set_defaults(func=cmd_inspect)

    l = sub.add_parser('list', help='列出数据集')
    l.set_defaults(func=cmd_list)

    s = sub.add_parser('serve', help='启动 MCP Server（stdio）')
    s.set_defaults(func=cmd_serve)

    args = ap.parse_args()
    return args.func(args) or 0


if __name__ == '__main__':
    raise SystemExit(main())
