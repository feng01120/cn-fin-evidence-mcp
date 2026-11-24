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
from fin_evidence.subject import evaluate_fact  # noqa: E402
from fin_evidence.extract import statement_unit  # noqa: E402

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
    structured_datasets = 0
    structured_metrics = 0
    structured_cross = {'pass': 0, 'restatement': 0, 'restatement_material': 0,
                        'warning': 0, 'missing': 0}
    second_datasets = 0
    second_metrics = 0
    second_cross = {'pass': 0, 'restatement': 0, 'restatement_material': 0,
                    'verified_isolated': 0, 'warning': 0, 'unverified': 0, 'missing': 0}
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
        unit_cache = {}
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
            sq = evaluate_fact(f)
            if sq.status == 'fail':
                errors.append(f'{mid}: 科目拦截失败 {sq.messages}')
            if not f.get('unit'):
                errors.append(f'{mid}: unit 为空')
            elif f.get('metric') != 'basic_eps':
                stmt = f.get('statement', '')
                if stmt not in unit_cache:
                    unit_cache[stmt] = statement_unit(doc, stmt)
                expected_unit = unit_cache[stmt]
                if f.get('unit') != expected_unit:
                    errors.append(f'{mid}: unit={f.get("unit")} 与报表单位 {expected_unit} 不一致')
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

        # structured 覆盖层：有来源、有值、无页码，质量必须显式 warning。
        sp = d / 'structured.json'
        if not sp.exists():
            errors.append(f'{code}/{period}: structured.json 缺失')
            continue
        try:
            sd = json.loads(sp.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{code}/{period}: structured.json 非法 {e}')
            continue
        sm = sd.get('metrics') if isinstance(sd, dict) else None
        if not isinstance(sm, dict) or not sm:
            errors.append(f'{code}/{period}: structured metrics 为空')
            continue
        structured_datasets += 1
        structured_metrics += len(sm)
        for metric, item in sm.items():
            sid = f'{code}/{period}/structured-{metric}'
            if item.get('metric') != metric:
                errors.append(f'{sid}: metric 字段不一致')
            try:
                float(item.get('value'))
            except (TypeError, ValueError):
                errors.append(f'{sid}: value 非数值')
            if item.get('statement') not in ALLOWED_STATEMENTS:
                errors.append(f'{sid}: 非法报表 {item.get("statement")}')
            if not item.get('unit'):
                errors.append(f'{sid}: unit 为空')
            if not str(item.get('source_url') or '').startswith('https://'):
                errors.append(f'{sid}: source_url 缺失')
            q = item.get('quality') or {}
            if q.get('status') != 'warning' or 'no_page_evidence' not in (q.get('checks') or []):
                errors.append(f'{sid}: 结构化质量未标记无页码 warning')
            cc = (item.get('cross_check') or {}).get('status', 'missing')
            structured_cross[cc] = structured_cross.get(cc, 0) + 1
            if cc in ('warning', 'restatement_material'):
                warnings.append(f'{sid}: 结构化值与年报解析值存在差异（{cc}），已保留两套口径')
            elif cc == 'missing':
                warnings.append(f'{sid}: 年报未解析出同指标，无法交叉核对')

        # 第二结构化源：只做交叉核对，不能没有来源或没有比对结果。
        second_path = d / 'sina.json'
        if not second_path.exists():
            errors.append(f'{code}/{period}: sina.json 缺失')
            continue
        try:
            sina = json.loads(second_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{code}/{period}: sina.json 非法 {e}')
            continue
        if sina.get('provider') != 'sina':
            errors.append(f'{code}/{period}: sina provider 非法')
        second_datasets += 1
        second_metrics += len(sina.get('metrics', {}))
        comparisons = sina.get('comparison') or {}
        if not comparisons:
            errors.append(f'{code}/{period}: sina comparison 为空')
        for metric, row in comparisons.items():
            sid = f'{code}/{period}/sina-{metric}'
            status = row.get('status', 'missing')
            if status not in second_cross:
                errors.append(f'{sid}: 未知比对状态 {status}')
                continue
            second_cross[status] += 1
            sina_metric = row.get('sina') or {}
            if status not in ('unverified', 'missing'):
                if not str(sina_metric.get('source_url') or '').startswith('https://'):
                    errors.append(f'{sid}: sina source_url 缺失')
                if not sina_metric.get('source_label'):
                    errors.append(f'{sid}: sina source_label 缺失')
            if status == 'verified_isolated':
                errors.append(f'{sid}: verified 与两个结构化源均不一致，疑似抽取错误')
            elif status in ('warning', 'restatement_material'):
                warnings.append(f'{sid}: 三源比对差异（{status}），保留两套口径')
    if len(keys) != len(set(keys)):
        errors.append('同一 (code, report_date) 存在多个数据集')
    report = {
        'datasets': len(datasets),
        'companies': len({d['code'] for d in datasets}),
        'structured_datasets': structured_datasets,
        'structured_metrics': structured_metrics,
        'structured_cross_check': structured_cross,
        'second_source_datasets': second_datasets,
        'second_source_metrics': second_metrics,
        'second_source_cross_check': second_cross,
        'errors': errors,
        'warnings': warnings,
        'error_count': len(errors),
        'warning_count': len(warnings),
        'pass': not errors,
    }
    out = BASE / 'audit_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('datasets', 'companies', 'structured_datasets',
                                              'structured_metrics', 'structured_cross_check',
                                              'second_source_datasets', 'second_source_metrics',
                                              'second_source_cross_check',
                                              'error_count', 'warning_count', 'pass')}, ensure_ascii=False))
    if errors:
        print('\n'.join(errors[:20]))
    return 0 if not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
