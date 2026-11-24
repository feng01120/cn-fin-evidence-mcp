# -*- coding: utf-8 -*-
"""30 秒演示：一条原披露值、一条后发重述值、一条错误声称值。

只依赖仓库内已提交的 JSON 数据集，不需要 data/raw 下的 PDF。
"""
from .server import (  # noqa: E402
    get_evidence, get_quality_report, get_source_comparison,
    list_companies, verify_fact,
)


def fmt(value):
    return f'{value:,.0f}' if float(value).is_integer() else f'{value:,.2f}'


def main() -> int:
    companies = list_companies()
    datasets = companies['meta']['count']
    codes = len({c['code'] for c in companies.get('data', [])})

    print('cn-fin-evidence  |  traceable financial facts')
    print(f'datasets={datasets}  companies={codes}  evidence=page+snippet')
    print()
    print('[1] 中国神华 2025 总资产是多少？')
    evidence = get_evidence('601088-2025-total_assets')
    fact = evidence['data']
    print(f"    {fmt(fact['value'])} {fact['unit']}   page {fact['page']}")
    print(f"    \"{fact['snippet']}\"")
    print(f"    source: {fact['source_file']}")
    print()
    print('[2] 后发披露写 903,830 百万元，怎么处理？')
    comparison = get_source_comparison('601088', '2025', 'total_assets')
    row = comparison['data']['metrics']['total_assets']
    verified = row['verified']
    eastmoney = row['eastmoney']
    diff = eastmoney['value'] / 1e6 - verified['value']
    pct = diff / verified['value']
    print('    status: restatement_material -> pass_with_restatement')
    print(f"    as_reported      {fmt(verified['value'])} 百万元  (page 148)")
    print(f"    restated         {fmt(eastmoney['value'] / 1e6)} 百万元  ({eastmoney['api_notice_date']})")
    print(f"    difference       {diff:+,.0f} 百万元  ({pct:+.2%})")
    quality = get_quality_report('601088', '2025')['quality']
    print(f"    review           reviewed={len(quality['reviewed_material'])}  unreviewed={len(quality['unreviewed_material'])}")
    print('    rule             original and restated are kept side by side; no overwrite')
    print()
    print('[3] 如果声称值是 999,999 百万元？')
    wrong = verify_fact('601088', '2025', 'total_assets', 999999)
    print(f"    verdict: {wrong['data']['verdict']}   quality: {wrong['quality']['status']}")
    print('    evidence is not rewritten to make the claim look right')
    print()
    print('[4] 如果声称值等于后发重述值 903,830 呢？')
    restated = verify_fact('601088', '2025', 'total_assets', 903830)
    print(f"    verdict: {restated['data']['verdict']}   quality: {restated['quality']['status']}")
    print('    it is marked as a restated comparative, not the current annual-report value')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
