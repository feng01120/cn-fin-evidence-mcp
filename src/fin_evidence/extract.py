# -*- coding: utf-8 -*-
"""从年报 PDF 还原报表行，并按科目锚点提取带页码与原文片段的证据。"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from .mapping import BY_STATEMENT, STOP_TITLES, MetricDef
from .models import BBox, Company, DatasetMeta, Evidence, Quality, RawRow

VALUE_RE = re.compile(r'^-?\d{1,3}(,\d{3})*\.\d{2}$')
PAGE_NO_RE = re.compile(r'^(\d+)\s*/\s*(\d+)$')
NUMBERING_RE = re.compile(r'^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+\.|（\d+）|其中：|加：|减：|其中:)')
PAREN_RE = re.compile(r'（[^（）]*）|\([^()]*\)')


@dataclass
class Word:
    x0: float
    x1: float
    text: str
    y: float
    y1: float = 0.0


@dataclass
class Line:
    page: int
    y: float
    words: List[Word]
    item: str
    note: str
    current: List[Word]
    prior: List[Word]
    raw: str
    printed_page: Optional[int] = None

    @property
    def has_value(self) -> bool:
        return bool(self.current or self.prior)

    @property
    def bbox(self) -> Optional[BBox]:
        if not self.words:
            return None
        return BBox(x0=min(w.x0 for w in self.words), y0=min(w.y for w in self.words),
                    x1=max(w.x1 for w in self.words), y1=max(w.y1 for w in self.words))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def normalize_label(text: str) -> str:
    text = re.sub(r'\s+', '', text)
    text = PAREN_RE.sub('', text)
    text = NUMBERING_RE.sub('', text)
    text = text.replace('：', '').replace(':', '')
    return text.strip()


def page_lines(page, page_index: int) -> List[Line]:
    words = sorted(page.get_text('words'), key=lambda w: (round(w[1], 1), w[0]))
    grouped: List[List[Word]] = []
    current: List[Word] = []
    base: Optional[float] = None
    for x0, y0, x1, y1, text, *_ in words:
        w = Word(x0=x0, x1=x1, text=text, y=y0, y1=y1)
        if base is None or abs(y0 - base) <= 4.0:
            current.append(w)
            if base is None:
                base = y0
        else:
            grouped.append(current)
            current = [w]
            base = y0
    if current:
        grouped.append(current)

    printed = None
    for line_words in grouped:
        joined = ''.join(w.text for w in line_words)
        m = PAGE_NO_RE.match(joined.strip())
        if m:
            printed = int(m.group(1))
            break

    lines: List[Line] = []
    for ws in grouped:
        ws = sorted(ws, key=lambda w: w.x0)
        item = ''.join(w.text for w in ws if w.x0 < 220)
        note = ''.join(w.text for w in ws if 220 <= w.x0 < 290)
        cur = [w for w in ws if 290 <= w.x0 < 425 and VALUE_RE.match(w.text)]
        pri = [w for w in ws if w.x0 >= 425 and VALUE_RE.match(w.text)]
        raw = ''.join(w.text for w in ws)
        if raw.strip():
            lines.append(Line(page=page_index + 1, y=ws[0].y, words=ws, item=item.strip(),
                              note=note.strip(), current=cur, prior=pri, raw=raw,
                              printed_page=printed))
    return lines


def _statement_start(doc, title: str, required: Sequence[str]) -> Optional[int]:
    for i in range(doc.page_count):
        text = doc[i].get_text()
        if title in text and all(k in text for k in required):
            return i
    return None


def statement_ranges(doc, title: str, lines_by_page: Dict[int, List[Line]]) -> List[Tuple[int, List[Line]]]:
    """返回报表覆盖的行区间；止页只取到下一张报表标题之前，保留同页的合并报表尾部。"""
    start = _statement_start(doc, title, ('单位：元', '项目'))
    if start is None:
        return []
    stop = doc.page_count
    stop_title = ''
    for candidate in STOP_TITLES.get(title, ()):
        idx = _statement_start(doc, candidate, ('单位：元', '项目'))
        if idx is not None and idx > start:
            stop = min(stop, idx)
            stop_title = candidate
            break
    segments: List[Tuple[int, List[Line]]] = []
    for page in range(start, min(stop, doc.page_count - 1) + 1):
        lines = lines_by_page.get(page, [])
        begin = 0
        end = len(lines)
        if page == start:
            for j, line in enumerate(lines):
                if title in line.raw:
                    begin = j + 1
                    break
        if page == stop and stop_title:
            for j, line in enumerate(lines):
                if stop_title in line.raw:
                    end = j
                    break
        segments.append((page, lines[begin:end]))
    return segments


def _value_in(lines: Sequence[Line]) -> Tuple[Optional[float], Optional[float], List[Word], Optional[str]]:
    note = None
    value_words: List[Word] = []
    cur = prior = None
    for line in lines:
        if line.note and not note:
            note = line.note
        for w in line.current + line.prior:
            if w not in value_words:
                value_words.append(w)
        if line.current and cur is None:
            cur = float(line.current[0].text.replace(',', ''))
        if line.prior and prior is None:
            prior = float(line.prior[0].text.replace(',', ''))
    return cur, prior, value_words, note


def find_metric(segments: Sequence[Tuple[int, List[Line]]],
                metric: MetricDef) -> Optional[Tuple[float, float, Line, List[Line], List[Word], str]]:
    aliases = {normalize_label(a) for a in metric.aliases}
    for page, lines in segments:
        for i, line in enumerate(lines):
            for s in range(max(0, i - 2), i + 1):
                for e in range(i, min(len(lines), i + 3)):
                    window = lines[s:e + 1]
                    combined = normalize_label(''.join(x.item for x in window))
                    if combined not in aliases:
                        continue
                    value_line = None
                    for j in range(e, s - 1, -1):
                        if lines[j].current or lines[j].prior:
                            value_line = j
                            break
                    if value_line is None:
                        continue
                    value, prior, value_words, note = _value_in([lines[value_line]])
                    if value is None and prior is None:
                        continue
                    return value, prior, lines[value_line], window, value_words, note or ''
    return None


def _snippet(page, window: Sequence[Line], anchor: Line, value_words: Sequence[Word]) -> str:
    """返回连续原文片段：按区域从 PDF 内容流取文本，并校验其确实出现在整页文本中。"""
    boxes = [x.bbox for x in window if x.bbox is not None]
    if anchor.bbox is not None:
        boxes.append(anchor.bbox)
    if not boxes:
        return anchor.raw[:400]
    x0 = min(b.x0 for b in boxes)
    y0 = min(b.y0 for b in boxes)
    x1 = max(b.x1 for b in boxes)
    y1 = max(b.y1 for b in boxes)
    rect = pymupdf.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
    text = re.sub(r'\s+', ' ', page.get_text('text', clip=rect)).strip()
    compact = re.sub(r'\s+', '', text)
    full = re.sub(r'\s+', '', page.get_text())
    if compact and compact in full:
        return text[:400]
    # 兜底：围绕数值在整页文本中截取连续窗口
    for w in sorted(value_words, key=lambda x: x.x0):
        token = re.sub(r'\s+', '', w.text)
        idx = full.find(token)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(full), idx + len(token) + 120)
            return full[start:end][:400]
    return compact[:400] or anchor.raw[:400]


def _bbox(window: Sequence[Line], value_words: Sequence[Word]) -> Optional[BBox]:
    words = [w for line in window for w in line.words] + list(value_words)
    if not words:
        return None
    return BBox(x0=min(w.x0 for w in words), y0=min(w.y for w in words),
                x1=max(w.x1 for w in words), y1=max(w.y1 for w in words))


def extract_metrics(doc, company: Company, period: str, source_file: str) -> List[Evidence]:
    lines_by_page = {i: page_lines(doc[i], i) for i in range(doc.page_count)}
    facts: List[Evidence] = []
    for statement, metrics in BY_STATEMENT.items():
        segments = statement_ranges(doc, statement, lines_by_page)
        if not segments:
            continue
        for metric in metrics:
            found = find_metric(segments, metric)
            if not found:
                continue
            value, prior, anchor, window, value_words, note = found
            zero_type = None
            if value is None:
                zero_type = '未披露'
            evidence_id = '%s-%s-%s' % (company.code, period, metric.key)
            quality = Quality(status='pass' if value is not None else 'warning',
                              checks=['value_present'] if value is not None else [],
                              messages=[] if value is not None else ['本期数值为空，按未披露处理，不参与比率计算'])
            facts.append(Evidence(
                evidence_id=evidence_id, company=company, period=period, metric=metric.key,
                metric_name=metric.name, value=value, prior_value=prior, unit=metric.unit,
                page=anchor.page, printed_page=anchor.printed_page,
                snippet=_snippet(doc[anchor.page - 1], window, anchor, value_words),
                bbox=_bbox(window, value_words), source_file=source_file, statement=statement,
                item_raw=normalize_label(''.join(x.item for x in window)) or metric.name,
                note=note or None, zero_type=zero_type, quality=quality,
            ))
    return facts


def extract_rows(doc, statement: str, segments: Sequence[Tuple[int, List[Line]]]) -> List[RawRow]:
    rows: List[RawRow] = []
    for page, lines in segments:
        for i, line in enumerate(lines):
            if not line.has_value:
                continue
            if '项目' in line.raw and '附注' in line.raw:
                continue
            prefix = []
            # 只有“仅数值行”才向上拼接标签；非空科目行不能再吞掉上一行的残片
            if not line.item and i - 1 >= 0:
                prev = lines[i - 1]
                if prev.item and not prev.has_value and not prev.item.endswith('：'):
                    prefix = [prev.item]
            item = ''.join(prefix) + line.item
            suffix = ''
            if i + 1 < len(lines) and lines[i + 1].item and not lines[i + 1].has_value \
                    and lines[i + 1].y - line.y <= 10:
                suffix = lines[i + 1].item
            item = item + suffix
            complete = bool(item)
            value, prior, value_words, note = _value_in([line])
            rows.append(RawRow(page=page + 1, statement=statement, item=item or '（未还原）',
                               note=note or None, value=value, prior_value=prior,
                               snippet=line.raw[:300], bbox=_bbox([line], value_words),
                               complete=complete))
    return rows


def build_dataset(pdf_path: str, company: Company, period: str) -> Tuple[List[Evidence], List[RawRow], DatasetMeta]:
    path = Path(pdf_path)
    doc = pymupdf.open(str(path))
    lines_by_page = {i: page_lines(doc[i], i) for i in range(doc.page_count)}
    facts = extract_metrics(doc, company, period, path.name)
    rows: List[RawRow] = []
    for statement in BY_STATEMENT:
        segments = statement_ranges(doc, statement, lines_by_page)
        rows.extend(extract_rows(doc, statement, segments))
    meta = DatasetMeta(
        company=company, period=period, source_file=path.name, source_sha256=_sha256(path),
        page_count=doc.page_count, extracted_at=datetime.now().astimezone().isoformat(timespec='seconds'),
        statements=list(BY_STATEMENT.keys()), fact_count=len(facts), row_count=len(rows),
    )
    return facts, rows, meta
