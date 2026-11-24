import argparse, json, re, hashlib, sys
from pathlib import Path
import pymupdf

ap = argparse.ArgumentParser(description='审计数据集：证据片段、页码、bbox、哈希与比率输入')
ap.add_argument('--data', default='data')
ap.add_argument('--pdf-dir', default='data/raw')
args = ap.parse_args()
BASE = Path(args.data)
PDFS = {}
for meta_path in sorted(BASE.glob('*/*/meta.json')):
    meta0 = json.loads(meta_path.read_text(encoding='utf-8'))
    code, period = meta0['company']['code'], meta0['period']
    for name in (meta0.get('source_file'), '%s_%s.pdf' % (code, period)):
        if name and (Path(args.pdf_dir) / name).exists():
            PDFS[(code, period)] = Path(args.pdf_dir) / name
            break
if not PDFS:
    print('未找到 PDF，请用 --pdf-dir 指向含年报 PDF 的目录（文件名见 meta.json 的 source_file）')
    sys.exit(2)
ALLOWED = {'合并资产负债表','合并利润表','合并现金流量表'}
errors, warnings = [], []
stats = {}

def norm(s): return re.sub(r'\s+', '', s or '')

for (code, period), pdf_path in PDFS.items():
    d = BASE / code / period
    meta = json.loads((d/'meta.json').read_text(encoding='utf-8'))
    facts = json.loads((d/'facts.json').read_text(encoding='utf-8'))
    rows = json.loads((d/'rows.json').read_text(encoding='utf-8'))
    ratios = json.loads((d/'ratios.json').read_text(encoding='utf-8'))
    checks = json.loads((d/'checks.json').read_text(encoding='utf-8'))
    assert pdf_path.exists(), f'PDF missing {pdf_path}'
    doc = pymupdf.open(pdf_path)
    pages = {i+1: doc[i] for i in range(doc.page_count)}
    text_by_page = {p: norm(pg.get_text()) for p, pg in pages.items()}
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if meta['source_sha256'] != sha: errors.append(f'{code} sha mismatch')
    if meta['page_count'] != doc.page_count: errors.append(f'{code} page_count mismatch')
    if meta['fact_count'] != len(facts): errors.append(f'{code} fact_count mismatch')
    if meta['row_count'] != len(rows): errors.append(f'{code} row_count mismatch')
    ids = [f['evidence_id'] for f in facts]
    if len(ids) != len(set(ids)): errors.append(f'{code} duplicate evidence ids')
    for f in facts:
        if f['evidence_id'] != f"{code}-{period}-{f['metric']}": errors.append(f'{code} bad id {f["evidence_id"]}')
        if f['company']['code'] != code or f['period'] != period: errors.append(f'{code}/{f["metric"]} meta mismatch')
        if not f.get('unit'): errors.append(f'{code}/{f["metric"]} empty unit')
        p = f.get('page')
        if p not in pages: errors.append(f'{code}/{f["metric"]} page {p} out of range'); continue
        sn = norm(f['snippet'])
        if sn not in text_by_page[p]:
            errors.append(f'{code}/{f["metric"]} snippet not on page {p}: {f["snippet"][:80]}')
        bb = f.get('bbox')
        if bb:
            r = pages[p].rect
            if not (bb['x0'] < bb['x1'] and bb['y0'] < bb['y1']): errors.append(f'{code}/{f["metric"]} bad bbox order')
            if bb['x0'] < -1 or bb['y0'] < -1 or bb['x1'] > r.width+1 or bb['y1'] > r.height+1:
                errors.append(f'{code}/{f["metric"]} bbox outside page: {bb} page {r.width}x{r.height}')
            if bb['y1'] - bb['y0'] <= 0 or bb['x1'] - bb['x0'] <= 0:
                errors.append(f'{code}/{f["metric"]} bbox has zero area: {bb}')
        if f.get('value') is None and not f.get('zero_type'): errors.append(f'{code}/{f["metric"]} null value without zero_type')
        for key in ('value', 'prior_value'):
            if f.get(key) is not None and f'{f[key]:,.2f}' not in f['snippet']:
                errors.append(f'{code}/{f["metric"]} {key} not in snippet: {f[key]}')
    for r in rows:
        if r['statement'] not in ALLOWED: errors.append(f'{code} row bad statement {r["statement"]}')
        if r['page'] not in pages: errors.append(f'{code} row page out of range')
        elif norm(r['snippet']) not in text_by_page[r['page']]: errors.append(f'{code} row snippet not found p{r["page"]}: {r["item"]}')
        elif r['value'] is not None and f'{r["value"]:,.2f}' not in r['snippet']:
            errors.append(f'{code} row value not in snippet p{r["page"]}: {r["item"]}')
        bb = r.get('bbox')
        if bb:
            rect = pages[r['page']].rect
            if not (bb['x0'] < bb['x1'] and bb['y0'] < bb['y1']):
                errors.append(f'{code} row bad bbox order p{r["page"]}: {r["item"]}')
            if bb['x0'] < -1 or bb['y0'] < -1 or bb['x1'] > rect.width+1 or bb['y1'] > rect.height+1:
                errors.append(f'{code} row bbox outside page p{r["page"]}: {r["item"]}')
    by_metric = {f['metric']: f for f in facts}
    for rt in ratios:
        if not rt.get('formula'): errors.append(f'{code}/{rt["ratio"]} no formula')
        if rt.get('value') is None: warnings.append(f'{code}/{rt["ratio"]} value None')
        for inp in rt.get('inputs', []):
            if inp.get('evidence_id') not in ids: errors.append(f'{code}/{rt["ratio"]} input evidence missing')
            elif by_metric.get(inp['metric'],{}).get('value') != inp['value']: errors.append(f'{code}/{rt["ratio"]} input value mismatch {inp["metric"]}')
        for eid in rt.get('evidence', []):
            if eid not in ids: errors.append(f'{code}/{rt["ratio"]} evidence missing {eid}')
    for c in checks:
        if c['status'] not in ('pass','warning','fail'): errors.append(f'{code} bad check status')
        if c['check'] != 'zero_type':
            for eid in c.get('evidence', []):
                if eid not in ids: errors.append(f'{code}/{c["check"]} evidence missing {eid}')
    stats[code] = {'pages': doc.page_count, 'facts': len(facts), 'rows': len(rows), 'ratios': len(ratios),
                   'checks': {s: sum(1 for c in checks if c['status']==s) for s in ('pass','warning','fail')},
                   'snippet_ok': sum(1 for f in facts if norm(f['snippet']) in text_by_page.get(f['page'],''))}

print(json.dumps({'stats': stats, 'errors': errors, 'warnings': warnings}, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
