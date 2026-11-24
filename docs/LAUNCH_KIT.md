# Launch Kit

## GitHub 仓库首屏

**标题：** cn-fin-evidence-mcp
**一句话：** 每个返回给 AI 的 A 股财报数字，都能回到年报页码；回不去的，拒答。
**Demo：** `fin-evidence --data data demo`，30 秒看原披露值、后发重述、错误声称值如何处理。
**三个卖点：**
1. 页码 + 原文 + bbox，不是只有一句“来自年报”。
2. 东方财富/新浪/年报三源交叉，识别追溯重述，不把差异静默吞掉。
3. 找不到证据就拒答；错误声称值不会被“修正”成看起来合理的数字。

## V2EX

**节点：** 程序员 / 分享发现

**标题：** 做了个 A 股财报 MCP：每个数字必须能回到年报页码，回不去就拒答

**正文：**

> 最近在折腾 A 股财报数据，发现一个很烦的问题：LLM 能告诉你“茅台营收多少”，但你没法确认它是不是把上期、母公司口径、万元和元混在一起了。
>
> 所以我做了 cn-fin-evidence-mcp。规则很硬：每个数字带公司/期间/指标/数值/单位/页码/原文片段；找不到就拒答。
>
> 现在覆盖 20 家非金融公司 × 2023–2025 年，60 个数据集，2,016 facts、8,352 rows。除了年报 PDF，还接了东方财富和新浪做三源交叉。最典型的是中国神华 2025 总资产：2025 年报原值 627,761 百万元（p148），2026 三季报把比较数重述成 903,830 百万元。工具不会覆盖原值，而是并列返回，并标记 `pass_with_restatement`；未复核的 material 差异仍然 fail。
>
> 10 条重大追溯逐条人工核过：10/10 真实追溯、0 条抽取错误。数据审计 0 error / 75 warning，验收 `acceptance=true`，52 项测试。
>
> 30 秒 demo 不需要 PDF：
>
> ```bash
> pip install -e .
> fin-evidence --data data demo
> ```
>
> 不是投资建议，也不装作“全 A 股通用”。目前只做非金融标准报表；银行/保险/券商、跨章节一致性、扫描件 OCR 都还没做。Known limits 写在 README 里。
>
> 想听听大家对“财报证据链”这种形态的看法：你会把它接进 coding agent、投研 workflow，还是只当数据核对工具？

## 掘金 / 知乎

**标题：** 为什么我不做一个“会读财报的 AI”，而做一个“敢拒答的财报 MCP”

**结构：**

1. 痛点：LLM 数字看着对，口径全错。
2. 硬规则：六元组 + 页码 + 原文 + bbox；无证据拒答。
3. 三源比对：年报 / 东方财富 / 新浪；追溯重述为什么要并列保存。
4. 真实案例：中国神华 627,761 → 903,830 的重述，`pass_with_restatement` 怎么判定。
5. 工程取舍：52 项测试、审计 0 error / 75 warning、为什么 warning 不藏起来。
6. 边界：20 家公司、非金融、PyMuPDF AGPL、未做跨章节。
7. 结尾：repo 链接 + demo 命令 + 欢迎拿真实财报来打脸。

## Hacker News / Reddit

**Title:** Show HN: A-share financial-statement MCP that refuses numbers without a page citation

**Body:**

> I built a small MCP server for Chinese A-share annual reports. The rule is simple: every number must carry company, period, metric, value, unit, PDF page, and a verbatim snippet; if it cannot be traced, the tool refuses.
>
> It covers 20 non-financial companies (2023–2025), 60 datasets, 2,016 facts, 8,352 statement rows. It also cross-checks three sources: the annual report, Eastmoney, and Sina. When a later filing restates a comparative, the original and restated values are returned side by side. Reviewed material restatements are tagged `pass_with_restatement`; unreviewed ones still fail.
>
> 30-second demo (no PDFs required):
>
> ```bash
> pip install -e .
> fin-evidence --data data demo
> ```
>
> Not investment advice. Scope is intentionally narrow: non-financial standard statements only, no banks/insurers/brokers, no OCR, no cross-chapter consistency yet. Feedback on the evidence contract is welcome.

## 小红书 / 即刻

**标题：** 我做了一个“不敢编数字”的 A 股财报工具

**正文：**

> 不是选股，不是预测，也不是“AI 帮你读财报”。
>
> 它只做一件事：你问一个财报数字，它把页码、原文、单位、口径一起给你；给不出证据，就拒答。
>
> 最爽的一个案例：中国神华 2025 总资产，年报原值 627,761 百万元，后发季报把比较数重述成 903,830 百万元。它不会偷偷改成“看起来合理”的数，而是把两套口径并排摆出来，再告诉你哪套是本期、哪套是重述。
>
> 10 条重大追溯人工核完：10/10 真实，0 条抽取错误。
>
> 开源在 GitHub，搜 cn-fin-evidence-mcp。不是投资建议，先当数据核验工具用。

## 发布节奏

1. 先发 GitHub Release + README demo GIF。
2. 同一天发 V2EX，收集安装失败和口径问题。
3. 48 小时后发掘金/知乎长文，带真实 issue 修复记录。
4. 一周后发英文 Show HN/Reddit，只发一次，不刷屏。
5. 所有渠道统一 UTM 或 GitHub traffic 观察，不买 star。
