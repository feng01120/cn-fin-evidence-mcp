# 数据来源与再分发边界

本项目是研究原型，不是持牌金融数据产品。

## verified 数据集

- 范围：20 家 A 股非金融公司，2023–2025 年，共 60 份年度报告。
- 原始来源：巨潮资讯网公开年度报告（`static.cninfo.com.cn`），每份 PDF 的公司、报告期、公告日、源 URL 与 SHA-256 记录在对应 `meta.json` 和 `data/raw/manifest.json`。
- 仓库只提交由 PDF 解析出的 JSON 证据（`facts.json` / `rows.json` / `ratios.json` / `checks.json` / `meta.json`），**不提交 PDF 本体**。
- 完整 PDF 只放在 Release 资产或本地 `data/raw`，用于复跑页码审计。
- 年报版权归各上市公司/交易所披露平台所有；本项目不主张对 PDF 的再授权，不应把 PDF 包用于商业再分发。

## structured 覆盖层

- 来源：东方财富公开三表接口（`datacenter-web.eastmoney.com`）。
- 只保留接口字段、数值、单位、披露日与源 URL；没有年报页码证据，质量固定为 warning/fail。
- 接口数据可能受服务条款约束；不得把该覆盖层单独包装成商业数据服务。

## 第二源

- 来源：新浪财经公开三表文本页（`money.finance.sina.com.cn`）。
- 仅用于交叉核对和东方财富缺值时的第二 fallback，不提供页码证据，不覆盖 verified。

## 使用建议

- 研究/原型：可直接使用仓库内 JSON 复现。
- 生产：替换为持牌数据源（Wind、Choice、通联等）的适配层，并保留同样的页码/片段证据契约。
- 投资决策：本项目不构成投资建议；以年报原文和持牌数据终端为准。
