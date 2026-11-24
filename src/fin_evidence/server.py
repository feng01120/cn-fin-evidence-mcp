# -*- coding: utf-8 -*-
"""MCP Server：只读、结构化、每个数字都附带证据。"""

import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .store import append_audit, find_fact, find_fact_by_metric, list_datasets, load_dataset

BASE = Path(os.environ.get('FIN_EVIDENCE_DATA', str(Path(__file__).resolve().parents[2] / 'data')))
mcp = FastMCP('cn-fin-evidence')

CODE_RE = re.compile(r'^\d{6}$')
PERIOD_RE = re.compile(r'^\d{4}(?:-\d{2}-\d{2}|Q[1-4])?$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _err(code: str, message: str, status: str = 'fail', **extra) -> Dict[str, Any]:
    return {
        'data': None,
        'evidence': [],
        'meta': {},
        'quality': {'status': status},
        'error': {'code': code, 'message': message, **extra},
    }


def _load(code: str, period: str, announce_date: str = ''):
    if not CODE_RE.fullmatch(str(code or '')):
        return None, _err('INVALID_CODE', 'stock_code 必须是 6 位数字', stock_code=code)
    if not PERIOD_RE.fullmatch(str(period or '')):
        return None, _err('INVALID_PERIOD', 'period 必须是 4 位年份、YYYY-MM-DD 或 YYYYQn', period=period)
    if announce_date and not DATE_RE.fullmatch(str(announce_date)):
        return None, _err('INVALID_ANNOUNCE_DATE', 'announce_date 必须是 YYYY-MM-DD', announce_date=announce_date)
    try:
        return load_dataset(BASE, code, period, announce_date), None
    except FileNotFoundError as e:
        return None, _err('DATASET_NOT_FOUND', str(e))


def _audit(tool: str, args: Dict[str, Any], status: str, evidence: Optional[List[str]] = None):
    try:
        append_audit(BASE, {'tool': tool, 'args': args, 'status': status, 'evidence': evidence or []})
    except OSError:
        # 只读部署或磁盘满时，审计失败不应阻断查询本身
        pass


def _subject_ok(fact: Dict[str, Any]) -> bool:
    return fact.get('subject_check', {}).get('status') != 'fail'


@mcp.tool()
def list_companies() -> Dict[str, Any]:
    """列出已收录的公司、报告期、公告日与证据等级。只返回元信息，不返回财务数据。"""
    rows = list_datasets(BASE)
    _audit('list_companies', {}, 'ok')
    return {'data': rows, 'evidence': [], 'meta': {'count': len(rows)},
            'quality': {'status': 'pass'}}


@mcp.tool()
def get_statement(stock_code: str, period: str, statement: str = '合并资产负债表',
                  items: str = '', cursor: str = '', limit: int = 50,
                  announce_date: str = '') -> Dict[str, Any]:
    """按报表读取科目行。statement 可选：合并资产负债表/合并利润表/合并现金流量表。

    items 为逗号分隔的科目关键词，用于过滤；cursor 为上一页返回的 next_cursor。
    每行包含页码、原文片段与单元格坐标；meta 里给出数据集文件路径，长表可按需读取。
    """
    ds, err = _load(stock_code, period, announce_date)
    if err:
        return err
    allowed = {'合并资产负债表', '合并利润表', '合并现金流量表'}
    if statement not in allowed:
        return _err('INVALID_STATEMENT', 'statement 必须是：%s' % '、'.join(sorted(allowed)))
    if cursor and not cursor.isdigit():
        return _err('INVALID_CURSOR', 'cursor 必须是上一页返回的非负整数字符串', cursor=cursor)
    try:
        limit_i = int(limit)
    except (TypeError, ValueError):
        return _err('INVALID_LIMIT', 'limit 必须是整数', limit=limit)
    rows = [r for r in ds['rows'] if r.get('statement') == statement]
    if items.strip():
        keys = [k.strip() for k in items.split(',') if k.strip()]
        rows = [r for r in rows if any(k in r.get('item', '') for k in keys)]
    start = int(cursor) if cursor else 0
    limit = max(1, min(limit_i, 200))
    page = rows[start:start + limit]
    nxt = str(start + limit) if start + limit < len(rows) else ''
    _audit('get_statement', {'stock_code': stock_code, 'period': period, 'statement': statement,
                             'items': items, 'cursor': cursor, 'limit': limit,
                             'announce_date': announce_date}, 'ok')
    return {
        'data': {'items': page},
        'evidence': [{'page': r.get('page'), 'snippet': r.get('snippet'), 'bbox': r.get('bbox')} for r in page],
        'meta': {'stock_code': stock_code, 'period': period, 'statement': statement,
                 'total': len(rows), 'returned': len(page), 'next_cursor': nxt,
                 'dataset_path': ds['dir'], 'rows_file': str(Path(ds['dir']) / 'rows.json'),
                 'evidence_level': ds['meta'].get('evidence_level', 'verified')},
        'quality': {'status': 'pass'},
    }


@mcp.tool()
def get_ratio(stock_code: str, period: str, ratio: str = '',
              announce_date: str = '') -> Dict[str, Any]:
    """读取财务比率。不传 ratio 返回全部；每个比率都带公式、输入值与证据编号。"""
    ds, err = _load(stock_code, period, announce_date)
    if err:
        return err
    rows = ds['ratios']
    if ratio.strip():
        rows = [r for r in rows if r.get('ratio') == ratio or ratio in r.get('name', '')]
    for r in rows:
        r.setdefault('value_type', 'computed')
    _audit('get_ratio', {'stock_code': stock_code, 'period': period, 'ratio': ratio,
                         'announce_date': announce_date}, 'ok',
           [e for r in rows for e in r.get('evidence', [])])
    if not rows:
        return _err('RATIO_NOT_FOUND', '没有匹配的比率', available=[r['ratio'] for r in ds['ratios']])
    facts_by_id = {f['evidence_id']: f for f in ds['facts']}
    evidence = []
    seen = set()
    for r in rows:
        for eid in r.get('evidence', []):
            if eid in seen:
                continue
            seen.add(eid)
            fact = facts_by_id.get(eid)
            if fact:
                evidence.append({
                    'evidence_id': eid, 'metric': fact.get('metric'),
                    'metric_name': fact.get('metric_name'), 'value': fact.get('value'),
                    'unit': fact.get('unit'), 'page': fact.get('page'),
                    'printed_page': fact.get('printed_page'), 'snippet': fact.get('snippet'),
                    'bbox': fact.get('bbox'), 'statement': fact.get('statement'),
                })
    return {'data': {'ratios': rows}, 'evidence': evidence,
            'meta': {'stock_code': stock_code, 'period': period, 'count': len(rows),
                     'dataset_path': ds['dir']},
            'quality': {'status': 'pass' if all(r['quality']['status'] == 'pass' for r in rows) else 'warning'}}


@mcp.tool()
def get_evidence(evidence_id: str = '', stock_code: str = '', period: str = '',
                 metric: str = '', announce_date: str = '') -> Dict[str, Any]:
    """取回一个数字的六元组：公司、期间、指标、数值、单位、页码与原文片段。

    支持两种调用：evidence_id，或 stock_code + period + metric。
    """
    if evidence_id:
        parts = evidence_id.split('-')
        if len(parts) < 2:
            return _err('EVIDENCE_NOT_FOUND', '证据编号不存在或格式错误', evidence_id=evidence_id)
        code, per = parts[0], parts[1]
        ds, err = _load(code, per)
        if err:
            return _err('EVIDENCE_NOT_FOUND', '证据编号不存在或数据集缺失', evidence_id=evidence_id)
        fact = find_fact(ds, evidence_id)
        if not fact:
            return _err('EVIDENCE_NOT_FOUND', '证据编号不存在', evidence_id=evidence_id)
    else:
        if not (stock_code and period and metric):
            return _err('MISSING_ARGUMENT', '需要 evidence_id，或 stock_code + period + metric')
        ds, err = _load(stock_code, period, announce_date)
        if err:
            return err
        fact = find_fact_by_metric(ds, metric)
        if not fact:
            return _err('METRIC_NOT_FOUND', '没有该指标', metric=metric,
                        available=sorted({f['metric'] for f in ds['facts']}))
    if not _subject_ok(fact):
        return _err('SUBJECT_MISMATCH', '数值存在，但科目名与指标别名不匹配，拒绝作为该指标返回',
                    metric=fact.get('metric'), item_raw=fact.get('item_raw'),
                    subject_check=fact.get('subject_check'), evidence_id=fact.get('evidence_id'))
    _audit('get_evidence', {'evidence_id': evidence_id, 'stock_code': stock_code,
                            'period': period, 'metric': metric}, 'ok', [fact['evidence_id']])
    return {'data': fact, 'evidence': [{
                'evidence_id': fact['evidence_id'], 'page': fact['page'],
                'printed_page': fact.get('printed_page'), 'snippet': fact['snippet'],
                'bbox': fact.get('bbox'), 'unit': fact.get('unit'),
                'value': fact.get('value'), 'priority': fact.get('value_type', 'disclosed'),
            }],
            'meta': {'dataset': ds['meta'].get('company', {}), 'dataset_path': ds['dir'],
                     'report_date': ds['meta'].get('report_date', ''),
                     'announce_date': ds['meta'].get('announce_date', '')},
            'quality': fact.get('quality', {})}


@mcp.tool()
def verify_fact(stock_code: str, period: str, metric: str, claimed_value: float,
                tolerance: float = 0.01, announce_date: str = '') -> Dict[str, Any]:
    """核对一个声称值是否与年报一致。tolerance 为相对误差（0.01 表示 1%）。找不到数值时拒答。"""
    ds, err = _load(stock_code, period, announce_date)
    if err:
        return err
    try:
        tolerance_f = float(tolerance)
    except (TypeError, ValueError):
        return _err('INVALID_TOLERANCE', 'tolerance 必须是非负有限数', tolerance=tolerance)
    if not math.isfinite(tolerance_f) or tolerance_f < 0:
        return _err('INVALID_TOLERANCE', 'tolerance 必须是非负有限数', tolerance=tolerance)
    fact = find_fact_by_metric(ds, metric)
    if not fact:
        return _err('METRIC_NOT_FOUND', '没有该指标', metric=metric,
                    available=sorted({f['metric'] for f in ds['facts']}))
    if not _subject_ok(fact):
        return _err('SUBJECT_MISMATCH', '数值存在，但科目名与指标别名不匹配，拒绝核对',
                    metric=metric, item_raw=fact.get('item_raw'), evidence_id=fact.get('evidence_id'))
    actual = fact.get('value')
    if actual is None:
        return _err('NO_VALUE', '该指标本期未披露，拒绝核对', evidence_id=fact['evidence_id'],
                    status='warning')
    try:
        claimed_f = float(claimed_value)
    except (TypeError, ValueError):
        return _err('INVALID_CLAIM', 'claimed_value 必须是有限数', claimed_value=claimed_value)
    if not math.isfinite(claimed_f):
        return _err('INVALID_CLAIM', 'claimed_value 必须是有限数', claimed_value=claimed_value)
    diff = claimed_f - float(actual)
    ok = abs(diff) <= max(abs(actual) * tolerance_f, 1e-6)
    _audit('verify_fact', {'stock_code': stock_code, 'period': period, 'metric': metric,
                           'claimed_value': claimed_f, 'tolerance': tolerance_f,
                           'announce_date': announce_date},
           'ok' if ok else 'mismatch', [fact['evidence_id']])
    return {
        'data': {'verdict': 'match' if ok else 'mismatch', 'metric': metric,
                 'claimed_value': claimed_f, 'actual_value': actual, 'difference': round(diff, 2),
                 'tolerance': tolerance_f, 'unit': fact.get('unit'),
                 'evidence_level': fact.get('evidence_level', 'verified')},
        'evidence': {'evidence_id': fact['evidence_id'], 'page': fact['page'],
                     'printed_page': fact.get('printed_page'), 'snippet': fact['snippet'],
                     'bbox': fact.get('bbox'), 'unit': fact.get('unit'),
                     'value': actual},
        'meta': {'stock_code': stock_code, 'period': period,
                 'report_date': ds['meta'].get('report_date', ''),
                 'announce_date': ds['meta'].get('announce_date', ''),
                 'dataset_path': ds['dir']},
        'quality': {'status': 'pass' if ok else 'fail'},
    }


@mcp.tool()
def get_quality_report(stock_code: str, period: str,
                       announce_date: str = '') -> Dict[str, Any]:
    """返回勾稽校验、科目校验与数据质量结果：哪些通过、哪些失败、哪些数值缺失。"""
    ds, err = _load(stock_code, period, announce_date)
    if err:
        return err
    checks = ds['checks']
    counts = {'pass': 0, 'warning': 0, 'fail': 0}
    for c in checks:
        counts[c.get('status', 'warning')] = counts.get(c.get('status', 'warning'), 0) + 1
    subject_fail = [f['evidence_id'] for f in ds['facts']
                    if f.get('subject_check', {}).get('status') == 'fail']
    _audit('get_quality_report', {'stock_code': stock_code, 'period': period,
                                  'announce_date': announce_date}, 'ok')
    status = 'fail' if counts['fail'] or subject_fail else ('warning' if counts['warning'] else 'pass')
    return {'data': {'checks': checks, 'counts': counts, 'subject_fail': subject_fail,
                     'coverage': ds['meta'].get('coverage', {}),
                     'coverage_score': ds['meta'].get('coverage_score', 0),
                     'quality_gate': ds['meta'].get('quality_gate', '')},
            'evidence': [],
            'meta': {'stock_code': stock_code, 'period': period,
                     'report_date': ds['meta'].get('report_date', ''),
                     'announce_date': ds['meta'].get('announce_date', ''),
                     'evidence_level': ds['meta'].get('evidence_level', 'verified'),
                     'dataset_path': ds['dir']},
            'quality': {'status': status}}


def main():
    mcp.run()


if __name__ == '__main__':
    main()
