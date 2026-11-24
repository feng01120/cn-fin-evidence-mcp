# -*- coding: utf-8 -*-
"""本地数据集读写与审计日志。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import CheckResult, DatasetMeta, Evidence, Ratio, RawRow


def dataset_dir(base: Path, code: str, period: str) -> Path:
    return Path(base) / code / period


def save_dataset(base: Path, facts: List[Evidence], rows: List[RawRow],
                 meta: DatasetMeta, ratios: List[Ratio], checks: List[CheckResult]) -> Path:
    d = dataset_dir(base, meta.company.code, meta.period)
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


def load_dataset(base: Path, code: str, period: str) -> Dict[str, Any]:
    d = dataset_dir(base, code, period)
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
    out = []
    if not base.exists():
        return out
    for code_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for period_dir in sorted(p for p in code_dir.iterdir() if p.is_dir()):
            meta = _read(period_dir / 'meta.json', None)
            if meta:
                out.append({'code': code_dir.name, 'period': period_dir.name,
                            'company': meta.get('company', {}), 'fact_count': meta.get('fact_count'),
                            'source_file': meta.get('source_file')})
    return out


def find_fact(dataset: Dict[str, Any], evidence_id: str) -> Optional[Dict[str, Any]]:
    for f in dataset.get('facts', []):
        if f.get('evidence_id') == evidence_id:
            return f
    return None


def append_audit(base: Path, record: Dict[str, Any]) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    record = {'time': datetime.now().astimezone().isoformat(timespec='seconds'), **record}
    with (base / 'audit.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
