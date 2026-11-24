# 自检报告 · 2026-11-24

## 结论

v0.2.4 试点已跑通：20 家公司 × 2023–2025 年、60 个数据集，全部 `evidence_level=verified`、`quality_gate=pass`。三源比对初判 5 个数据集 / 10 个重大追溯指标为 `cross_source_gate=fail`；逐项复核确认真实追溯后，按用户批准的门禁改为 `pass_with_restatement`，未复核 material 仍 fail。每个 fact 与每条报表行都能回到年报页码和原文片段；找不到就不写入、不返回。

本轮把 structured 从“有值但没有页码”推进到“差异有语义”：
- 东方财富 60/60 数据集、1,200 个指标；
- 新浪财经 60/60 数据集、2,040 个指标，作为第二源做三源交叉核对；
- 46 条东方财富差异被判定为后发年报追溯/重分类（`restatement`），10 条差异超过 25% 标 `restatement_material`；
- `verified_isolated=0`：没有出现“两个结构化源一致、年报解析值反而不同”的情况。

**未发布到 GitHub。**

10 个重大追溯指标已完成逐项审查，结论与证据见 [`MATERIAL_REVIEW.md`](MATERIAL_REVIEW.md)：10/10 为真实追溯，0 条抽取错误；其中 600690/2023 现金净增加额的原因已确认但披露颗粒度有限。门禁已按审查结论改为 `pass_with_restatement`：当前审计 0 error / 75 warning、`material_failure_count=0`、`reviewed_material_count=10`、`pass=true`，验收 `acceptance=true`。

## 检测矩阵

| 项目 | 结果 |
|---|---|
| 数据集 / 公司 | 60 / 20（2023–2025，非金融标准报表） |
| 单元/契约测试 | 52 / 52 通过 |
| facts 规模 | 2,016 条 |
| rows 规模 | 8,352 条 |
| 证据逐条回查 | 随机 20 条 facts，20 / 20 命中；全量 facts `snippet_hit_rate=1.0` |
| 行级回查 | 8,352 rows，0 条科目名/数值无法在对应页命中 |
| 页码与 bbox | 全部 facts / rows 页内、bbox 有效且非零面积 |
| 源文件哈希 | 60 份 PDF 的 SHA-256 与 meta 一致 |
| 比率 | 9 个比率 / 数据集；输入证据可解析为证据对象；`value_type=computed` |
| 硬勾稽 | 4 项 × 60 = 240 / 240 pass |
| 质量门槛 | `quality_gate` pass 60；`cross_source_gate` pass 55 + `pass_with_restatement` 5（10 个已复核重大追溯指标），fail 0 |
| structured 覆盖 | 60 / 60 数据集、1,200 指标；1,123 一致、46 追溯、10 重大追溯（已复核）、21 无法核对 |
| 第二源覆盖 | 60 / 60 数据集、2,040 指标；1,960 一致、45 追溯、10 重大追溯（已复核）、25 无 verified、0 无对应 |
| 三源隔离 | `verified_isolated=0`；第二源 `warning=0`；10 个重大追溯指标在两侧各记一次 review 通过，不再记 error |
| 结构化质量 | 普通条目无页码、`evidence=[]`、`quality=warning`；10 个重大追溯条目原始 `quality=fail` 保留，工具层返回 `warning + reviewed_restatement` |
| 拒答边界 | 未知指标 / 证据 / 数据集 / 非法容差均返回结构化错误 |
| 官方下载 | 巨潮接口按 orgId → 年报分类 → 静态 PDF 下载；批量重建可复跑 |
| 静态检查 | pyflakes 无告警；compileall 通过 |

审计明细：`data/audit_report.json`（0 error / 75 warning）；验收报告：`data/acceptance_report.json`；逐数据集覆盖：`data/rebuild_report.json`；东方财富抓取：`data/structured_report.json`；第二源抓取：`data/second_source_report.json`。

## 0 error / 75 warning 的构成

- 0 条 error：10 个 `restatement_material` 指标经逐项复核后计入 `reviewed_material_metrics`，不再计 error；`material_failure_count=0`；
- 75 条 warning：54 条 `cash_bs_vs_cf`（货币资金与“期末现金及现金等价物”口径差异），21 条东方财富指标没有对应 verified fact、无法交叉核对。

`restatement`（46 + 45 条）是正常语义标签，不进入 warning；`missing` / `unverified` 也不等于 fail。`quality_gate` 仍以 verified 的硬勾稽和覆盖率判定；`cross_source_gate` 对 5 个含已复核重大追溯指标的数据集为 `pass_with_restatement`，只对未复核 material 或 `verified_isolated` 记 fail。

## 三源状态的含义

| 状态 | 含义 | 是否 warning |
|---|---|---|
| `pass` | 与 verified 差异 ≤ 1%，或两个结构化源均与 verified 一致 | 否 |
| `restatement` | API 披露日晚于数据集公告日，差异 ≤ 25%；视为后发年报的可比数重述/重分类 | 否 |
| `restatement_material` | 同上，但差异 > 25%；可能是合并范围变化、会计政策变更或抽取问题 | 已复核为真实追溯：`pass_with_restatement`；未复核：fail |
| `warning` | 同一披露期内差异 > 1%，且不属于可识别的追溯 | 是 |
| `verified_isolated` | 东方财富与新浪一致，但 verified 不一致；高度怀疑 PDF 抽取错误 | 是（当前为 0） |
| `missing` / `unverified` | 没有对应指标或没有 verified 值 | 否 |

## 本轮发现并修复

1. **证据片段不是连续原文**：原实现用 `" | "` 拼接标签和数值，无法通过“字符串在不在原文”的硬校验。改为按区域取 PDF 内容流文本，并校验归一化后确实出现在整页文本中。
2. **bbox 高度为 0**：`Word` 只存了 y0，y1 被写成 y0。补充 y1，事实与行级 bbox 均恢复有效面积。
3. **行级科目名串行**：`get_statement` 会把相邻空行/续行拼成“现金经营活动现金流入小计”这类错误标签。改为“仅数值行才向上拼一行标签 + 按 7pt 行距拼续行”，并回归检查截断标签。
4. **小额指标容差过宽**：`verify_fact` 以 1 元为绝对下限，导致 EPS 这类小数值的 0.84 偏差被误判为 match。改为严格相对容差，绝对下限降到 1e-6。
5. **审计日志写失败会阻断查询**：只读部署或磁盘满时，`append_audit` 抛错会打崩工具调用。改为记录失败不影响查询。
6. **路径穿越**：股票代码/期间直接拼路径，`../../etc` 可越出数据目录。增加 6 位代码与 `YYYY`/`YYYYQn` 校验，非法输入返回 `INVALID_CODE` / `INVALID_PERIOD`。
7. **比率计算缺期初值会崩**：ROE/总资产周转率在 prior 缺失时抛 `ValueError`，中断整份构建。改为 `value=None` + `warning`，构建继续。
8. **下载脚本失效**：东财 PDF 直链已返回 EdgeOne JS 反爬挑战，不是 PDF。改用巨潮资讯官方公告接口（查 orgId → 年报分类 → `static.cninfo.com.cn`），批量重建实测可用。
9. **README 示例数值错误**：示例写成 151.69B，实际货币资金为 51.69B；已按真实证据修正。
10. **行级数据混入注释表**：比亚迪、迈瑞的现金流量表曾一直扫到附注末尾，单数据集出现 990–1,126 条现金流行。补齐“公司现金流量表/公司资产负债表”等停止标题，并在抽取层丢弃“科目名或数值不能在本页命中”的行；修复后比亚迪 2025 行数 1,244 → 186，迈瑞 2025 1,098 → 240。
11. **批量脚本与 CLI 签名不一致**：`fetch_report.py` 支持 `org=` 并返回结构化下载结果；`cli.py` 补齐 `REQUIRED_METRICS` 导入；`rebuild_universe.py` 可直接复跑。
12. **`get_ratio` 证据为空**：比率内部只有证据 ID，工具层返回空列表。改为按 ID 回填页码、片段、bbox、单位、科目，并标记 `value_type=computed`。
13. **structured 无页码层缺失**：新增 `structured.py` + `fetch_structured.py`，用东方财富三表接口补结构化指标；工具层在 verified 缺值时才 fallback，`evidence=[]`、`quality=warning`，绝不返回伪造页码。
14. **科目拦截只看别名**：新增 `subject.py`，把校验提升为“指标 + 报表归属 + 科目别名”三重；错误报表直接 `SUBJECT_MISMATCH`，高频指标缺报表归属也拒绝。
15. **structured 与 verified 口径冲突无提示**：新增 `cross_check`，按单位换算后比较两套值；差异 >1% 标 warning，`get_quality_report` 暴露 `structured_cross_check` / `structured_status`。
16. **`verify_fact` 证据契约不一致**：统一为 evidence 数组；structured 命中仍返回 warning，不让“API 命中”看起来像“原文命中”。
17. **营业利润错挂上一行金额**：`find_metric` 的窗口会从上一行金额反推标签，恒瑞 2024 的“营业利润”因此取成“资产处置收益”5,397,912.01。改为从标签行向后拼、数值行只能出现在标签行之后；重建后恢复 7,490,632,003.88。
18. **合并表续页被当成母公司表**：美的 2023/2024/2025 的“合并及公司资产负债表(续)”包含“公司资产负债表”子串，被误判为母公司表并截断，导致负债、权益等 7 个指标缺失。停止标题增加“合并及公司”排除规则，三张表恢复完整。
19. **页码污染金额列**：宁德 2025 现金流页的页脚“119”被当成右侧金额，列中心右移，导致本期 477.8B 被读成上期 417.5B。页脚纯数字不再进入列中心，并且只有一组列中心时回退固定分栏。
20. **追溯差异没有语义**：新增 `api_notice_date` 与公告日比较；后发年报差异标 `restatement`，超过 25% 标 `restatement_material`。不再把 46 条正常重述都算成 warning。
21. **只有东方财富一个结构化源**：新增新浪财经三表适配器与 `get_source_comparison`；`verified_isolated=0`，三源比对不再只看单一源。
22. **新浪缺两个指标**：补 `归属于母公司股东权益合计` 与 `加:期初现金及现金等价物余额` 两个标签；从 32 指标（历史值 1,920）扩展到 34 指标（2,040 值），并补入第二 fallback。
23. **重大追溯仍只是 warning**：v0.2.3 先将 10 个 `restatement_material` 指标升级为 fail，审计去重后记录 10 个失败指标、源级错误 20 条；不再让“超过 25% 的追溯”静默通过。
24. **真实追溯被误判为数据错误**：逐项回年报/后发季报核验 10 条差异，10/10 确认真实追溯、0 条抽取错误。门禁改为 `pass_with_restatement`，未复核 material 仍 fail，`verified_isolated` 始终 fail；原始 `quality=fail` 与两套口径继续保留。

## 仍未覆盖

- 只有 20 家非金融标准报表；银行/保险/券商特殊报表未纳入。
- structured fallback 仍以东方财富为第一源、新浪为第二源；两个源都无页码，不能替代 verified。
- 跨章节一致性（正文引用 vs 报表数值）未做；科目拦截已覆盖 10 个高频指标，但尚未覆盖全部指标。
- 母公司报表、TTM、更多历史期未做。
- 持牌数据源适配层、审计日志哈希链/签名未做。
- `printed_page` 大多为空，当前以 PDF 物理页码为准。
- 未发布 GitHub，未做外部 MCP Host 实测（仅本地 stdio 客户端）。

## 复跑命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/audit_data.py --data data --pdf-dir data/raw
PYTHONPATH=src python scripts/accept_20.py
PYTHONPATH=src python scripts/fetch_structured.py --overwrite
PYTHONPATH=src python scripts/fetch_sina.py --overwrite
PYTHONPATH=src python scripts/rebuild_universe.py --only 002594,300760 --workers 2
fin-evidence --data data serve
```
