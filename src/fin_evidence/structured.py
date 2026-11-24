# -*- coding: utf-8 -*-
"""结构化数据覆盖层：有值、有来源，但没有年报页码。

用途很明确：当 PDF 证据不可用或用户只需要快速覆盖时，返回
`evidence_level=structured` 的数字，并强制标注“无页码证据”。它永远不能
冒充 `verified`，也不能覆盖已经通过页码/片段校验的 facts。
"""

import datetime
from typing import Any, Dict, List, Optional

import requests

from .mapping import BY_KEY

API = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

BALANCE = 'RPT_DMSK_FN_BALANCE'
INCOME = 'RPT_DMSK_FN_INCOME'
CASH = 'RPT_DMSK_FN_CASHFLOW'

# metric -> (东方财富报表名, 字段名)
FIELDS = {
    # 资产负债表
    'cash': (BALANCE, 'MONETARYFUNDS'),
    'accounts_receivable': (BALANCE, 'ACCOUNTS_RECE'),
    'inventory': (BALANCE, 'INVENTORY'),
    'total_assets': (BALANCE, 'TOTAL_ASSETS'),
    'total_liabilities': (BALANCE, 'TOTAL_LIABILITIES'),
    'total_equity': (BALANCE, 'TOTAL_EQUITY'),
    # 利润表
    'total_revenue': (INCOME, 'TOTAL_OPERATE_INCOME'),
    'revenue': (INCOME, 'OPERATE_INCOME'),
    'total_cost': (INCOME, 'TOTAL_OPERATE_COST'),
    'cost_of_revenue': (INCOME, 'OPERATE_COST'),
    'selling_expense': (INCOME, 'SALE_EXPENSE'),
    'admin_expense': (INCOME, 'MANAGE_EXPENSE'),
    'finance_expense': (INCOME, 'FINANCE_EXPENSE'),
    'operating_profit': (INCOME, 'OPERATE_PROFIT'),
    'total_profit': (INCOME, 'TOTAL_PROFIT'),
    'net_profit_parent': (INCOME, 'PARENT_NETPROFIT'),
    # 现金流量表
    'sales_cash': (CASH, 'SALES_SERVICES'),
    'cfo': (CASH, 'NETCASH_OPERATE'),
    'cfi': (CASH, 'NETCASH_INVEST'),
    'cff': (CASH, 'NETCASH_FINANCE'),
    'net_cash_increase': (CASH, 'CCE_ADD'),
    'beginning_cash': (CASH, 'BEGIN_CCE'),
    'ending_cash': (CASH, 'END_CCE'),
}

REPORT_NAMES = (BALANCE, INCOME, CASH)
UNIT_FACTORS = {'元': 1.0, '千元': 1e3, '万元': 1e4, '百万元': 1e6, '亿元': 1e8}
PASS_TOLERANCE = 0.01
RESTATEMENT_TOLERANCE = 0.25


def _source_url(report_name: str, code: str, report_date: str) -> str:
    params = {
        'reportName': report_name, 'columns': 'ALL',
        'filter': '(SECURITY_CODE="%s")(REPORT_DATE=\'%s\')' % (code, report_date),
        'pageNumber': 1, 'pageSize': 1, 'source': 'WEB', 'client': 'WEB',
    }
    return requests.Request('GET', API, params=params).prepare().url


def fetch_metrics(code: str, report_date: str, timeout: int = 20) -> Dict[str, Any]:
    """抓取三表结构化字段。API 失败/缺字段都不编造，直接返回 errors/missing。"""
    metrics: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for report_name in REPORT_NAMES:
        params = {
            'reportName': report_name, 'columns': 'ALL',
            'filter': '(SECURITY_CODE="%s")(REPORT_DATE=\'%s\')' % (code, report_date),
            'pageNumber': 1, 'pageSize': 1, 'source': 'WEB', 'client': 'WEB',
        }
        try:
            resp = requests.get(API, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:  # 网络错误不应阻断其它报表
            errors.append('%s: %s' % (report_name, e))
            continue
        rows = ((payload.get('result') or {}).get('data') or [])
        if not rows:
            errors.append('%s: 无数据' % report_name)
            continue
        row = rows[0]
        url = _source_url(report_name, code, report_date)
        for metric, (rn, field) in FIELDS.items():
            if rn != report_name:
                continue
            raw = row.get(field)
            if raw in (None, '', '-'):
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            definition = BY_KEY[metric]
            metrics[metric] = {
                'metric': metric,
                'metric_name': definition.name,
                'value': value,
                'unit': '元',
                'statement': definition.statement,
                'api_field': field,
                'report_name': report_name,
                'source_url': url,
                'api_notice_date': str(row.get('NOTICE_DATE') or '')[:10],
                'report_type_code': row.get('REPORT_TYPE_CODE'),
                'data_state': row.get('DATA_STATE'),
                'quality': {
                    'status': 'warning',
                    'checks': ['no_page_evidence'],
                    'messages': ['结构化接口数据，无年报页码证据；不得冒充 verified'],
                },
            }
    return {'metrics': metrics, 'errors': errors,
            'provider': 'eastmoney', 'report_date': report_date,
            'fetched_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds')}


def to_yuan(value: Optional[float], unit: str) -> Optional[float]:
    if value is None:
        return None
    return float(value) * UNIT_FACTORS.get(unit, 1.0)


def build_overlay(facts: List[Dict[str, Any]], fetched: Dict[str, Any],
                  announce_date: str = '') -> Dict[str, Any]:
    """把结构化指标与已解析 facts 交叉核对；只做标注，不覆盖 verified。

    结构化 API 的 NOTICE_DATE 如果是“后一年年报”的披露日，报表期相同但
    数值可能已被追溯重述/重分类。此时标成 restatement，而不是把两套口径
    都当成同一张表的冲突。差异超过 25% 的标成 restatement_material，
    仍进入 warning，要求人工核对合并范围/会计政策变更。
    """
    verified = {f.get('metric'): f for f in facts if f.get('value') is not None}
    metrics = fetched.get('metrics', {})
    cross = {'pass': 0, 'restatement': 0, 'restatement_material': 0,
             'warning': 0, 'missing': 0}
    announce = announce_date or fetched.get('announce_date', '')
    for metric, item in metrics.items():
        fact = verified.get(metric)
        chk = {'status': 'missing', 'verified_value': None, 'verified_unit': None,
               'relative_diff': None, 'announce_date': announce,
               'api_notice_date': item.get('api_notice_date', '')}
        if fact:
            expected = to_yuan(fact.get('value'), fact.get('unit', '元'))
            if expected is not None:
                diff = abs(item['value'] - expected) / max(abs(expected), 1e-9)
                notice = str(item.get('api_notice_date') or '')
                later = bool(notice and announce and notice > announce)
                if diff <= PASS_TOLERANCE:
                    status = 'pass'
                elif later and diff <= RESTATEMENT_TOLERANCE:
                    status = 'restatement'
                elif later:
                    status = 'restatement_material'
                else:
                    status = 'warning'
                chk.update({'status': status, 'verified_value': fact.get('value'),
                            'verified_unit': fact.get('unit'),
                            'relative_diff': round(diff, 6), 'later_filing': later})
                if status == 'restatement':
                    item['quality']['status'] = 'warning'
                    item['quality']['messages'].append(
                        '结构化值与原始年报值相差 %.2f%%；API 披露日 %s 晚于数据集公告日 %s，'
                        '判定为后发年报追溯/重分类，保留双口径'
                        % (diff * 100, notice, announce))
                elif status == 'restatement_material':
                    item['quality']['status'] = 'warning'
                    item['quality']['messages'].append(
                        '结构化值与原始年报值相差 %.2f%%；虽为后发年报追溯，但差异超过 %.0f%%，'
                        '需人工核对合并范围/会计政策变更'
                        % (diff * 100, RESTATEMENT_TOLERANCE * 100))
                elif status == 'warning':
                    item['quality']['status'] = 'warning'
                    item['quality']['messages'].append(
                        '结构化值与年报解析值相差 %.2f%%，且不属于可识别的后发年报追溯；'
                        '保留两套口径并标记待核'
                        % (diff * 100))
        item['cross_check'] = chk
    for item in metrics.values():
        status = item.get('cross_check', {}).get('status', 'missing')
        cross[status] = cross.get(status, 0) + 1
    return {
        'provider': fetched.get('provider', 'eastmoney'),
        'fetched_at': fetched.get('fetched_at'),
        'report_date': fetched.get('report_date'),
        'announce_date': announce,
        'metrics': metrics,
        'cross_check': cross,
        'errors': fetched.get('errors', []),
    }
