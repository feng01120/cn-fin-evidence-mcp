# -*- coding: utf-8 -*-
"""已复核重大追溯的读取与门禁判定。

`data/material_review.json` 是唯一的例外清单：只有
`review.verdict=confirmed_restatement` 且 `review.extraction_error=false`
的指标，才允许把 `restatement_material` 判为 `pass_with_restatement`。
未进入清单的 material 差异仍然 fail。
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


@lru_cache(maxsize=32)
def _load(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    items = doc.get('items') if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return {}
    out = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        review = item.get('review') or {}
        if review.get('verdict') != 'confirmed_restatement':
            continue
        if review.get('extraction_error') is not False:
            continue
        item_id = item.get('id')
        if item_id:
            out[item_id] = item
    return out


def ledger_path(base: Path) -> Path:
    return Path(base) / 'material_review.json'


def reviewed_items(base: Path) -> Dict[str, Any]:
    return _load(str(ledger_path(base).resolve()))


def reviewed_ids(base: Path) -> Set[str]:
    return set(reviewed_items(base))


def item_for(base: Path, code: str, period: str, metric: str) -> Optional[Dict[str, Any]]:
    return reviewed_items(base).get('%s/%s/%s' % (code, period, metric))


def is_confirmed(base: Path, code: str, period: str, metric: str) -> bool:
    return item_for(base, code, period, metric) is not None


def material_metrics(base: Path, code: str, period: str,
                     metrics: Iterable[str]) -> Dict[str, List[str]]:
    """Split material metrics into reviewed and unreviewed.

    The caller passes the set of metrics that are actually marked
    `restatement_material` in the dataset; this function never invents one.
    """
    ordered = sorted(set(metrics))
    reviewed = [m for m in ordered if is_confirmed(base, code, period, m)]
    unreviewed = [m for m in ordered if m not in reviewed]
    return {'reviewed': reviewed, 'unreviewed': unreviewed}


def summary(base: Path) -> Dict[str, Any]:
    items = reviewed_items(base)
    return {
        'reviewed_count': len(items),
        'reviewed_ids': sorted(items),
        'ledger': str(ledger_path(base)),
    }
