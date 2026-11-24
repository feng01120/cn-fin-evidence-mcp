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


def load_dataset(base: Path, code: str, period: str, announce_date: str = '') -> Dict[str, Any]:
    d = dataset_dir(base, code, period, announce_date)
    if not (d / 'meta.json').exists():
        raise FileNotFoundError('%s/%s 数据集不存在' % (code, period))
    return {
        'meta': _read(d / 'meta.json', {}),
        'facts': _read(d / 'facts.json', []),
        'rows': _read(d / 'rows.json', []),
        'ratios': _read(d / 'ratios.json', []),
        'checks': _read(d / 'checks.json', []),
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
    return None


def find_fact_by_metric(dataset: Dict[str, Any], metric: str) -> Optional[Dict[str, Any]]:
    for f in dataset.get('facts', []):
        if f.get('metric') == metric:
            return f
    return None


def append_audit(base: Path, record: Dict[str, Any]) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    record = {'time': datetime.now().astimezone().isoformat(timespec='seconds'), **record}
    with (base / 'audit.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
