# -*- coding: utf-8 -*-
"""审计新契约数据集：哈希、页数、证据片段、bbox、数值原文、勾稽与比率引用。"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fin_evidence.store import list_datasets  # noqa: E402

BASE = ROOT / 'data'
PDF_DIR = BASE / 'raw'
ALLOWED_STATEMENTS = {'合并资产负债表', '合并利润表', '合并现金流量表'}


def norm(s: str) -> str:
    return re.sub(r'[\s\u200a\u200b\xa0]+', '', s or '')


def variants(value: float):
    out = set()
    av = abs(float(value))
    for p in range(7):
        s = f'{av:,.{p}f}'
        if abs(float(s.replace(',', '')) - av) <= 1e-9:
            out.add(s)
    if value < 0:
        for s in list(out):
            out.add('(' + s + ')')
            out.add('（' + s + '）')
            out.add('-' + s)
    return out


def main() -> int:
    errors, warnings = [], []
    datasets = list_datasets(BASE)
    if len(datasets) != 60:
        warnings.append(f'数据集数量为 {len(datasets)}，预期 60')
    keys = []
    pdf_cache = {}
    for ds in datasets:
        d = Path(ds['path'])
        meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
        facts = json.loads((d / 'facts.json').read_text(encoding='utf-8'))
        rows = json.loads((d / 'rows.json').read_text(encoding='utf-8'))
        ratios = json.loads((d / 'ratios.json').read_text(encoding='utf-8'))
        checks = json.loads((d / 'checks.json').read_text(encoding='utf-8'))
        code, period = meta['company']['code'], meta['period']
        keys.append((code, meta.get('report_date')))
        pdf = PDF_DIR / meta['source_file']
        if not pdf.exists():
            errors.append(f'{code}/{period}: PDF 缺失 {pdf}')
            continue
        if pdf not in pdf_cache:
            pdf_cache[pdf] = pymupdf.open(str(pdf))
        doc = pdf_cache[pdf]
        text = {i + 1: norm(doc[i].get_text()) for i in range(doc.page_count)}
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if meta.get('source_sha256') != sha:
            errors.append(f'{code}/{period}: source_sha256 不匹配')
        if meta.get('page_count') != doc.page_count:
            errors.append(f'{code}/{period}: page_count 不匹配')
        if meta.get('fact_count') != len(facts):
            errors.append(f'{code}/{period}: fact_count 不匹配')
        if meta.get('row_count') != len(rows):
            errors.append(f'{code}/{period}: row_count 不匹配')
        ids = [f['evidence_id'] for f in facts]
        if len(ids) != len(set(ids)):
            errors.append(f'{code}/{period}: evidence_id 重复')
        metrics = [f['metric'] for f in facts]
        if len(metrics) != len(set(metrics)):
            errors.append(f'{code}/{period}: metric 重复')
        if meta.get('evidence_level') not in ('verified', 'structured'):
            errors.append(f'{code}/{period}: evidence_level 非法')
        for f in facts:
            mid = f'{code}/{period}/{f["metric"]}'
            if f['company']['code'] != code or f['period'] != period:
                errors.append(f'{mid}: 公司或期间不一致')
            if not f.get('unit'):
                errors.append(f'{mid}: unit 为空')
            p = f.get('page')
            if p not in text:
                errors.append(f'{mid}: page {p} 超出范围'); continue
            if norm(f.get('snippet', '')) not in text[p]:
                errors.append(f'{mid}: snippet 不在第 {p} 页')
            bb = f.get('bbox')
            if bb:
                rect = doc[p - 1].rect
                if not (bb['x0'] < bb['x1'] and bb['y0'] < bb['y1']):
                    errors.append(f'{mid}: bbox 顺序错误')
                if bb['x0'] < -1 or bb['y0'] < -1 or bb['x1'] > rect.width + 1 or bb['y1'] > rect.height + 1:
                    errors.append(f'{mid}: bbox 超出页面')
            if f.get('value') is None and not f.get('zero_type'):
                errors.append(f'{mid}: 空值未标记 zero_type')
            for k in ('value', 'prior_value'):
                v = f.get(k)
                if v is not None and not any(x in norm(f['snippet']) for x in variants(float(v))):
                    errors.append(f'{mid}: {k}={v} 不在 snippet 原文')
        for r in rows:
            rid = f'{code}/{period}/row-p{r.get("page")}'
            if r.get('statement') not in ALLOWED_STATEMENTS:
                errors.append(f'{rid}: 非法报表 {r.get("statement")}')
            p = r.get('page')
            if p not in text:
                errors.append(f'{rid}: page 超出范围'); continue
            # 行片段会为跨行科目拼上前后行，连续性可能被 PDF 阅读顺序打断；
            # 以“科目名 + 数值”是否同时出现在该页作为行级可回查标准。
            item_ok = norm(r.get('item', '')) in text[p]
            val_ok = True
            if r.get('value') is not None:
                val_ok = any(x in text[p] for x in variants(float(r['value'])))
            if not item_ok or not val_ok:
                errors.append(f'{rid}: row item/value 不在第 {p} 页 ({r.get("item")}, {r.get("value")})')
            bb = r.get('bbox')
            if bb:
                rect = doc[p - 1].rect
                if not (bb['x0'] < bb['x1'] and bb['y0'] < bb['y1']):
                    errors.append(f'{rid}: row bbox 顺序错误')
                if bb['x0'] < -1 or bb['y0'] < -1 or bb['x1'] > rect.width + 1 or bb['y1'] > rect.height + 1:
                    errors.append(f'{rid}: row bbox 超出页面')
        fact_ids = set(ids)
        for rt in ratios:
            for eid in rt.get('evidence', []):
                if eid not in fact_ids:
                    errors.append(f'{code}/{period}/ratio-{rt.get("ratio")}: 引用不存在的 evidence {eid}')
        for c in checks:
            if c.get('status') == 'fail':
                errors.append(f'{code}/{period}/check-{c.get("check")}: {c.get("detail")}')
            elif c.get('status') == 'warning':
                warnings.append(f'{code}/{period}/check-{c.get("check")}: {c.get("detail")}')
    if len(keys) != len(set(keys)):
        errors.append('同一 (code, report_date) 存在多个数据集')
    report = {
        'datasets': len(datasets),
        'companies': len({d['code'] for d in datasets}),
        'errors': errors,
        'warnings': warnings,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'pass': not errors,
    }
    out = BASE / 'audit_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('datasets', 'companies', 'error_count',
                                              'warning_count', 'pass')}, ensure_ascii=False))
    if errors:
        print('\n'.join(errors[:20]))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
