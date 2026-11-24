# -*- coding: utf-8 -*-
"""本地数据集读写与审计日志。"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import CheckResult, DatasetMeta, Evidence, Ratio, RawRow

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def normalize_report_date(period: str) -> str:
    period = str(period)
    return period if DATE_RE.match(period) else '%s-12-31' % period


def _candidates(base: Path, code: str, period: str, announce_date: str = '') -> List[Path]:
    base = Path(base)
    report_date = normalize_report_date(period)
    out: List[Path] = []
    if announce_date:
        out += [base / code / report_date / announce_date, base / code / str(period) / announce_date]
    out += [base / code / report_date, base / code / str(period)]
    return out


def dataset_dir(base: Path, code: str, period: str, announce_date: str = '') -> Path:
    """优先按 (report_date, announce_date) 定位；兼容旧的 code/period 目录。"""
    base = Path(base)
    report_date = normalize_report_date(period)
    new_parent = base / code / report_date
    old = base / code / str(period)
    if announce_date:
        for exact in (new_parent / announce_date, old / announce_date):
            if (exact / 'meta.json').exists():
                return exact
    if new_parent.exists():
        subs = [p for p in new_parent.iterdir() if p.is_dir() and (p / 'meta.json').exists()]
        if subs:
            if announce_date:
                for p in subs:
                    if p.name == announce_date:
                        return p
            return sorted(subs, key=lambda p: p.name)[-1]
    if (old / 'meta.json').exists():
        return old
    return new_parent / announce_date if announce_date else old

def save_dataset(base: Path, facts: List[Evidence], rows: List[RawRow],
                 meta: DatasetMeta, ratios: List[Ratio], checks: List[CheckResult]) -> Path:
    base = Path(base)
    if meta.report_date and meta.announce_date:
        d = base / meta.company.code / meta.report_date / meta.announce_date
    else:
        d = base / meta.company.code / meta.period
    d.mkdir(parents=True, exist_ok=True)
    (d / 'facts.json').write_text(json.dumps([f.model_dump(mode='json') for f in facts],
                                             ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'rows.json').write_text(json.dumps([r.model_dump(mode='json') for r in rows],
                                            ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'ratios.json').write_text(json.dumps([r.model_dump(mode='json') for r in ratios],
                                              ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'checks.json').write_text(json.dumps([c.model_dump(mode='json') for c in checks],
                                              ensure_ascii=False, indent=2), encoding='utf-8')
    (d / 'meta.json').write_text(json.dumps(meta.model_dump(mode='json'), ensure_ascii=False, indent=2),
                                 encoding='utf-8')
    return d


def _read(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def structured_fact(meta: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """把结构化指标转成事实对象；页码/片段显式为空，quality=warning。"""
    company = meta.get('company', {})
    code = company.get('code', '')
    period = meta.get('period', '')
    metric = entry.get('metric', '')
    quality = entry.get('quality') or {
        'status': 'warning', 'checks': ['no_page_evidence'],
        'messages': ['结构化接口数据，无年报页码证据'],
    }
    return {
        'evidence_id': '%s-%s-%s-structured' % (code, period, metric),
        'company': company,
        'report_date': meta.get('report_date', ''),
        'announce_date': meta.get('announce_date', ''),
        'evidence_level': 'structured',
        'source_type': 'structured_api',
        'source_url': entry.get('source_url'),
        'period': period,
        'metric': metric,
        'metric_name': entry.get('metric_name', metric),
        'value': entry.get('value'),
        'prior_value': None,
        'unit': entry.get('unit', '元'),
        'page': None,
        'printed_page': None,
        'snippet': '',
        'bbox': None,
        'source_file': 'eastmoney:%s' % entry.get('report_name', ''),
        'statement': entry.get('statement', ''),
        'item_raw': entry.get('api_field', ''),
        'note': ((entry.get('quality') or {}).get('messages') or [''])[0],
        'value_type': 'disclosed',
        'zero_type': None,
        'formula': None,
        'inputs': None,
        'quality': quality,
        'subject_check': {
            'status': 'pass', 'checks': ['api_field_mapped'], 'messages': [],
        },
        'cross_check': entry.get('cross_check'),
    }


def load_dataset(base: Path, code: str, period: str, announce_date: str = '') -> Dict[str, Any]:
    d = dataset_dir(base, code, period, announce_date)
    if not (d / 'meta.json').exists():
        raise FileNotFoundError('%s/%s 数据集不存在' % (code, period))
    meta = _read(d / 'meta.json', {})
    structured_doc = _read(d / 'structured.json', {})
    structured = structured_doc.get('metrics', {}) if isinstance(structured_doc, dict) else {}
    structured_facts = [structured_fact(meta, e) for e in structured.values()]
    sina_doc = _read(d / 'sina.json', {})
    return {
        'meta': meta,
        'facts': _read(d / 'facts.json', []),
        'rows': _read(d / 'rows.json', []),
        'ratios': _read(d / 'ratios.json', []),
        'checks': _read(d / 'checks.json', []),
        'structured': structured_doc,
        'structured_facts': structured_facts,
        'sina': sina_doc,
        'second_source': sina_doc.get('comparison', {}) if isinstance(sina_doc, dict) else {},
        'dir': str(d),
    }


def list_datasets(base: Path) -> List[Dict[str, Any]]:
    base = Path(base)
    if not base.exists():
        return []
    metas = list(base.glob('*/*/meta.json')) + list(base.glob('*/*/*/meta.json'))
    records: Dict[tuple, Dict[str, Any]] = {}
    for meta_path in sorted(set(metas)):
        rel = meta_path.relative_to(base)
        if any(part == 'raw' or part.startswith('_') for part in rel.parts):
            continue
        meta = _read(meta_path, None)
        if not meta:
            continue
        d = meta_path.parent
        code = meta.get('company', {}).get('code', d.parent.name)
        report_date = meta.get('report_date') or normalize_report_date(meta.get('period', ''))
        structured_doc = _read(d / 'structured.json', {})
        structured_count = len(structured_doc.get('metrics', {})) if isinstance(structured_doc, dict) else 0
        sina_doc = _read(d / 'sina.json', {})
        sina_count = len(sina_doc.get('metrics', {})) if isinstance(sina_doc, dict) else 0
        item = {
            'code': meta.get('company', {}).get('code', d.parent.name),
            'period': meta.get('period', ''),
            'report_date': meta.get('report_date', ''),
            'announce_date': meta.get('announce_date', ''),
            'dataset_id': meta.get('dataset_id', ''),
            'evidence_level': meta.get('evidence_level', 'verified'),
            'company': meta.get('company', {}),
            'fact_count': meta.get('fact_count'),
            'row_count': meta.get('row_count'),
            'coverage_score': meta.get('coverage_score', 0),
            'quality_gate': meta.get('quality_gate', ''),
            'structured_count': structured_count,
            'second_source_count': sina_count,
            'path': str(d),
            'source_file': meta.get('source_file'),
        }
        # 同一 code + 报告期只保留新结构（带 announce_date）的一条，避免旧目录重复计数。
        key = (code, report_date)
        if key not in records or meta.get('announce_date'):
            records[key] = item
    return sorted(records.values(), key=lambda x: (x['code'], x['report_date']))


def find_fact(dataset: Dict[str, Any], evidence_id: str) -> Optional[Dict[str, Any]]:
    for f in dataset.get('facts', []):
        if f.get('evidence_id') == evidence_id:
            return f
    for f in dataset.get('structured_facts', []):
        if f.get('evidence_id') == evidence_id:
            return f
    return None


def find_fact_by_metric(dataset: Dict[str, Any], metric: str) -> Optional[Dict[str, Any]]:
    for f in dataset.get('facts', []):
        if f.get('metric') == metric:
            return f
    return None


def find_structured_fact(dataset: Dict[str, Any], metric: str) -> Optional[Dict[str, Any]]:
    for f in dataset.get('structured_facts', []):
        if f.get('metric') == metric:
            return f
    return None


def append_audit(base: Path, record: Dict[str, Any]) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    record = {'time': datetime.now().astimezone().isoformat(timespec='seconds'), **record}
    with (base / 'audit.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
