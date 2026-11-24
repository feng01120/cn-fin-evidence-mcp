# -*- coding: utf-8 -*-
"""按新契约重建 raw 下全部年报；保留 _staging，不删除旧数据。"""

import argparse
import datetime
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fetch_report import find_annual, resolve_org  # noqa: E402
from fin_evidence.extract import build_dataset, snippet_hit_rate  # noqa: E402
from fin_evidence.mapping import METRICS, REQUIRED_METRICS  # noqa: E402
from fin_evidence.models import Company  # noqa: E402
from fin_evidence.ratios import compute_ratios, run_checks  # noqa: E402
from fin_evidence.store import save_dataset  # noqa: E402


def build_one(pdf: Path, code: str, year: str, name: str, announce: str, source_url: str) -> dict:
    company = Company(code=code, name=name)
    facts, rows, meta = build_dataset(str(pdf), company, year,
                                     report_date='%s-12-31' % year,
                                     announce_date=announce, source_url=source_url or None)
    ratios = compute_ratios(company, year, facts)
    checks = run_checks(facts)
    present = {f.metric for f in facts if f.value is not None}
    metric_cov = round(len(present & set(REQUIRED_METRICS)) / max(1, len(REQUIRED_METRICS)), 4)
    snippet = snippet_hit_rate(str(pdf), facts)
    passed = sum(1 for c in checks if c.status == 'pass')
    failed = sum(1 for c in checks if c.status == 'fail')
    meta.coverage = {
        'metric_coverage': metric_cov,
        'fact_count': len(facts),
        'expected_metrics': len(REQUIRED_METRICS),
        'all_metrics': len(METRICS),
        'snippet_hit_rate': snippet,
        'check_pass_rate': round(passed / len(checks), 4) if checks else 0.0,
        'check_fail': failed,
        'missing_required': sorted(set(REQUIRED_METRICS) - present),
    }
    meta.coverage['score'] = round((metric_cov + snippet + meta.coverage['check_pass_rate']) / 3, 4)
    meta.coverage_score = meta.coverage['score']
    if failed or metric_cov < 0.8 or snippet < 0.95:
        gate = 'fail'
    elif metric_cov < 0.95 or snippet < 0.99:
        gate = 'warning'
    else:
        gate = 'pass'
    meta.quality_gate = gate
    d = save_dataset(ROOT / 'data', facts, rows, meta, ratios, checks)
    return {'code': code, 'year': year, 'name': name, 'announce_date': announce,
            'fact_count': len(facts), 'row_count': len(rows), 'coverage': meta.coverage,
            'quality_gate': gate, 'dataset': str(d),
            'failed_checks': [{'check': c.check, 'detail': c.detail, 'diff': c.diff}
                              for c in checks if c.status == 'fail']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--only', default='', help='逗号分隔股票代码')
    args = ap.parse_args()
    raw = ROOT / 'data' / 'raw'
    jobs = []
    for pdf in sorted(raw.glob('*_20*.pdf')):
        code, year = pdf.stem.split('_')
        if args.only and code not in set(args.only.split(',')):
            continue
        meta_path = ROOT / 'data' / '_staging' / code / year / 'meta.json'
        if not meta_path.exists():
            # _staging 可能被 build_universe 清理；优先复用现有正式数据集的公告日。
            meta_path = next(iter(sorted(
                (ROOT / 'data' / code).glob('%s-12-31/*/meta.json' % year
                                             ))), meta_path)
        if meta_path.exists():
            m = json.loads(meta_path.read_text(encoding='utf-8'))
            name = m.get('company', {}).get('name', code)
            announce = m.get('announce_date', '')
            source_url = m.get('source_url', '')
        else:
            found = find_annual(code, int(year), org=resolve_org(code))
            if not found:
                print('MISSING META', code, year)
                continue
            ts, adj, _ = found
            announce = datetime.datetime.fromtimestamp(
                ts / 1000, datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
            source_url = 'https://static.cninfo.com.cn/' + adj.lstrip('/')
            name = {'601088': '中国神华能源股份有限公司'}.get(code, code)
        jobs.append((pdf, code, year, name, announce, source_url))

    records = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(build_one, *j): j for j in jobs}
        for fut in as_completed(futures):
            j = futures[fut]
            try:
                rec = fut.result()
                print(json.dumps(rec, ensure_ascii=False))
                records.append(rec)
            except Exception as e:
                print(json.dumps({'code': j[1], 'year': j[2], 'error': '%s: %s' % (type(e).__name__, e)},
                                 ensure_ascii=False))
    out = ROOT / 'data' / 'rebuild_report.json'
    old_records = json.loads(out.read_text(encoding='utf-8')) if out.exists() else []
    if args.only:
        only = set(args.only.split(','))
        old_records = [r for r in old_records if r.get('code') not in only]
    else:
        old_records = []
    merged = old_records + records
    merged.sort(key=lambda r: (r.get('code', ''), r.get('year', '')))
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    codes = {r['code'] for r in merged}
    print(json.dumps({'datasets': len(merged), 'companies': len(codes),
                      'pass': sum(1 for r in merged if r['quality_gate'] == 'pass'),
                      'warning': sum(1 for r in merged if r['quality_gate'] == 'warning'),
                      'fail': sum(1 for r in merged if r['quality_gate'] == 'fail'),
                      'report': str(out)}, ensure_ascii=False))
    return


if __name__ == '__main__':
    main()
