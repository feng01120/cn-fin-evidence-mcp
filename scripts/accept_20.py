# -*- coding: utf-8 -*-
"""B 阶段验收：20 个随机数值原文命中 + 勾稽通过率 + verified 拒答边界。"""
import json
import random
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fin_evidence.server import get_evidence, get_source_comparison, verify_fact  # noqa: E402
from fin_evidence.store import list_datasets  # noqa: E402

DATA = ROOT / 'data'
SEED = 20261124
HARD_CHECKS = ('balance_identity', 'total_le_identity', 'cash_flow_identity', 'cash_roll')


def compact(s: str) -> str:
    return re.sub(r'[\s\u200a\u200b\xa0]+', '', s)


def variants(value: float):
    """只接受与数值精确相等的原文写法，从 0 到 6 位小数中选。"""
    out = set()
    av = abs(float(value))
    for p in range(7):
        s = f'{av:,.{p}f}'
        try:
            if abs(float(s.replace(',', '')) - av) > 1e-9:
                continue
        except ValueError:
            continue
        out.add(s)
    if value < 0:
        for s in list(out):
            out.add('(' + s + ')')
            out.add('（' + s + '）')
            out.add('-' + s)
    return out


def main() -> int:
    rng = random.Random(SEED)
    datasets = list_datasets(DATA)
    by_company = {}
    for d in datasets:
        by_company.setdefault(d['code'], []).append(d)

    # 每家公司随机抽一条有值的证据，合计 20 条，覆盖 20 家公司。
    picks = []
    for code in sorted(by_company):
        ds = rng.choice(by_company[code])
        facts = json.loads((Path(ds['path']) / 'facts.json').read_text(encoding='utf-8'))
        candidates = [f for f in facts if f.get('value') is not None]
        fact = rng.choice(candidates)
        picks.append((ds, fact))

    results = []
    for ds, fact in picks:
        pdf_path = DATA / 'raw' / Path(ds['source_file']).name
        doc = pymupdf.open(str(pdf_path))
        page_text = compact(doc[fact['page'] - 1].get_text())
        snippet_text = compact(fact.get('snippet', ''))
        hit_variants = sorted(v for v in variants(float(fact['value']))
                              if v in page_text and v in snippet_text)
        results.append({
            'code': fact['company']['code'], 'company': fact['company']['name'],
            'metric': fact['metric'], 'value': fact['value'], 'unit': fact['unit'],
            'page': fact['page'], 'evidence_id': fact['evidence_id'],
            'pdf': pdf_path.name, 'hit': bool(hit_variants),
            'matched_text': hit_variants[0] if hit_variants else '',
            'snippet': fact['snippet'],
        })

    # 勾稽通过率：四条硬校验逐数据集统计。
    hard_total = hard_pass = 0
    check_counts = {'pass': 0, 'warning': 0, 'fail': 0}
    check_names = {}
    for d in datasets:
        checks = json.loads((Path(d['path']) / 'checks.json').read_text(encoding='utf-8'))
        for c in checks:
            check_counts[c['status']] = check_counts.get(c['status'], 0) + 1
            check_names[c['check']] = check_names.get(c['check'], 0) + 1
            if c['check'] in HARD_CHECKS:
                hard_total += 1
                hard_pass += int(c['status'] == 'pass')

    # verified 模式的拒答边界。
    refusals = {
        'unknown_metric': get_evidence(stock_code='600519', period='2025', metric='not_exist')['error']['code'],
        'unknown_evidence': get_evidence('600519-2025-not_exist')['error']['code'],
        'unknown_dataset': get_evidence(stock_code='999999', period='2025', metric='cash')['error']['code'],
        'verify_unknown_metric': verify_fact('600519', '2025', 'not_exist', 1.0)['error']['code'],
    }

    audit_path = DATA / 'audit_report.json'
    row_audit = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else {}
    structured_datasets = sum(1 for d in datasets if d.get('structured_count'))
    sample_ds = next((d for d in datasets if d['code'] == '600519' and d['period'] == '2025'), None)
    structured_sample = {}
    structured_ok = False
    if sample_ds:
        sd = json.loads((Path(sample_ds['path']) / 'structured.json').read_text(encoding='utf-8'))
        metric = next(iter(sd.get('metrics', {})))
        eid = '%s-%s-%s-structured' % (sample_ds['code'], sample_ds['period'], metric)
        sr = get_evidence(eid)
        structured_sample = {
            'evidence_id': eid,
            'evidence_level': sr.get('meta', {}).get('evidence_level'),
            'evidence_count': len(sr.get('evidence', [])),
            'quality_status': sr.get('quality', {}).get('status'),
            'error': (sr.get('error') or {}).get('code'),
        }
        structured_ok = (
            structured_sample['error'] is None
            and structured_sample['evidence_level'] == 'structured'
            and structured_sample['evidence_count'] == 0
            and structured_sample['quality_status'] == 'warning'
        )

    second_datasets = sum(1 for d in datasets if d.get('second_source_count'))
    second_metrics = sum(int(d.get('second_source_count') or 0) for d in datasets)
    second_sample = {}
    second_ok = False
    second_cross = row_audit.get('second_source_cross_check', {})
    if sample_ds:
        sr = get_source_comparison('600519', '2025', 'sales_cash')
        row = (sr.get('data') or {}).get('metrics', {}).get('sales_cash', {})
        second_sample = {
            'provider': (sr.get('meta') or {}).get('provider'),
            'status': row.get('status'),
            'source_url': (row.get('sina') or {}).get('source_url'),
            'eastmoney_vs_sina_diff': row.get('eastmoney_vs_sina_diff'),
            'error': (sr.get('error') or {}).get('code'),
        }
        second_ok = (
            second_sample['error'] is None
            and second_sample['status'] == 'pass'
            and str(second_sample['source_url'] or '').startswith('https://')
        )

    levels = {}
    gates = {}
    cross_gates = {}
    for d in datasets:
        levels[d.get('evidence_level', '')] = levels.get(d.get('evidence_level', ''), 0) + 1
        gates[d.get('quality_gate', '')] = gates.get(d.get('quality_gate', ''), 0) + 1
        cross_gates[d.get('cross_source_gate', '')] = cross_gates.get(d.get('cross_source_gate', ''), 0) + 1

    report = {
        'seed': SEED,
        'datasets': len(datasets),
        'companies': len(by_company),
        'evidence_levels': levels,
        'quality_gates': gates,
        'cross_source_gates': cross_gates,
        'random_20': results,
        'random_20_hit': sum(1 for r in results if r['hit']),
        'random_20_hit_rate': round(sum(1 for r in results if r['hit']) / len(results), 4),
        'hard_checks': {'total': hard_total, 'pass': hard_pass,
                        'pass_rate': round(hard_pass / hard_total, 4) if hard_total else 0.0},
        'check_status_counts': check_counts,
        'check_names': check_names,
        'refusals': refusals,
        'structured': {
            'datasets': structured_datasets,
            'metrics': sum(int(d.get('structured_count') or 0) for d in datasets),
            'sample': structured_sample,
            'sample_ok': structured_ok,
        },
        'second_source': {
            'datasets': second_datasets,
            'metrics': second_metrics,
            'sample': second_sample,
            'sample_ok': second_ok,
            'cross_check': second_cross,
            'cross_source_gates': cross_gates,
        },
        'row_audit': {
            'error_count': row_audit.get('error_count'),
            'warning_count': row_audit.get('warning_count'),
            'pass': row_audit.get('pass'),
        },
        'acceptance': (
            len(results) == 20
            and all(r['hit'] for r in results)
            and hard_pass == hard_total
            and all(v == 'EVIDENCE_NOT_FOUND' or v == 'METRIC_NOT_FOUND' or v == 'DATASET_NOT_FOUND'
                    for v in refusals.values())
            and row_audit.get('error_count') == 0
            and structured_datasets == len(datasets)
            and structured_ok
            and second_datasets == len(datasets)
            and second_ok
            and int(second_cross.get('verified_isolated', 0)) == 0
        ),
    }
    out = DATA / 'acceptance_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('datasets', 'companies', 'evidence_levels',
                                              'quality_gates', 'random_20_hit_rate',
                                              'hard_checks', 'check_status_counts',
                                              'refusals', 'acceptance')}, ensure_ascii=False, indent=2))
    return 0 if report['acceptance'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
