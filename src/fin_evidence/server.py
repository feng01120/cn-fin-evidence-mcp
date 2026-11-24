# -*- coding: utf-8 -*-
"""MCP Server：只读、结构化、每个数字都附带证据。"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .store import append_audit, find_fact, list_datasets, load_dataset

BASE = Path(os.environ.get('FIN_EVIDENCE_DATA', str(Path(__file__).resolve().parents[2] / 'data')))
mcp = FastMCP('cn-fin-evidence')


def _err(code: str, message: str, **extra) -> Dict[str, Any]:
    return {'error': {'code': code, 'message': message, **extra}}


def _audit(tool: str, args: Dict[str, Any], status: str, evidence: Optional[List[str]] = None):
    append_audit(BASE, {'tool': tool, 'args': args, 'status': status, 'evidence': evidence or []})


@mcp.tool()
def list_companies() -> Dict[str, Any]:
    """列出已收录的公司与报告期。只返回元信息，不返回财务数据。"""
    rows = list_datasets(BASE)
    _audit('list_companies', {}, 'ok')
    return {'data': rows, 'meta': {'count': len(rows)}, 'quality': {'status': 'pass'}}


@mcp.tool()
def get_statement(stock_code: str, period: str, statement: str = '合并资产负债表',
                  items: str = '', cursor: str = '', limit: int = 50) -> Dict[str, Any]:
    """按报表读取科目行。statement 可选：合并资产负债表/合并利润表/合并现金流量表。

    items 为逗号分隔的科目关键词，用于过滤；cursor 为上一页返回的 next_cursor。
    每行包含页码、原文片段与单元格坐标，便于复核。
    """
    try:
        ds = load_dataset(BASE, stock_code, period)
    except FileNotFoundError as e:
        return _err('DATASET_NOT_FOUND', str(e))
    allowed = {'合并资产负债表', '合并利润表', '合并现金流量表'}
    if statement not in allowed:
        return _err('INVALID_STATEMENT', 'statement 必须是：%s' % '、'.join(sorted(allowed)))
    rows = [r for r in ds['rows'] if r.get('statement') == statement]
    if items.strip():
        keys = [k.strip() for k in items.split(',') if k.strip()]
        rows = [r for r in rows if any(k in r.get('item', '') for k in keys)]
    start = int(cursor) if cursor.isdigit() else 0
    limit = max(1, min(int(limit), 200))
    page = rows[start:start + limit]
    nxt = str(start + limit) if start + limit < len(rows) else ''
    _audit('get_statement', {'stock_code': stock_code, 'period': period, 'statement': statement,
                             'items': items, 'cursor': cursor, 'limit': limit}, 'ok')
    return {
        'data': {'items': page},
        'evidence': [{'page': r.get('page'), 'snippet': r.get('snippet'), 'bbox': r.get('bbox')} for r in page],
        'meta': {'stock_code': stock_code, 'period': period, 'statement': statement,
                 'total': len(rows), 'returned': len(page), 'next_cursor': nxt},
        'quality': {'status': 'pass'},
    }


@mcp.tool()
def get_ratio(stock_code: str, period: str, ratio: str = '') -> Dict[str, Any]:
    """读取财务比率。不传 ratio 返回全部；每个比率都带公式、输入值与证据编号。"""
    try:
        ds = load_dataset(BASE, stock_code, period)
    except FileNotFoundError as e:
        return _err('DATASET_NOT_FOUND', str(e))
    rows = ds['ratios']
    if ratio.strip():
        rows = [r for r in rows if r.get('ratio') == ratio or ratio in r.get('name', '')]
    _audit('get_ratio', {'stock_code': stock_code, 'period': period, 'ratio': ratio}, 'ok',
           [e for r in rows for e in r.get('evidence', [])])
    if not rows:
        return _err('RATIO_NOT_FOUND', '没有匹配的比率', available=[r['ratio'] for r in ds['ratios']])
    return {'data': {'ratios': rows}, 'meta': {'stock_code': stock_code, 'period': period,
                                               'count': len(rows)},
            'quality': {'status': 'pass' if all(r['quality']['status'] == 'pass' for r in rows) else 'warning'}}


@mcp.tool()
def get_evidence(evidence_id: str) -> Dict[str, Any]:
    """按证据编号取回一个数字的六元组：公司、期间、指标、数值、单位、页码与原文片段。"""
    code, period = (evidence_id.split('-') + ['', ''])[:2]
    try:
        ds = load_dataset(BASE, code, period)
    except FileNotFoundError:
        return _err('EVIDENCE_NOT_FOUND', '证据编号不存在或数据集缺失', evidence_id=evidence_id)
    fact = find_fact(ds, evidence_id)
    if not fact:
        return _err('EVIDENCE_NOT_FOUND', '证据编号不存在', evidence_id=evidence_id)
    _audit('get_evidence', {'evidence_id': evidence_id}, 'ok', [evidence_id])
    return {'data': fact, 'meta': {'dataset': ds['meta'].get('company', {})}, 'quality': fact.get('quality', {})}


@mcp.tool()
def verify_fact(stock_code: str, period: str, metric: str, claimed_value: float,
                tolerance: float = 0.01) -> Dict[str, Any]:
    """核对一个声称值是否与年报一致。tolerance 为相对误差（0.01 表示 1%）。找不到数值时拒答。"""
    try:
        ds = load_dataset(BASE, stock_code, period)
    except FileNotFoundError as e:
        return _err('DATASET_NOT_FOUND', str(e))
    fact = next((f for f in ds['facts'] if f.get('metric') == metric), None)
    if not fact:
        return _err('METRIC_NOT_FOUND', '没有该指标', metric=metric,
                    available=sorted({f['metric'] for f in ds['facts']}))
    actual = fact.get('value')
    if actual is None:
        return _err('NO_VALUE', '该指标本期未披露，拒绝核对', evidence_id=fact['evidence_id'])
    diff = float(claimed_value) - float(actual)
    ok = abs(diff) <= max(abs(actual) * float(tolerance), 1.0)
    _audit('verify_fact', {'stock_code': stock_code, 'period': period, 'metric': metric,
                           'claimed_value': claimed_value, 'tolerance': tolerance},
           'ok' if ok else 'mismatch', [fact['evidence_id']])
    return {
        'data': {'verdict': 'match' if ok else 'mismatch', 'metric': metric,
                 'claimed_value': claimed_value, 'actual_value': actual, 'difference': round(diff, 2),
                 'tolerance': tolerance, 'unit': fact.get('unit')},
        'evidence': {'evidence_id': fact['evidence_id'], 'page': fact['page'],
                     'snippet': fact['snippet'], 'bbox': fact.get('bbox')},
        'meta': {'stock_code': stock_code, 'period': period},
        'quality': {'status': 'pass' if ok else 'fail'},
    }


@mcp.tool()
def get_quality_report(stock_code: str, period: str) -> Dict[str, Any]:
    """返回勾稽校验与数据质量结果：哪些校验通过、哪些失败、哪些数值缺失。"""
    try:
        ds = load_dataset(BASE, stock_code, period)
    except FileNotFoundError as e:
        return _err('DATASET_NOT_FOUND', str(e))
    checks = ds['checks']
    counts = {'pass': 0, 'warning': 0, 'fail': 0}
    for c in checks:
        counts[c.get('status', 'warning')] = counts.get(c.get('status', 'warning'), 0) + 1
    _audit('get_quality_report', {'stock_code': stock_code, 'period': period}, 'ok')
    return {'data': {'checks': checks, 'counts': counts}, 'meta': {'stock_code': stock_code, 'period': period},
            'quality': {'status': 'fail' if counts['fail'] else ('warning' if counts['warning'] else 'pass')}}


def main():
    mcp.run()


if __name__ == '__main__':
    main()
