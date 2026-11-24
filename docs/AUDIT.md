# 自检报告 · 2026-11-24

## 结论

v0.1 可以本地运行、可由官方年报重建、可通过 MCP 协议调用。**未发布到 GitHub。**

## 检测矩阵

| 项目 | 结果 |
|---|---|
| 单元/契约测试 | 19 / 19 通过 |
| 证据逐条回查 | 67 / 67 条 facts 的片段能在对应 PDF 页原文命中；0 错误 |
| 数值与片段一致 | 全部 value / prior_value 均出现在 snippet 中 |
| 页码与 bbox | 67 条 facts + 230 条 rows 均在页内、bbox 有效且非零面积 |
| 源文件哈希 | 两份 PDF 的 SHA-256 与 meta 一致 |
| 比率独立复算 | 18 / 18（2 家公司 × 9 个比率）与存储值一致 |
| 勾稽独立复算 | 4 项恒等式全部通过；五粮液另有 1 项同比异常 warning |
| MCP 协议 | 6 个工具正常路径 + 分页 + 拒答 + 非法参数；0 错误 |
| 安装 | wheel 构建成功；`pip install -e .` 后 `fin-evidence` 入口可用 |
| 重建一致性 | 同一 PDF 两次构建，facts/rows/ratios/checks 完全一致（仅 extracted_at 不同） |
| 官方下载 | 巨潮接口下载两份年报；SHA-256 与数据集源文件一致 |
| 静态检查 | pyflakes 无告警；compileall 通过 |

## 本轮发现并修复

1. **证据片段不是连续原文**：原实现用 `" | "` 拼接标签和数值，无法通过“字符串在不在原文”的硬校验。改为按区域取 PDF 内容流文本，并校验归一化后确实出现在整页文本中。
2. **bbox 高度为 0**：`Word` 只存了 y0，y1 被写成 y0。补充 y1，事实与行级 bbox 均恢复有效面积。
3. **行级科目名串行**：`get_statement` 会把相邻空行/续行拼成“现金经营活动现金流入小计”这类错误标签。改为“仅数值行才向上拼一行标签 + 按 7pt 行距拼续行”，并回归检查截断标签。
4. **小额指标容差过宽**：`verify_fact` 以 1 元为绝对下限，导致 EPS 这类小数值的 0.84 偏差被误判为 match。改为严格相对容差，绝对下限降到 1e-6。
5. **审计日志写失败会阻断查询**：只读部署或磁盘满时，`append_audit` 抛错会打崩工具调用。改为记录失败不影响查询。
6. **路径穿越**：股票代码/期间直接拼路径，`../../etc` 可越出数据目录。增加 6 位代码与 `YYYY`/`YYYYQn` 校验，非法输入返回 `INVALID_CODE` / `INVALID_PERIOD`。
7. **比率计算缺期初值会崩**：ROE/总资产周转率在 prior 缺失时抛 `ValueError`，中断整份构建。改为 `value=None` + `warning`，构建继续。
8. **下载脚本失效**：东财 PDF 直链已返回 EdgeOne JS 反爬挑战，不是 PDF。改用巨潮资讯官方公告接口（查 orgId → 年报分类 → `static.cninfo.com.cn`），两家公司实测下载成功，哈希与现有数据源一致。
9. **README 示例数值错误**：示例写成 151.69B，实际货币资金为 51.69B；已按真实证据修正。

## 仍未覆盖

- 只有 2 家公司、文本型 PDF；扫描件 OCR 未做。
- 跨章节一致性校验（正文引用 vs 报表数值）未做。
- 母公司报表、TTM、追溯重述对比未做。
- 持牌数据源适配层、审计日志哈希链/签名未做。
- `printed_page` 大多为空，当前以 PDF 物理页码为准。
- 未发布 GitHub，未做外部 MCP Host 实测（仅本地 stdio 客户端）。

## 复跑命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/audit_data.py --data data --pdf-dir data/raw
fin-evidence --data data serve
```
