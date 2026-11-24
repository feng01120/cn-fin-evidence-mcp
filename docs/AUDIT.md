# 自检报告 · 2026-11-24

## 结论

v0.2 试点已跑通：20 家公司 × 2023–2025 年、60 个数据集，全部 `evidence_level=verified`、`quality_gate=pass`。每个 fact 与每条报表行都能回到年报页码和原文片段；找不到就不写入、不返回。**未发布到 GitHub。**

## 检测矩阵

| 项目 | 结果 |
|---|---|
| 数据集 / 公司 | 60 / 20（2023–2025，非金融标准报表） |
| 单元/契约测试 | 26 / 26 通过 |
| facts 规模 | 2,017 条 |
| rows 规模 | 8,400 条 |
| 证据逐条回查 | 随机 20 条 facts，20 / 20 命中；全量 facts `snippet_hit_rate=1.0` |
| 行级回查 | 8,400 rows，0 条科目名/数值无法在对应页命中 |
| 页码与 bbox | 全部 facts / rows 页内、bbox 有效且非零面积 |
| 源文件哈希 | 60 份 PDF 的 SHA-256 与 meta 一致 |
| 比率 | 9 个比率 / 数据集；输入证据可解析为证据对象；`value_type=computed` |
| 硬勾稽 | 4 项 × 60 = 240 / 240 pass |
| 质量门槛 | `quality_gate` pass 60，warning 0，fail 0 |
| 拒答边界 | 未知指标 / 证据 / 数据集 / 非法容差均返回结构化错误 |
| 官方下载 | 巨潮接口按 orgId → 年报分类 → 静态 PDF 下载；批量重建可复跑 |
| 静态检查 | pyflakes 无告警；compileall 通过 |

审计明细：`data/audit_report.json`（0 error / 54 warning）；验收报告：`data/acceptance_report.json`；逐数据集覆盖：`data/rebuild_report.json`。

54 条 warning 全部是 `cash_bs_vs_cf`：货币资金与现金流量表“期末现金及现金等价物”存在口径差异，提示核对受限资金/现金等价物，不判错。

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

## 仍未覆盖

- 只有 20 家非金融标准报表；银行/保险/券商特殊报表未纳入。
- 全部 60 个数据集走 PDF `verified`；`structured`（akshare/baostock 无页码覆盖层）尚未接入。
- 跨章节一致性（正文引用 vs 报表数值）未做；科目拦截白名单只做到 `subject_check`，未覆盖全部高频指标。
- 母公司报表、TTM、追溯重述对比未做。
- 持牌数据源适配层、审计日志哈希链/签名未做。
- `printed_page` 大多为空，当前以 PDF 物理页码为准。
- 未发布 GitHub，未做外部 MCP Host 实测（仅本地 stdio 客户端）。

## 复跑命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/audit_data.py --data data --pdf-dir data/raw
PYTHONPATH=src python scripts/accept_20.py
PYTHONPATH=src python scripts/rebuild_universe.py --only 002594,300760 --workers 2
fin-evidence --data data serve
```
