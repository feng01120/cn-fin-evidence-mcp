# -*- coding: utf-8 -*-
"""批量下载并构建试点公司年报，带覆盖率门槛。

用法：
    python scripts/build_universe.py --data data --raw data/raw --years 2023 2024 2025
"""

import argparse
import datetime
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fetch_report import download, find_annual, resolve_org  # noqa: E402
from fin_evidence.extract import build_dataset  # noqa: E402
from fin_evidence.models import Company  # noqa: E402
from fin_evidence.ratios import compute_ratios, run_checks  # noqa: E402
from fin_evidence.store import save_dataset  # noqa: E402

UNIVERSE = [
    ('600519', '贵州茅台酒股份有限公司', '贵州茅台'),
    ('000858', '宜宾五粮液股份有限公司', '五粮液'),
    ('600887', '内蒙古伊利实业集团股份有限公司', '伊利股份'),
    ('000651', '珠海格力电器股份有限公司', '格力电器'),
    ('000333', '美的集团股份有限公司', '美的集团'),
    ('600690', '海尔智家股份有限公司', '海尔智家'),
    ('002594', '比亚迪股份有限公司', '比亚迪'),
    ('300750', '宁德时代新能源科技股份有限公司', '宁德时代'),
    ('601012', '隆基绿能科技股份有限公司', '隆基绿能'),
    ('600309', '万华化学集团股份有限公司', '万华化学'),
    ('603288', '佛山市海天调味食品股份有限公司', '海天味业'),
    ('002304', '江苏洋河酒厂股份有限公司', '洋河股份'),
    ('000568', '泸州老窖股份有限公司', '泸州老窖'),
    ('600809', '山西杏花村汾酒厂股份有限公司', '山西汾酒'),
    ('600276', '江苏恒瑞医药股份有限公司', '恒瑞医药'),
    ('300760', '深圳迈瑞生物医疗电子股份有限公司', '迈瑞医疗'),
    ('002714', '牧原食品股份有限公司', '牧原股份'),
    ('600031', '三一重工股份有限公司', '三一重工'),
    ('601919', '中远海运控股股份有限公司', '中远海控'),
    ('601088', '中国神华能源股份有限公司', '中国神华'),
    ('000725', '京东方科技集团股份有限公司', '京东方A'),
    ('600585', '安徽海螺水泥股份有限公司', '海螺水泥'),
    ('002415', '杭州海康威视数字技术股份有限公司', '海康威视'),
    ('601668', '中国建筑股份有限公司', '中国建筑'),
]


def build_one(company: Company, year: int, pdf: Path, announce_date: str, source_url: str,
              staging: Path) -> tuple:
    period = str(year)
    facts, rows, meta = build_dataset(
        str(pdf), company, period,
        report_date='%d-12-31' % year, announce_date=announce_date, source_url=source_url,
    )
    ratios = compute_ratios(company, period, facts)
    checks = run_checks(facts)
    passed = sum(1 for c in checks if c.status == 'pass')
    failed = sum(1 for c in checks if c.status == 'fail')
    meta.coverage['check_pass_rate'] = round(passed / len(checks), 4) if checks else 0.0
    meta.coverage['check_fail'] = failed
    meta.coverage['score'] = round((
        meta.coverage.get('metric_coverage', 0) + meta.coverage.get('snippet_hit_rate', 0) +
        meta.coverage['check_pass_rate']
    ) / 3, 4)
    meta.coverage_score = meta.coverage['score']
    save_dataset(staging, facts, rows, meta, ratios, checks)
    return meta, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default='data')
    ap.add_argument('--raw', default='data/raw')
    ap.add_argument('--years', nargs='+', type=int, default=[2023, 2024, 2025])
    ap.add_argument('--limit', type=int, default=len(UNIVERSE))
    ap.add_argument('--min-coverage', type=float, default=0.85)
    ap.add_argument('--min-snippet', type=float, default=0.98)
    ap.add_argument('--min-check-pass', type=float, default=0.5)
    args = ap.parse_args()

    raw, data = Path(args.raw), Path(args.data)
    staging = Path(args.data) / '_staging'
    if staging.exists():
        shutil.rmtree(staging)
    manifest_path = raw / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    accepted_companies = set()
    records = []

    for code, name, short in UNIVERSE[:args.limit]:
        org = resolve_org(code)
        for year in args.years:
            key = '%s-%d' % (code, year)
            pdf = raw / ('%s_%d.pdf' % (code, year))
            rec = {'code': code, 'name': name, 'short_name': short, 'year': year,
                   'report_date': '%d-12-31' % year, 'pdf': str(pdf)}
            try:
                if not pdf.exists() or pdf.stat().st_size < 10000:
                    got = download(code, year, raw, org=org)
                    rec.update({'announce_date': got['announce_date'],
                                'source_url': got['source_url'], 'title': got['title']})
                    time.sleep(0.2)
                else:
                    old = manifest.get(key, {})
                    rec.update({'announce_date': old.get('announce_date', ''),
                                'source_url': old.get('source_url', '')})
                    if not rec['announce_date'] or not rec['source_url']:
                        ts, adj, title = find_annual(code, year, org=org)
                        rec.update({'announce_date': datetime.datetime.fromtimestamp(
                            ts / 1000, datetime.timezone(
                                datetime.timedelta(hours=8))).date().isoformat(),
                            'source_url': 'https://static.cninfo.com.cn/' + adj.lstrip('/'),
                            'title': title})
                company = Company(code=code, name=name, short_name=short)
                meta, checks = build_one(company, year, pdf, rec['announce_date'],
                                         rec['source_url'], staging)
                cov = meta.coverage
                ok = (cov.get('metric_coverage', 0) >= args.min_coverage
                      and cov.get('snippet_hit_rate', 0) >= args.min_snippet
                      and cov.get('check_fail', 1) == 0
                      and cov.get('check_pass_rate', 0) >= args.min_check_pass)
                rec.update({'status': 'accepted' if ok else 'rejected', 'coverage': cov,
                            'fact_count': meta.fact_count})
                if ok:
                    # save_dataset 使用 (report_date, announce_date) 目录布局；
                    # 不能再用旧的 code/year 路径，否则 copytree 找不到源目录。
                    target = data / code / meta.report_date / meta.announce_date
                    source = staging / code / meta.report_date / meta.announce_date
                    shutil.copytree(source, target, dirs_exist_ok=True)
                    accepted_companies.add(code)
                else:
                    rec['reason'] = 'coverage/check gate failed'
            except Exception as e:
                rec.update({'status': 'error', 'error': '%s: %s' % (type(e).__name__, e)})
            records.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

    manifest.update({('%s-%d' % (r['code'], r['year'])): r for r in records})
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    complete = 0
    for code, _, _ in UNIVERSE[:args.limit]:
        years = [r for r in records if r['code'] == code]
        if years and all(r.get('status') == 'accepted' for r in years) and len(years) == len(args.years):
            complete += 1
    summary = {
        'records': len(records),
        'accepted': sum(1 for r in records if r.get('status') == 'accepted'),
        'rejected': sum(1 for r in records if r.get('status') == 'rejected'),
        'errors': sum(1 for r in records if r.get('status') == 'error'),
        'accepted_companies': len(accepted_companies),
        'complete_companies': complete,
    }
    print(json.dumps({'summary': summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
