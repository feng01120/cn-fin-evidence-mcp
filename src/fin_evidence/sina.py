# -*- coding: utf-8 -*-
"""新浪财经三表结构化适配器：第二个独立结构化源。

新浪返回的是制表符分隔的文本表，金额列单位在表头标明。它只用于
交叉核对，不参与 verified 的 fallback；任何一个源都不能单独冒充年报页码。
"""

import datetime
from typing import Any, Dict, List, Optional

import requests

from .extract import normalize_label
from .mapping import BY_KEY
from .structured import UNIT_FACTORS

REPORTS = {
    '合并资产负债表': 'BalanceSheet',
    '合并利润表': 'ProfitStatement',
    '合并现金流量表': 'CashFlow',
}
URL = ('https://money.finance.sina.com.cn/corp/go.php/vDOWN_%s/'
       'displaytype/4/stockid/%s/ctrl/%s/type/1.phtml')
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}

FIELDS = {
    '合并资产负债表': {
        '货币资金': 'cash',
        '应收账款': 'accounts_receivable',
        '存货': 'inventory',
        '流动资产合计': 'total_current_assets',
        '非流动资产合计': 'total_noncurrent_assets',
        '资产总计': 'total_assets',
        '流动负债合计': 'total_current_liabilities',
        '非流动负债合计': 'total_noncurrent_liabilities',
        '负债合计': 'total_liabilities',
        '归属于母公司所有者权益合计': 'equity_parent',
        '所有者权益合计': 'total_equity',
        '负债和所有者权益总计': 'total_liabilities_equity',
    },
    '合并利润表': {
        '营业总收入': 'total_revenue',
        '营业收入': 'revenue',
        '营业总成本': 'total_cost',
        '营业成本': 'cost_of_revenue',
        '税金及附加': 'taxes_surcharges',
        '营业税金及附加': 'taxes_surcharges',
        '销售费用': 'selling_expense',
        '管理费用': 'admin_expense',
        '研发费用': 'rd_expense',
        '财务费用': 'finance_expense',
        '营业利润': 'operating_profit',
        '利润总额': 'total_profit',
        '净利润': 'net_profit',
        '归属于母公司股东的净利润': 'net_profit_parent',
        '归属于母公司所有者的净利润': 'net_profit_parent',
        '基本每股收益': 'basic_eps',
    },
    '合并现金流量表': {
        '销售商品、提供劳务收到的现金': 'sales_cash',
        '经营活动产生的现金流量净额': 'cfo',
        '投资活动产生的现金流量净额': 'cfi',
        '筹资活动产生的现金流量净额': 'cff',
        '汇率变动对现金及现金等价物的影响': 'fx_effect',
        '现金及现金等价物净增加额': 'net_cash_increase',
        '现金及现金等价物净减少额': 'net_cash_increase',
        '期初现金及现金等价物余额': 'beginning_cash',
        '期末现金及现金等价物余额': 'ending_cash',
    },
}


def _url(report: str, code: str, year: str) -> str:
    return URL % (REPORTS[report], code, year)


def _number(raw: str) -> Optional[float]:
    text = (raw or '').strip().replace(',', '').replace('\u200a', '')
    if text in ('', '-', '--', '—'):
        return None
    negative = text.startswith('(') or text.startswith('（')
    text = text.strip('()（）')
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def parse_report(text: str, report_date: str, report: str,
                 code: str, source_url: str = '') -> Dict[str, Any]:
    """解析新浪三表文本；只取 report_date 所在的那一列。"""
    lines = [line.split('\t') for line in text.splitlines()]
    if not lines:
        return {'metrics': {}, 'errors': ['空响应'], 'unit': '元'}
    header = [x.strip() for x in lines[0]]
    wanted = report_date.replace('-', '')
    date_idx = None
    for i, cell in enumerate(header):
        if cell.replace('-', '').replace('/', '') == wanted:
            date_idx = i
            break
    if date_idx is None:
        return {'metrics': {}, 'errors': ['没有报告期 %s 的列' % report_date], 'unit': '元'}

    unit = '元'
    for row in lines[1:4]:
        if row and row[0].strip() == '单位':
            unit = (row[date_idx] if len(row) > date_idx else '元').strip() or '元'
            break

    metrics: Dict[str, Dict[str, Any]] = {}
    for row in lines:
        if not row:
            continue
        label = normalize_label(row[0])
        metric = FIELDS.get(report, {}).get(label)
        if not metric or len(row) <= date_idx:
            continue
        value = _number(row[date_idx])
        if value is None:
            continue
        definition = BY_KEY[metric]
        metrics[metric] = {
            'metric': metric,
            'metric_name': definition.name,
            'value': value * UNIT_FACTORS.get(unit, 1.0),
            'unit': (definition.unit if metric == 'basic_eps' else '元'),
            'statement': report,
            'source_label': row[0].strip(),
            'source_url': source_url or _url(report, code, report_date[:4]),
            'provider': 'sina',
        }
    return {'metrics': metrics, 'errors': [], 'unit': unit}


def fetch_metrics(code: str, report_date: str, timeout: int = 20) -> Dict[str, Any]:
    """抓取新浪三表；任一报表失败不阻断其它报表。"""
    metrics: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    year = report_date[:4]
    for report in REPORTS:
        url = _url(report, code, year)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            parsed = parse_report(resp.text, report_date, report, code, url)
        except Exception as e:
            errors.append('%s: %s' % (report, e))
            continue
        if parsed.get('errors'):
            errors.extend('%s: %s' % (report, x) for x in parsed['errors'])
            continue
        metrics.update(parsed.get('metrics', {}))
    return {'metrics': metrics, 'errors': errors, 'provider': 'sina',
            'report_date': report_date,
            'fetched_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds')}


def _yuan(value: Optional[float], unit: str) -> Optional[float]:
    if value is None:
        return None
    return float(value) * UNIT_FACTORS.get(unit, 1.0)


def build_comparison(facts: List[Dict[str, Any]], east_doc: Dict[str, Any],
                     sina_doc: Dict[str, Any], announce_date: str = '') -> Dict[str, Any]:
    """三源并排：verified / 东方财富 / 新浪；只标注，不改写任何值。"""
    verified = {f.get('metric'): f for f in facts if f.get('value') is not None}
    east = (east_doc or {}).get('metrics', {}) if isinstance(east_doc, dict) else {}
    sina = (sina_doc or {}).get('metrics', {}) if isinstance(sina_doc, dict) else {}
    rows: Dict[str, Dict[str, Any]] = {}
    counts = {'pass': 0, 'restatement': 0, 'restatement_material': 0,
              'verified_isolated': 0, 'warning': 0, 'unverified': 0, 'missing': 0}

    def diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return abs(a - b) / max(abs(a), 1e-9)

    for metric in sorted(set(verified) | set(east) | set(sina)):
        fact = verified.get(metric)
        e = east.get(metric) or {}
        s = sina.get(metric) or {}
        v_value = _yuan(fact.get('value'), fact.get('unit', '元')) if fact else None
        e_value = e.get('value')
        s_value = s.get('value')
        e_status = (e.get('cross_check') or {}).get('status')
        d_vs = diff(v_value, s_value)
        d_es = diff(e_value, s_value)
        if fact is None:
            status = 'unverified'
        elif s_value is None and e_value is None:
            status = 'missing'
        elif s_value is None:
            status = e_status or 'warning'
        elif d_vs is not None and d_vs <= 0.01 and (d_es is None or d_es <= 0.01):
            status = 'pass'
        elif e_status in ('restatement', 'restatement_material'):
            status = e_status
        elif (d_vs is None or d_vs > 0.01) and d_es is not None and d_es <= 0.01:
            status = 'verified_isolated'
        else:
            status = 'warning'
        counts[status] = counts.get(status, 0) + 1
        rows[metric] = {
            'metric': metric,
            'metric_name': (fact or e or s).get('metric_name', metric),
            'verified': ({'value': fact.get('value'), 'unit': fact.get('unit'),
                          'evidence_id': fact.get('evidence_id')} if fact else None),
            'eastmoney': ({'value': e.get('value'), 'unit': e.get('unit'),
                           'api_notice_date': e.get('api_notice_date'),
                           'cross_check': e_status} if e else None),
            'sina': ({'value': s.get('value'), 'unit': s.get('unit'),
                      'source_label': s.get('source_label'),
                      'source_url': s.get('source_url')} if s else None),
            'verified_vs_sina_diff': round(d_vs, 6) if d_vs is not None else None,
            'eastmoney_vs_sina_diff': round(d_es, 6) if d_es is not None else None,
            'status': status,
        }
    return {
        'provider': 'sina',
        'fetched_at': (sina_doc or {}).get('fetched_at'),
        'report_date': (sina_doc or {}).get('report_date'),
        'announce_date': announce_date,
        'rows': rows,
        'cross_check': counts,
        'errors': (sina_doc or {}).get('errors', []),
    }
