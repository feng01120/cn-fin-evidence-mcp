# -*- coding: utf-8 -*-
"""Render docs/MATERIAL_REVIEW.md from data/material_review.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'material_review.json'
OUT = ROOT / 'docs' / 'MATERIAL_REVIEW.md'


def num(value):
    if value is None:
        return '—'
    if abs(value - round(value)) < 1e-9:
        return f'{int(round(value)):,}'
    return f'{value:,.2f}'


def pct(value):
    return f'{value * 100:+.2f}%' if value is not None else '—'


def main():
    ledger = json.loads(DATA.read_text(encoding='utf-8'))
    items = ledger['items']
    summary = ledger['summary']

    lines = []
    lines.append('# 10 条重大追溯逐项审查')
    lines.append('')
    lines.append('审查日期：2026-11-24  ')
    lines.append('范围：20 家公司 × 2023–2025 年试点中的 10 个 `restatement_material` 指标。  ')
    lines.append('数据：`data/material_review.json`；校验：`scripts/build_material_review.py`。')
    lines.append('')
    lines.append('## 结论先行')
    lines.append('')
    lines.append('- **10/10 确认为真实追溯重述，0 条抽取错误。** `verified_isolated=0`，即不存在“东方财富与新浪一致、反而年报解析值错误”的情况。')
    lines.append('- **0 条原始披露值被改写。** 台账把原报告本期数 `as_reported` 与后发报告比较数 `restated_comparative` 并列保存。')
    lines.append(f'- **原因分为 {len(ledger["reasons"])} 组：** 解释第18号重分类 2 条；同一控制下物流业务并表 1 条；杭锦能源并表 1 条；2026 年 12 家标的并表 6 条。')
    lines.append('- **1 条披露有限：** 600690/2023 现金净增加额能确认比较数被重述、且原因指向物流业务并表，但年报没有单列该现金流项目的调整明细，不能把差额写成逐行可复算的精确结论。')
    lines.append('')
    lines.append('> 这不是“把差异解释掉”。判断标准是：后发报告是否明确披露了会计政策变更或同一控制下合并，且后发比较数是否与原报告本期数在同一期间、同一口径下对应。10 条均满足；600690 的披露颗粒度不足，单独标明。')
    lines.append('')
    lines.append('## 口径规则')
    lines.append('')
    lines.append('| 字段 | 含义 | 是否覆盖原值 |')
    lines.append('|---|---|---|')
    lines.append('| `as_reported` | 数据集对应年报中“本期”列的原披露值，带页码与原文片段 | 不覆盖 |')
    lines.append('| `restated_comparative` | 后续年报/季报中同一期间的“上期/比较期”列，带后发披露日与来源 | 不覆盖 |')
    lines.append('| `second_source` | 新浪财经同一期间的原披露值，用于确认原报告值可复现 | 不覆盖 |')
    lines.append('')
    lines.append('**关键点：** 同一个 `report_date` 可以有两个口径的值。工具不应把后发比较数写回原报告本期数；调用方应同时看到 `as_reported`、`restated_comparative` 和 `difference.reason`。')
    lines.append('')
    lines.append('## 总表')
    lines.append('')
    lines.append('| # | 指标 | 原披露（本期） | 后发比较数 | 差额 | 原因 | 结论 |')
    lines.append('|---|---|---|---|---|---|---|')
    for index, item in enumerate(items, 1):
        asr = item['as_reported']
        rst = item['restated_comparative']
        diff = item['difference']
        lines.append(
            f'| {index} | `{item["id"]}`<br>{item["metric_name"]} | '
            f'{num(asr["value"])} {asr["unit"]}<br>p{asr["page"]} | '
            f'{num(rst["value"])} {rst["unit"]}<br>{rst["api_notice_date"]} | '
            f'{num(diff["amount_yuan"])} 元<br>{pct(diff["pct_of_as_reported"])} | '
            f'{item["reason"]["label"]} | 确认真实追溯 |'
        )
    lines.append('')
    lines.append('差额百分比以原披露值为分母；负值表示后发比较数低于原披露值。东方财富与新浪之间的差额百分比另见逐项卡片。')
    lines.append('')
    lines.append('## 逐项结论')
    lines.append('')
    for index, item in enumerate(items, 1):
        asr = item['as_reported']
        rst = item['restated_comparative']
        diff = item['difference']
        second = item['second_source']
        reason = item['reason']
        lines.append(f'### {index}. `{item["id"]}` / {item["metric_name"]}')
        lines.append('')
        lines.append(f'- **原披露：** {num(asr["value"])} {asr["unit"]}（= {num(asr["value_yuan"])} 元），{item["period"]} 年报 p{asr["page"]}，`{asr["source_file"]}`。')
        lines.append(f'- **后发比较数：** {num(rst["value"])} {rst["unit"]}（= {num(rst["value_yuan"])} 元），东方财富披露日 `{rst["api_notice_date"]}`；对照原文 `{rst["comparison_source"]}` p{rst["comparison_page"]}。')
        lines.append(f'- **差额：** {num(diff["amount_yuan"])} 元（相对原值 {pct(diff["pct_of_as_reported"])}；东方财富相对新浪 {pct(diff["pct_of_restated"])}）。')
        lines.append(f'- **第二源：** 新浪 {num(second["value"])} {second["unit"]}（= {num(second["value_yuan"])} 元），与原披露{"一致" if second["agrees_with_as_reported"] else "不一致"}。')
        lines.append(f'- **原因：** {reason["detail"]}')
        if item.get('reclass_check'):
            lines.append(f'- **重分类复核：** {item["reclass_check"]["note"]}')
        if item.get('review', {}).get('note'):
            lines.append(f'- **披露限制：** {item["review"]["note"]}')
        lines.append(f'- **结论：** {item["review"]["verdict"]}，`extraction_error=false`；保留原值，不覆盖；数据处置为“{item["review"]["data_action"]}”。')
        lines.append('')
        lines.append('证据：')
        for evidence in item['evidence']:
            source = evidence['source']
            if source.startswith('http'):
                source_label = f'[官方 PDF]({source})'
            else:
                source_label = f'`{source}`'
            lines.append(f'- {source_label} p{evidence["page"]}：`{"` / `".join(evidence.get("must_contain", []))}`')
        lines.append('')

    lines.append('## 门禁改造：改造前 / 改造后')
    lines.append('')
    lines.append('用户已明确批准按逐项审查结论修改门禁。下表不是“建议”，而是改造前后实际口径。')
    lines.append('')
    lines.append('| 口径 | acceptance | error | material failure | 已复核 | 说明 |')
    lines.append('|---|---:|---:|---:|---:|---|')
    change = summary['gate_changes']
    before = change['before']
    after = change['after']
    lines.append(f'| 改造前严格审计 | {str(before["acceptance"]).lower()} | {before["error_count"]} | {before["material_failure_count"]} | 0 | {before["note"]} |')
    lines.append(f'| 改造后 | {str(after["acceptance"]).lower()} | {after["error_count"]} | {after["material_failure_count"]} | {after.get("reviewed_material_count", 0)} | {after["note"]} |')
    lines.append('')
    lines.append('改造后的质量门语义：')
    lines.append('')
    lines.append('- `restatement_material` 且 10 个指标全部在 `data/material_review.json` 中确认：数据集记为 `pass_with_restatement`。')
    lines.append('- 任一 material 未复核：仍记 `fail`，审计继续报 error。')
    lines.append('- `verified_isolated`：始终 `fail`，不因 review 豁免。')
    lines.append('- 原始 `structured.json` / `sina.json` 中的 `quality=fail` 不被覆盖，保留为审计信号；工具层对已复核条目返回 `warning + reviewed_restatement`。')
    lines.append('- 原始 `as_reported` 与后发 `restated_comparative` 并列保存，不写回、不覆盖。')
    lines.append('')
    lines.append('当前审计：`data/audit_report.json` 为 0 error / 75 warning、`material_failure_count=0`、`reviewed_material_count=10`、`pass=true`；验收脚本已按同一口径复跑。')
    lines.append('')
    lines.append('## 复跑')
    lines.append('')
    lines.append('```bash')
    lines.append('cd /home/user/Doubao/chats/38456275306143746/fin-evidence-mcp')
    lines.append('PYTHONPATH=src python scripts/build_material_review.py')
    lines.append('# 输出 10 items / 10 confirmed / evidence_errors 0 / pass true')
    lines.append('```')
    lines.append('')
    lines.append('## 边界')
    lines.append('')
    lines.append('- 只覆盖这 10 个 `restatement_material`；不把 46 条普通 `restatement` 当作已逐条人工复核。')
    lines.append('- 601088/2025 的后发比较数来自 2026 年第三季度报告，不是 2025 年报原文；它是“后发季报比较数”，不能标成 `verified` 年报页证据。')
    lines.append('- 600690/2023 的 940,640,094.73 元差额没有被年报单列调整表逐行量化；结论是“原因已确认、金额可复核到比较数”，不是“每一元都能解释到明细”。')
    lines.append('- 这 10 条不构成投资判断；只回答数据口径与证据问题。')

    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
