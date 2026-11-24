# -*- coding: utf-8 -*-
"""比率计算与勾稽校验：每个比率都要给出公式、输入与证据。"""

from typing import Dict, List, Optional

from .models import CheckResult, Company, Evidence, Quality, Ratio


def _fmt(x: Optional[float]) -> str:
    return '缺失' if x is None else ('%.2f' % x)


def compute_ratios(company: Company, period: str, facts: List[Evidence]) -> List[Ratio]:
    by_key = {f.metric: f for f in facts}
    out: List[Ratio] = []

    def add(key: str, name: str, formula: str, inputs: List[tuple], calc):
        missing = [k for k, _ in inputs if by_key.get(k) is None or by_key[k].value is None]
        vals = [(k, by_key[k]) for k, _ in inputs if by_key.get(k) and by_key[k].value is not None]
        value = None
        if not missing:
            value = calc()
        quality = Quality(status='pass' if not missing else 'warning',
                          checks=['inputs_present'] if not missing else [],
                          messages=[] if not missing else ['缺少输入：%s' % '、'.join(missing)])
        out.append(Ratio(
            ratio=key, name=name, company=company, period=period,
            value=round(value, 4) if value is not None else None, unit='%',
            formula=formula,
            inputs=[{'metric': k, 'name': f.metric_name, 'value': f.value,
                     'evidence_id': f.evidence_id} for k, f in vals],
            evidence=[f.evidence_id for _, f in vals],
            quality=quality,
        ))

    add('gross_margin', '毛利率',
        '(营业收入 - 营业成本) / 营业收入',
        [('revenue', '营业收入'), ('cost_of_revenue', '营业成本')],
        lambda: (by_key['revenue'].value - by_key['cost_of_revenue'].value) / by_key['revenue'].value * 100)

    add('net_margin', '净利率',
        '净利润 / 营业收入',
        [('net_profit', '净利润'), ('revenue', '营业收入')],
        lambda: by_key['net_profit'].value / by_key['revenue'].value * 100)

    def roe():
        cur = by_key['equity_parent'].value
        prior = by_key['equity_parent'].prior_value
        if prior is None:
            raise ValueError('缺少期初权益')
        return by_key['net_profit_parent'].value / ((cur + prior) / 2) * 100

    add('roe', '净资产收益率（ROE）',
        '归属于母公司股东的净利润 / 平均归属于母公司所有者权益',
        [('net_profit_parent', '归属于母公司股东的净利润'), ('equity_parent', '归属于母公司所有者权益合计')],
        roe)

    add('debt_ratio', '资产负债率',
        '负债合计 / 资产总计',
        [('total_liabilities', '负债合计'), ('total_assets', '资产总计')],
        lambda: by_key['total_liabilities'].value / by_key['total_assets'].value * 100)

    add('current_ratio', '流动比率',
        '流动资产合计 / 流动负债合计',
        [('total_current_assets', '流动资产合计'), ('total_current_liabilities', '流动负债合计')],
        lambda: by_key['total_current_assets'].value / by_key['total_current_liabilities'].value)

    add('cfo_to_revenue', '经营现金流/营业收入',
        '经营活动产生的现金流量净额 / 营业收入',
        [('cfo', '经营活动产生的现金流量净额'), ('revenue', '营业收入')],
        lambda: by_key['cfo'].value / by_key['revenue'].value * 100)

    add('revenue_growth', '营业收入增长率',
        '(本期营业收入 - 上期营业收入) / 上期营业收入',
        [('revenue', '营业收入')],
        lambda: (by_key['revenue'].value - by_key['revenue'].prior_value) / by_key['revenue'].prior_value * 100)

    add('net_profit_growth', '净利润增长率',
        '(本期净利润 - 上期净利润) / 上期净利润',
        [('net_profit', '净利润')],
        lambda: (by_key['net_profit'].value - by_key['net_profit'].prior_value) / by_key['net_profit'].prior_value * 100)

    def turnover():
        prior = by_key['total_assets'].prior_value
        if prior is None:
            raise ValueError('缺少期初资产')
        return by_key['revenue'].value / ((by_key['total_assets'].value + prior) / 2)

    add('asset_turnover', '总资产周转率',
        '营业收入 / 平均资产总计',
        [('revenue', '营业收入'), ('total_assets', '资产总计')],
        turnover)

    # 流动比率不是百分比，单独修正单位
    for r in out:
        if r.ratio in ('current_ratio', 'asset_turnover'):
            r.unit = '倍'
    return out


def run_checks(facts: List[Evidence]) -> List[CheckResult]:
    by_key = {f.metric: f for f in facts}
    results: List[CheckResult] = []

    def get(k: str) -> Optional[float]:
        f = by_key.get(k)
        return f.value if f else None

    def check(name: str, left: Optional[float], right: Optional[float], detail: str, keys: List[str]):
        if left is None or right is None:
            results.append(CheckResult(check=name, status='warning', detail='缺少输入，无法校验',
                                       evidence=[by_key[k].evidence_id for k in keys if k in by_key]))
            return
        diff = left - right
        ok = abs(diff) <= max(1.0, abs(left) * 1e-6)
        results.append(CheckResult(check=name, status='pass' if ok else 'fail', detail=detail,
                                   left=left, right=right, diff=round(diff, 2),
                                   evidence=[by_key[k].evidence_id for k in keys if k in by_key]))

    check('balance_identity', get('total_assets'),
          (get('total_liabilities') + get('total_equity')) if get('total_liabilities') is not None and get('total_equity') is not None else None,
          '资产 = 负债 + 所有者权益', ['total_assets', 'total_liabilities', 'total_equity'])

    check('total_le_identity', get('total_liabilities_equity'), get('total_assets'),
          '负债和所有者权益总计 = 资产总计', ['total_liabilities_equity', 'total_assets'])

    check('cash_flow_identity',
          (get('cfo') + get('cfi') + get('cff') + (get('fx_effect') or 0))
          if all(get(k) is not None for k in ('cfo', 'cfi', 'cff')) else None,
          get('net_cash_increase'), '经营 + 投资 + 筹资现金流 + 汇率影响 = 现金净增加额',
          ['cfo', 'cfi', 'cff', 'fx_effect', 'net_cash_increase'])

    check('cash_roll', (get('beginning_cash') + get('net_cash_increase')) if get('beginning_cash') is not None and get('net_cash_increase') is not None else None,
          get('ending_cash'), '期初现金 + 净增加额 = 期末现金',
          ['beginning_cash', 'net_cash_increase', 'ending_cash'])

    # 同比异常提示：超过 ±50% 不直接判错，但要求人工复核报告口径/重述
    anomalies = []
    for k, label in (('revenue', '营业收入'), ('net_profit', '净利润')):
        f = by_key.get(k)
        if f is None or f.value is None or f.prior_value in (None, 0):
            continue
        growth = (f.value - f.prior_value) / abs(f.prior_value) * 100
        if abs(growth) > 50:
            anomalies.append('%s同比 %.2f%%（本期 %.2f，上期 %.2f）' % (
                label, growth, f.value, f.prior_value))
    results.append(CheckResult(
        check='growth_anomaly',
        status='warning' if anomalies else 'pass',
        detail='；'.join(anomalies) if anomalies else '营收与净利同比波动均在 ±50% 以内',
        evidence=[by_key[k].evidence_id for k in ('revenue', 'net_profit') if k in by_key],
    ))

    for f in facts:
        if f.value is None:
            results.append(CheckResult(check='zero_type', status='warning',
                                       detail='%s 本期值为空，标记为“%s”' % (f.metric_name, f.zero_type or '未披露'),
                                       evidence=[f.evidence_id]))
    return results
