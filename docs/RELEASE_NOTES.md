# v0.2.4 Release Notes

发布日期：2026-11-24

GitHub：https://github.com/feng01120/cn-fin-evidence-mcp  
Release：https://github.com/feng01120/cn-fin-evidence-mcp/releases/tag/v0.2.4

## 一句话

10 条重大追溯差异逐项复核完毕；已复核的真实追溯按 `pass_with_restatement` 通过门禁，未复核仍 fail。同时补齐 GitHub 发布形态、CI、Docker、30 秒 demo 和完整发布审计。

## 变更

- **门禁**
  - 新增 `src/fin_evidence/review.py`，从 `data/material_review.json` 读取已复核例外。
  - `restatement_material` + 已复核：数据集记 `pass_with_restatement`。
  - 未复核 material：仍 `fail`；`verified_isolated` 始终 `fail`。
  - 原始 `structured.json` / `sina.json` 中的 `quality=fail` 保留为审计信号；工具层返回 `warning + reviewed_restatement`。
- **数据**
  - 10 条重大追溯 10/10 确认真实追溯、0 条抽取错误。
  - 原始 `as_reported` 与后发 `restated_comparative` 并列保存，不覆盖。
- **工具**
  - `verify_fact` 新增 `restatement_match`：声称值匹配后发重述值时返回 warning，而不是误报 fail。
  - `fin-evidence demo`：30 秒终端演示，不需要 PDF。
- **发布工程**
  - GitHub Actions CI（Python 3.10/3.11/3.12，52 项测试 + MCP stdio 冒烟）。
  - Release workflow：tag `v*` 时构建 wheel/sdist 并附加到 Release。
  - Dockerfile / `.vscode/mcp.json` / Claude Desktop 示例配置。
  - wheel 内置 2 家公司 / 6 个数据集的离线 demo 数据。
  - README 首屏加入 demo GIF、badges、快速开始、范围与限制；新增 English README。
  - SECURITY / CONTRIBUTING / DATA_SOURCES / THIRD_PARTY_LICENSES。

## 验收

| 项目 | 结果 |
|---|---:|
| 数据集 / 公司 | 60 / 20 |
| facts / rows | 2,016 / 8,352 |
| 数据审计 | 0 error / 75 warning |
| material failure | 0 |
| 已复核 material | 10 |
| 验收 | `acceptance=true` |
| 三源门禁 | pass 55 + pass_with_restatement 5 |
| 测试 | 52 / 52 |
| GitHub Actions CI | Python 3.10 / 3.11 / 3.12 全部通过 |
| MCP stdio 冒烟 | 7 tools；证据与重述核对通过 |

## 资产

- `cn_fin_evidence-0.2.4-py3-none-any.whl`：Python wheel，内置 demo 数据。
- `cn_fin_evidence-0.2.4.tar.gz`：源码分发包。
- `cn-fin-evidence-mcp-v0.2.4-60datasets-with-pdf.zip`：完整数据 + 60 份 PDF。
- `cn-fin-evidence-mcp-v0.2.4-source.zip`：不含 `data/raw` 的源码包。
- `RELEASE_AUDIT.md` / `release_audit.json`：完整发布审计报告与机器可读结果。
- `SHA256SUMS`：资产校验和。

## 已知限制

- 只覆盖 20 家非金融 A 股公司、2023–2025 年；银行/保险/券商未纳入。
- 75 条 warning 仍保留：54 条现金口径差异，21 条结构化指标无 verified 交叉核对。
- 600690/2023 现金净增加额披露颗粒度有限；601088/2025 六项后发证据来自 2026 年三季报比较数，不是 2025 年报页码。
- PDF 解析依赖 PyMuPDF（AGPL-3.0 或商业许可）；闭源商业分发需单独处理。
- Dockerfile 已提供，但本次构建环境没有 Docker daemon，未实际构建镜像。
- 已发布到 GitHub `feng01120/cn-fin-evidence-mcp`；`v0.2.4` Release 含 wheel、sdist、完整离线包、源码包与审计报告。
