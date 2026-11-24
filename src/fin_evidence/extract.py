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

VALUE_RE = re.compile(r'^[（(]?-?\d{1,3}(,\d{3})*(?:\.\d+)?[）)]?$')
UNIT_RE = re.compile(r'(?:金额单位|单位)(?:为)?[:：]?\s*(?:人民币)?\s*(亿元|百万元|千元|万元|元)')
GLOBAL_UNIT_RE = re.compile(r'以人民币\s*(亿元|百万元|千元|万元|元)\s*为单位')
PAGE_NO_RE = re.compile(r'^(\d+)\s*/\s*(\d+)$')
NUMBERING_RE = re.compile(r'^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+[、.]|（\d+）|其中：|加：|减：|其中:)')
PAREN_RE = re.compile(r'（[^（）]*）|\([^()]*\)')
WS_RE = re.compile(r'[\s\u200a\u200b\xa0]+')


def _compact(text: str) -> str:
    return WS_RE.sub('', text or '')


def _number_variants(value: float) -> set:
    """同一数值在年报里的常见写法：千分位、不同小数位、括号负数。"""
    out = set()
    av = abs(float(value))
    for p in range(7):
        s = f'{av:,.{p}f}'
        try:
            if abs(float(s.replace(',', '')) - av) > 1e-9:
                continue
        except ValueError:
            continue
        out.add(s)
    if value < 0:
        for s in list(out):
            out.add('(' + s + ')')
            out.add('（' + s + '）')
            out.add('-' + s)
    return out
TITLE_VARIANTS = {
    '合并资产负债表': ('合并资产负债表', '合并及公司资产负债表'),
    '合并利润表': ('合并利润表', '合并及公司利润表'),
    '合并现金流量表': ('合并现金流量表', '合并及公司现金流量表'),
}
TABLE_MARKERS = ('货币资金', '流动资产', '营业收入', '营业成本', '经营活动产生的现金流量')
START_MARKERS = {
    '合并资产负债表': ('货币资金', '流动资产合计', '资产总计'),
    '合并利润表': ('营业总收入', '营业收入', '营业成本', '销售费用'),
    '合并现金流量表': ('经营活动产生的现金流量', '销售商品、提供劳务收到的现金'),
}
EXPENSE_METRICS = {'total_cost', 'cost_of_revenue', 'taxes_surcharges', 'selling_expense', 'admin_expense', 'rd_expense'}


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
    # 去掉括号内容；允许跨行拼接后括号闭合不全
    text = re.sub(r'[（(][^（）()]*[）)]?', '', text)
    text = NUMBERING_RE.sub('', text)
    text = text.replace('：', '').replace(':', '').replace('/', '')
    # 去掉末尾附注编号：七、1 / 五、47(1) / 四(48)
    text = re.sub(r'(?:[一二三四五六七八九十]+、)?\d+(?:[、.]\d+)*$', '', text)
    text = re.sub(r'[一二三四五六七八九十]+、\d+.*$', '', text)
    return text.strip('（）()')


def _parse_value(text: str) -> float:
    text = text.replace('\u200a', '').replace('\u200b', '').replace('\xa0', '').strip().replace(',', '')
    negative = text.startswith('(') or text.startswith('（')
    text = text.strip('()（）')
    value = float(text)
    return -value if negative else value


def _is_value_word(w: Word) -> bool:
    text = w.text.replace('\u200a', '').replace('\u200b', '').replace('\xa0', '').strip()
    if not VALUE_RE.match(text) or w.x0 < 240:
        return False
    if len(text) < 3 and ',' not in text and '.' not in text and w.x0 < 380:
        return False
    return True


def _column_centers(words: Sequence[Word]) -> List[float]:
    xs = sorted(w.x1 for w in words if _is_value_word(w))
    groups: List[List[float]] = []
    for x in xs:
        if not groups or x - groups[-1][-1] > 12:
            groups.append([x])
        else:
            groups[-1].append(x)
    groups = [g for g in groups if len(g) >= 2]
    if not groups:
        groups = [[x] for x in xs]
    centers = sorted(sum(g) / len(g) for g in groups)
    # 三表都是“本期/上期”两列；只有一组中心时无法判断左右列，
    # 交给固定分栏兜底，避免把右列金额误当本期。
    return centers[:2] if len(centers) >= 2 else []


def page_lines(page, page_index: int) -> List[Line]:
    words = sorted(page.get_text('words'), key=lambda w: (round(w[1], 1), w[0]))
    grouped: List[List[Word]] = []
    current: List[Word] = []
    base: Optional[float] = None
    for x0, y0, x1, y1, text, *_ in words:
        text = text.replace('\u200a', '').replace('\u200b', '').replace('\xa0', '').strip()
        if not text:
            continue
        w = Word(x0=x0, x1=x1, text=text, y=y0, y1=y1)
        if base is None or abs(y0 - base) <= 6.0:
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
    # 页码是独立行；留在金额词表里会污染列中心（如“418”被当成右列金额）。
    grouped = [ws for ws in grouped
               if not PAGE_NO_RE.match(''.join(w.text for w in ws).strip())]

    centers = _column_centers([w for ws in grouped for w in ws])
    fallback_split = page.rect.width * 0.82
    lines: List[Line] = []
    for ws in grouped:
        ws = sorted(ws, key=lambda w: w.x0)
        # 页脚常见“119”单独一行；不是金额，留在列中心会把右列并向左移。
        if len(ws) == 1 and ws[0].text.strip().isdigit() and ws[0].y > page.rect.height * 0.9:
            continue
        item = ''.join(w.text for w in ws if w.x0 < 220)
        note = ''.join(w.text for w in ws if 220 <= w.x0 < 290 and not VALUE_RE.match(w.text))
        cur: List[Word] = []
        pri: List[Word] = []
        for w in ws:
            if not _is_value_word(w):
                continue
            if centers:
                idx = min(range(len(centers)), key=lambda i: abs(w.x1 - centers[i]))
                if abs(w.x1 - centers[idx]) <= 16:
                    (cur if idx == 0 else pri).append(w)
                continue
            (cur if w.x1 <= fallback_split else pri).append(w)
        raw = ''.join(w.text for w in ws)
        if raw.strip():
            lines.append(Line(page=page_index + 1, y=ws[0].y, words=ws, item=item.strip(),
                              note=note.strip(), current=cur, prior=pri, raw=raw,
                              printed_page=printed))
    return lines


def _statement_start(doc, title: str, require_table: bool = True) -> Optional[int]:
    variants = TITLE_VARIANTS.get(title, (title,))
    for i in range(doc.page_count):
        text = doc[i].get_text()
        compact = re.sub(r'\s+', '', text)
        if not any(v in compact for v in variants):
            continue
        if not require_table:
            return i
        markers = START_MARKERS.get(title, TABLE_MARKERS)
        if not any(k in compact for k in markers):
            continue
        # 真正的报表页至少有一个千分位金额；审计报告/正文页通常没有
        if not re.search(r'\d{1,3},\d{3}', text):
            continue
        if '项目' in compact or '附注' in compact or '资产' in compact or '营业收入' in compact:
            return i
    # 少数年报的报表页省略了“合并利润表”等标题，只能按表头+关键科目兜底
    for i in range(doc.page_count):
        compact = re.sub(r'\s+', '', doc[i].get_text())
        if not re.search(r'\d{1,3},\d{3}', doc[i].get_text()):
            continue
        if title == '合并利润表' and '营业总收入' in compact and '营业总成本' in compact:
            return i
        if title == '合并现金流量表' and '经营活动产生的现金流量净额' in compact \
                and '销售商品、提供劳务收到的现金' in compact and '项目' in compact:
            return i
        if title == '合并资产负债表':
            nxt = re.sub(r'\s+', '', doc[i + 1].get_text()) if i + 1 < doc.page_count else ''
            if '货币资金' in compact and '项目' in compact and '资产总计' in compact + nxt \
                    and '负债合计' in compact + nxt:
                return i
    return None


def _line_has_title(line: Line, title: str) -> bool:
    compact = re.sub(r'\s+', '', line.raw)
    if title.startswith(('公司', '母公司')) and '合并及公司' in compact:
        # “合并及公司资产负债表(续)”同时包含合并与母公司两列，
        # 不是母公司表的独立起始页；不能在这里截断合并表。
        return False
    return any(v in compact for v in TITLE_VARIANTS.get(title, (title,)))


def statement_unit(doc, title: str) -> str:
    start = _statement_start(doc, title)
    if start is None:
        return '元'
    # 只在报表起始页及后续页找单位；不要向前扫到 MD&A，否则会把
    # “单位：元”的营业收入分析表误当成三表单位（比亚迪 2023 即此问题）。
    for i in range(start, min(doc.page_count, start + 20)):
        compact = re.sub(r'\s+', '', doc[i].get_text())
        m = UNIT_RE.search(compact) or GLOBAL_UNIT_RE.search(compact)
        if m:
            return m.group(1)
    # 部分年报把“均以人民币千元为单位”放在附注开头，不在报表页。
    for i in range(start, min(doc.page_count, start + 30)):
        compact = re.sub(r'\s+', '', doc[i].get_text())
        m = GLOBAL_UNIT_RE.search(compact)
        if m:
            return m.group(1)
    return '元'


def _recolumn_lines(lines: Sequence[Line]) -> List[Line]:
    """按单个报表片段重新识别两列金额，避免同页混排的其它表格干扰列坐标。"""
    words = [w for line in lines for w in line.words if _is_value_word(w)]
    xs = sorted(w.x1 for w in words)
    groups: List[List[float]] = []
    for x in xs:
        if not groups or x - groups[-1][-1] > 12:
            groups.append([x])
        else:
            groups[-1].append(x)
    counts = [len(g) for g in groups]
    max_count = max(counts) if counts else 0
    kept = [g for g, c in zip(groups, counts) if c >= max(2, max_count * 0.5)]
    centers = sorted(sum(g) / len(g) for g in kept)[:2]
    out: List[Line] = []
    for line in lines:
        cur: List[Word] = []
        pri: List[Word] = []
        for w in line.words:
            if not _is_value_word(w):
                continue
            if centers:
                idx = min(range(len(centers)), key=lambda i: abs(w.x1 - centers[i]))
                if abs(w.x1 - centers[idx]) <= 16:
                    (cur if idx == 0 else pri).append(w)
                continue
            (cur if w.x1 <= 600 * 0.82 else pri).append(w)
        out.append(Line(page=line.page, y=line.y, words=line.words, item=line.item,
                        note=line.note, current=cur, prior=pri, raw=line.raw,
                        printed_page=line.printed_page))
    return out


def _title_after(doc, title: str, start: int) -> Optional[int]:
    """在 start 之后找下一张报表标题的页；不能复用从头扫描的 _statement_start。"""
    variants = TITLE_VARIANTS.get(title, (title,))
    for i in range(start + 1, doc.page_count):
        compact = re.sub(r'\s+', '', doc[i].get_text())
        if title.startswith(('公司', '母公司')) and '合并及公司' in compact:
            continue
        if any(v in compact for v in variants):
            return i
    return None


def statement_ranges(doc, title: str, lines_by_page: Dict[int, List[Line]]) -> List[Tuple[int, List[Line]]]:
    """返回报表覆盖的行区间；止页只取到下一张报表标题之前。"""
    start = _statement_start(doc, title)
    if start is None:
        return []
    stop = doc.page_count
    stop_title = ''
    for candidate in STOP_TITLES.get(title, ()):
        idx = _title_after(doc, candidate, start)
        if idx is not None and idx > start and idx < stop:
            stop = idx
            stop_title = candidate
    segments: List[Tuple[int, List[Line]]] = []
    for page in range(start, min(stop, doc.page_count - 1) + 1):
        lines = lines_by_page.get(page, [])
        begin = 0
        end = len(lines)
        if page == start:
            for j, line in enumerate(lines):
                if _line_has_title(line, title):
                    begin = j + 1
                    break
        if page == stop and stop_title:
            for j, line in enumerate(lines):
                if _line_has_title(line, stop_title):
                    end = j
                    break
        # 同页可能继续排“母公司资产负债表/利润表/现金流量表”，
        # 这些表的金额列会污染合并表的两列聚类，必须在标题处截断。
        for j in range(begin, end):
            raw = re.sub(r'\s+', '', lines[j].raw)
            for company_title in ('母公司资产负债表', '母公司利润表', '母公司现金流量表',
                                  '公司资产负债表', '公司利润表', '公司现金流量表',
                                  '公司所有者权益变动表'):
                if company_title not in raw:
                    continue
                if company_title.startswith('公司') and '合并及公司' in raw:
                    # 合并及公司资产负债表(续)同页展示合并/母公司两列，
                    # 不是母公司表标题，不能截断。
                    continue
                end = j
                break
            else:
                continue
            break
        segments.append((page, _recolumn_lines(lines[begin:end])))
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
            cur = _parse_value(line.current[0].text)
        if line.prior and prior is None:
            prior = _parse_value(line.prior[0].text)
    return cur, prior, value_words, note


def find_metric(segments: Sequence[Tuple[int, List[Line]]],
                metric: MetricDef) -> Optional[Tuple[float, float, Line, List[Line], List[Word], str]]:
    """按科目标签锚定数值行。

    报表 PDF 常把一个科目拆成多行：标签行没有金额，金额行没有标签。
    因此窗口必须从标签行开始向后拼，数值行只能出现在标签行之后。不能从
    上一行金额反推标签，否则会把“资产处置收益”的金额挂到“营业利润”。
    """
    aliases = {normalize_label(a) for a in metric.aliases}
    for page, lines in segments:
        for i, line in enumerate(lines):
            if not normalize_label(line.item):
                continue
            for e in range(i, min(len(lines), i + 3)):
                window = lines[i:e + 1]
                combined = normalize_label(''.join(x.item for x in window))
                if combined not in aliases:
                    continue
                value_line = None
                for j in range(i, e + 1):
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


def extract_metrics(doc, company: Company, period: str, source_file: str,
                    report_date: str = '', announce_date: str = '',
                    source_url: Optional[str] = None) -> List[Evidence]:
    lines_by_page = {i: page_lines(doc[i], i) for i in range(doc.page_count)}
    facts: List[Evidence] = []
    for statement, metrics in BY_STATEMENT.items():
        segments = statement_ranges(doc, statement, lines_by_page)
        if not segments:
            continue
        stmt_unit = statement_unit(doc, statement)
        for metric in metrics:
            found = find_metric(segments, metric)
            if not found:
                continue
            value, prior, anchor, window, value_words, note = found
            if metric.key in EXPENSE_METRICS:
                if value is not None and value < 0:
                    value = -value
                if prior is not None and prior < 0:
                    prior = -prior
            zero_type = None
            if value is None:
                zero_type = '未披露'
            evidence_id = '%s-%s-%s' % (company.code, period, metric.key)
            item_raw = normalize_label(''.join(x.item for x in window)) or metric.name
            aliases = {normalize_label(a) for a in metric.aliases}
            alias_ok = item_raw in aliases
            statement_ok = statement == metric.statement
            subject_ok = alias_ok and statement_ok
            subject_checks = []
            subject_messages = []
            if alias_ok:
                subject_checks.append('alias_match')
            else:
                subject_messages.append('科目名与指标别名不匹配：%s' % item_raw)
            if statement_ok:
                subject_checks.append('statement_match')
            else:
                subject_messages.append('指标预期在 %s，实际来自 %s' % (metric.statement, statement))
            subject = Quality(status='pass' if subject_ok else 'fail',
                              checks=subject_checks if subject_ok else [],
                              messages=subject_messages)
            quality = Quality(status='pass' if value is not None else 'warning',
                              checks=['value_present'] if value is not None else [],
                              messages=[] if value is not None else ['本期数值为空，按未披露处理，不参与比率计算'])
            facts.append(Evidence(
                evidence_id=evidence_id, company=company, period=period,
                report_date=report_date, announce_date=announce_date,
                evidence_level='verified', source_type='annual_report_pdf', source_url=source_url,
                metric=metric.key, metric_name=metric.name, value=value, prior_value=prior,
                unit=('元/股' if metric.unit == '元/股' else stmt_unit),
                page=anchor.page, printed_page=anchor.printed_page,
                snippet=_snippet(doc[anchor.page - 1], window, anchor, value_words),
                bbox=_bbox(window, value_words), source_file=source_file, statement=statement,
                item_raw=item_raw, note=note or None, zero_type=zero_type,
                quality=quality, subject_check=subject,
            ))
    return facts


def extract_rows(doc, statement: str, segments: Sequence[Tuple[int, List[Line]]]) -> List[RawRow]:
    rows: List[RawRow] = []
    for page, lines in segments:
        page_text = _compact(doc[page].get_text())
        for i, line in enumerate(lines):
            if not line.has_value:
                continue
            if '项目' in line.raw and '附注' in line.raw:
                continue
            prefix = []
            if not line.item and i - 1 >= 0:
                prev = lines[i - 1]
                if prev.item and not prev.has_value and not prev.item.endswith('：'):
                    prefix = [prev.item]
            item = ''.join(prefix) + line.item
            # 行级科目名不再拼接下一行：下一行可能是另一个空值科目，
            # 会造成“取得投资收益…处置固定资产…”这类串行。
            if not item or _compact(item) not in page_text:
                # 科目名无法在本页原文中命中，不能作为可回查的报表行。
                continue
            value, prior, value_words, note = _value_in([line])
            for v in (value, prior):
                if v is not None and not any(x in page_text for x in _number_variants(float(v))):
                    value = None
                    prior = None
                    break
            if value is None and prior is None:
                # 数值同样无法在原文命中，整行丢弃，避免“看起来有值”。
                continue
            window = [line]
            if prefix:
                window.insert(0, prev)
            rows.append(RawRow(page=page + 1, statement=statement, item=item,
                               note=note or None, value=value, prior_value=prior,
                               snippet=''.join(x.raw for x in window)[:300],
                               bbox=_bbox(window, value_words), complete=True))
    return rows


def snippet_hit_rate(pdf_path: str, facts: Sequence[Evidence]) -> float:
    """逐条检查证据片段是否仍能在对应 PDF 页原文中命中。"""
    if not facts:
        return 0.0
    doc = pymupdf.open(str(pdf_path))
    hit = 0
    for f in facts:
        if not (1 <= f.page <= doc.page_count):
            continue
        page = re.sub(r'\s+', '', doc[f.page - 1].get_text())
        if re.sub(r'\s+', '', f.snippet) in page:
            hit += 1
    return round(hit / len(facts), 4)


def build_dataset(pdf_path: str, company: Company, period: str, report_date: str = '',
                  announce_date: str = '', source_url: Optional[str] = None
                  ) -> Tuple[List[Evidence], List[RawRow], DatasetMeta]:
    path = Path(pdf_path)
    report_date = report_date or ('%s-12-31' % period if period.isdigit() else period)
    doc = pymupdf.open(str(path))
    lines_by_page = {i: page_lines(doc[i], i) for i in range(doc.page_count)}
    facts = extract_metrics(doc, company, period, path.name, report_date, announce_date, source_url)
    rows: List[RawRow] = []
    for statement in BY_STATEMENT:
        segments = statement_ranges(doc, statement, lines_by_page)
        rows.extend(extract_rows(doc, statement, segments))
    meta = DatasetMeta(
        company=company, period=period, report_date=report_date, announce_date=announce_date,
        dataset_id='%s-%s-%s' % (company.code, report_date, announce_date or 'unknown'),
        evidence_level='verified', source_type='annual_report_pdf', source_url=source_url,
        source_file=path.name, source_sha256=_sha256(path),
        page_count=doc.page_count, extracted_at=datetime.now().astimezone().isoformat(timespec='seconds'),
        statements=list(BY_STATEMENT.keys()), fact_count=len(facts), row_count=len(rows),
    )
    return facts, rows, meta
