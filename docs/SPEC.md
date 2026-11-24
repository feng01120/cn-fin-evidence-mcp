# 设计规格

## 产品原则

1. **证据先于答案。** 没有页码与原文片段的数字不返回；没有任何字段缺失时静默补全，缺失即拒答。
2. **披露值优先于计算值。** 年报直接披露的比率优先；计算值必须附公式、输入字段与来源证据编号。
3. **口径显式。** 合并/母公司、本期/上期、单位、追溯重述状态必须出现在返回体中，冲突数据隔离而非合并。
4. **校验先于输出。** 勾稽不过的数据带 `fail` 返回，不允许“看起来对”就放行。
5. **错误是内容。** 数据缺失、口径不可比、指标未知，都以结构化 `error.code` 返回，由调用方决定降级。

## 证据对象

```json
{
  "evidence_id": "600519-2025-revenue",
  "stock_code": "600519",
  "period": "2025",
  "report_date": "2025-12-31",
  "announce_date": "2026-03-27",
  "evidence_level": "verified",
  "metric": "revenue",
  "value": 168838102514.79,
  "unit": "元",
  "page": 56,
  "snippet": "其中：营业收入168,838,102,514.79147,693,864,158.69",
  "bbox": {"x0": 100.3, "y0": 712.4, "x1": 520.0, "y1": 730.0},
  "zero_type": null,
  "quality": "pass"
}
```

六元组为 `[公司, 期间, 指标, 数值, 单位, 页码+原文片段]`，缺一即拒答。主键为 `(stock_code, report_date, announce_date)`，同一报告期多次修订按披露日隔离。

`evidence_level=structured` 时没有页码证据，`evidence=[]`、`quality` 至少为 warning；它只作为 verified 缺值时的 fallback，不能冒充 `verified`，也不能覆盖已验证值。重大追溯条目 `quality=fail`。

结构化条目额外带 `api_notice_date`。当该披露日晚于数据集 `announce_date` 时，与 verified 的差异标为 `restatement`；差异超过 25% 标为 `restatement_material`，并升级为 fail。新浪第二源先用于三源比对，东方财富也缺值时才作为第二 fallback。

## 工具边界

- 只读，不提供写操作。
- 按报表/维度拆分工具，不提供 `query_financials(任意问题)` 这类万能入口。
- `outputSchema` 统一为 `data` / `evidence` / `meta` / `quality`。
- 单次返回有行数与字符上限，长表用 cursor 分页。
- 行级 `get_statement` 只返回能在对应页命中科目名与数值的行；否则不写入。
- `get_evidence` / `verify_fact` 才允许使用 structured fallback（东方财富优先、新浪第二）；返回时必须标注 `evidence_level=structured`、`source_provider`，且 `quality` 为 warning 或 fail。
- `get_source_comparison` 并排返回 verified / 东方财富 / 新浪三源值与差异；三源不一致不自动改写任何一方。
- 科目拦截同时校验指标、报表归属、科目别名；错误报表直接返回 `SUBJECT_MISMATCH`。

## 当前落地（v0.2.4 试点）

- 20 家非金融公司 × 2023–2025 年，60 个数据集；全部 `verified`、`quality_gate=pass`；5 个数据集 `cross_source_gate=pass_with_restatement`（10 个已复核真实追溯），其余 55 个 `pass`，fail 0。
- 2,016 条 facts、8,352 条 rows；60 份年报 PDF；52 项契约测试。
- 验收：随机 20 条证据 20/20 命中；4 项硬勾稽 240/240 pass；行级审计 0 error / 75 warning；`material_failure_count=0`、`reviewed_material_count=10`；`acceptance=true`。
- structured：60/60 数据集、1,200 指标；1,123 一致、46 追溯、10 重大追溯（已复核，`pass_with_restatement`）、21 无法核对；普通条目无页码证据只作 warning。
- 第二源：60/60 数据集、2,040 指标；1,960 一致、45 追溯、10 重大追溯（已复核）、25 无 verified、0 无对应；`verified_isolated=0`。
- 跨章节一致性尚未做；科目拦截覆盖 10 个高频指标，尚未覆盖全部指标。

## 质量门语义

- `cross_source_gate` 取值：`pass`、`warning`、`pass_with_restatement`、`fail`。
- `restatement_material` 且所有相关指标均在 `data/material_review.json` 中确认为真实追溯：`pass_with_restatement`。
- `restatement_material` 有任一未复核：`fail`。
- `verified_isolated`：始终 `fail`，不能被 review 豁免。
- 原始 `structured.json` / `sina.json` 中的 `quality=fail` 保留为审计信号；加载到工具层时，已复核条目返回 `warning + reviewed_restatement`。
- 原始 `as_reported` 与后发 `restated_comparative` 并列保存、不覆盖；后发季报比较数不能标成 `verified` 年报页证据。

## 校验

- `balance_identity`：资产 = 负债 + 所有者权益。
- `total_le_identity`：负债和所有者权益总计 = 资产总计。
- `cash_flow_identity`：经营 + 投资 + 筹资 + 汇率影响 = 现金净增加额。
- `cash_roll`：期初现金 + 净增加额 = 期末现金。
- `growth_anomaly`：营收或净利同比超过 ±50% 时给 warning，要求人工复核口径/重述，不直接判 fail。
- 0 值三分类：`零` / `未披露` / `不适用`。

## 非目标（v0.2.4）

- 不做投资建议、估值、预测。
- 不覆盖母公司报表、TTM、行业均值。
- 不承诺数据商用授权；示例仅用于原型。
- 不做扫描件 OCR 与正文跨章节比对（列入 v0.3）。
- 不把 structured 值当作 verified；没有页码证据时至少返回 warning；新浪第二源只作第二 fallback，不能冒充页码证据。

## v1.0 验收

- 50–100 家公司、三表全科目、100 个以上指标；银行/保险/券商特殊报表可选。
- 每条证据可通过页码+片段复核；抽样 100 条人工复核准确率 ≥ 99%。
- 跨章节一致性校验可定位“正文与报表打架”的具体页码。
- 持牌数据源适配层可切换，审计日志可导出且可校验完整性。
