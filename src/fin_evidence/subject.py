# -*- coding: utf-8 -*-
"""科目拦截：指标、报表与科目别名必须同时匹配。

数值真、页码真，但答成另一个科目，仍然是错答案。这里把这条规则从
抽取阶段延伸到工具返回阶段，特别是 structured（无页码）数据。
"""

import re
from typing import Any, Dict

from .mapping import METRICS
from .models import Quality

BY_KEY = {m.key: m for m in METRICS}

# 高频指标一旦科目/报表不对，用户最容易直接拿错数。
HIGH_FREQUENCY = {
    'revenue', 'total_revenue', 'net_profit', 'net_profit_parent',
    'operating_profit', 'cfo', 'cash', 'total_assets', 'total_liabilities',
    'total_equity',
}


def _norm(text: str) -> str:
    text = re.sub(r'\s+', '', text or '')
    text = re.sub(r'[（(][^（）()]*[）)]?', '', text)
    text = re.sub(r'^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+[、.]|（\d+）|其中：|加：|减：)', '', text)
    text = text.replace('：', '').replace(':', '').replace('/', '')
    text = re.sub(r'(?:[一二三四五六七八九十]+、)?\d+(?:[、.]\d+)*$', '', text)
    return text.strip('（）()')


def evaluate(metric: str, statement: str, item_raw: str = '',
             existing: Dict[str, Any] | None = None,
             source_type: str = 'annual_report_pdf') -> Quality:
    """返回科目拦截结果；fail 时调用方必须拒绝返回该数字。"""
    definition = BY_KEY.get(metric)
    checks = []
    messages = []
    failed = False

    if not definition:
        return Quality(status='fail', checks=['metric_known'],
                       messages=['未知指标：%s' % metric])

    if statement and definition.statement and statement != definition.statement:
        failed = True
        messages.append('指标 %s 预期在 %s，实际来自 %s' % (
            metric, definition.statement, statement))
    else:
        checks.append('statement_match')

    if metric in HIGH_FREQUENCY and not statement:
        failed = True
        messages.append('高频指标 %s 缺少报表归属，不能放行' % metric)

    existing = existing or {}
    if existing.get('status') == 'fail':
        failed = True
        messages.append('已有科目校验失败：%s' % '；'.join(existing.get('messages', [])))

    # structured 数据的 item_raw 是 API 字段名，不做中文别名匹配；
    # verified 数据必须通过中文别名匹配。
    if source_type != 'structured_api' and item_raw:
        aliases = {_norm(a) for a in definition.aliases}
        if _norm(item_raw) not in aliases:
            failed = True
            messages.append('科目名与指标别名不匹配：%s' % item_raw)
        else:
            checks.append('alias_match')

    return Quality(status='fail' if failed else 'pass',
                   checks=checks if not failed else [],
                   messages=messages)


def evaluate_fact(fact: Dict[str, Any]) -> Quality:
    return evaluate(
        metric=fact.get('metric', ''),
        statement=fact.get('statement', ''),
        item_raw=fact.get('item_raw', ''),
        existing=fact.get('subject_check'),
        source_type=fact.get('source_type', 'annual_report_pdf'),
    )
