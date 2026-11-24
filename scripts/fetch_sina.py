# -*- coding: utf-8 -*-
"""为 verified 数据集补新浪财经第二结构化源，并生成三源比对。

新浪只用于交叉核对：不覆盖 verified，不进入 fallback。抓取失败记录
no_data，不编造任何数值。
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fin_evidence.sina import build_comparison, fetch_metrics  # noqa: E402
from fin_evidence.store import list_datasets, load_dataset  # noqa: E402

DATA = ROOT / 'data'
KEYS = ('pass', 'restatement', 'restatement_material', 'verified_isolated',
        'warning', 'unverified', 'missing')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='', help='逗号分隔股票代码')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--sleep', type=float, default=0.15)
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()

    codes = {x.strip() for x in args.only.split(',') if x.strip()}
    datasets = list_datasets(DATA)
    if codes:
        datasets = [d for d in datasets if d['code'] in codes]
    if args.limit:
        datasets = datasets[:args.limit]

    records = []
    for ds in datasets:
        d = Path(ds['path'])
        out = d / 'sina.json'
        if out.exists() and not args.overwrite:
            records.append({'code': ds['code'], 'period': ds['period'], 'status': 'skipped'})
            continue
        report_date = ds.get('report_date') or ('%s-12-31' % ds['period'])
        fetched = fetch_metrics(ds['code'], report_date)
        if not fetched.get('metrics'):
            records.append({'code': ds['code'], 'period': ds['period'],
                            'report_date': report_date, 'status': 'no_data',
                            'errors': fetched.get('errors', [])})
            print(json.dumps(records[-1], ensure_ascii=False))
            continue
        verified = load_dataset(DATA, ds['code'], ds['period'], ds.get('announce_date', ''))
        comp = build_comparison(verified['facts'], verified.get('structured', {}), fetched,
                                ds.get('announce_date', ''))
        doc = {
            'provider': 'sina',
            'fetched_at': fetched['fetched_at'],
            'company': ds.get('company', {}),
            'report_date': report_date,
            'announce_date': ds.get('announce_date', ''),
            'metrics': fetched['metrics'],
            'comparison': comp['rows'],
            'cross_check': comp['cross_check'],
            'errors': comp['errors'],
        }
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
        rec = {'code': ds['code'], 'period': ds['period'], 'status': 'ok',
               'metric_count': len(fetched['metrics']),
               'cross_check': comp['cross_check'],
               'errors': comp['errors']}
        records.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        time.sleep(max(0.0, args.sleep))

    report_path = DATA / 'second_source_report.json'
    old_records = []
    if report_path.exists():
        old_records = (json.loads(report_path.read_text(encoding='utf-8')) or {}).get('records', [])
    if args.only:
        only = {x.strip() for x in args.only.split(',') if x.strip()}
        old_records = [r for r in old_records if r.get('code') not in only]
    else:
        old_records = []
    merged = old_records + records
    merged.sort(key=lambda r: (r.get('code', ''), r.get('period', '')))
    summary = {
        'datasets': len(merged),
        'ok': sum(1 for r in merged if r['status'] == 'ok'),
        'skipped': sum(1 for r in merged if r['status'] == 'skipped'),
        'no_data': sum(1 for r in merged if r['status'] == 'no_data'),
        'metrics': sum(r.get('metric_count', 0) for r in merged),
        'cross_check': {k: sum(r.get('cross_check', {}).get(k, 0) for r in merged) for k in KEYS},
        'verified_isolated_datasets': sum(
            1 for r in merged if r.get('cross_check', {}).get('verified_isolated')),
    }
    report_path.write_text(
        json.dumps({'summary': summary, 'records': merged}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(json.dumps({'summary': summary}, ensure_ascii=False, indent=2))
    return 0 if summary['no_data'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
