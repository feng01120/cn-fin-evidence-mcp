# cn-fin-evidence-mcp

A 股财报证据链 MCP：**每个返回给 AI 的数字，都能被验证、被信任、被追责。**

不是又一个“把三表塞进向量库”的财报问答。这个项目的核心是一条硬规则：

> 找不到页码与原文片段，就拒答。

## 为什么值得单独做一个

通用 RAG 能回答“茅台毛利率多少”，但金融从业者真正需要的是：

- 这个数字来自哪一页、哪一行？
- 是年报直接披露的，还是工具算出来的？
- 用的是合并口径还是母公司口径？单位是元还是万元？
- 本期为空，是零、未披露，还是不适用？
- 三表勾稽过没过？哪一项没过？

`cn-fin-evidence-mcp` 把这些问题变成结构化的返回字段，而不是提示词里的“请不要编造”。

## 现在能做什么（v0.1）

| 能力 | 状态 |
|---|---|
| 从年报 PDF 还原三表科目与数值 | 已实现（文本型 PDF） |
| 每个数值附带公司/期间/指标/数值/单位/页码/原文片段 | 已实现 |
| 单元格坐标 bbox | 已实现 |
| 披露值优先，计算值附公式与输入 | 已实现 |
| 三表勾稽校验（资产=负债+权益、现金流恒等、现金滚存） | 已实现 |
| 结构化错误、缺证据拒答 | 已实现 |
| 分页与 token 控制 | 已实现 |
| 本地审计日志 | 已实现 |
| 示例数据 | 贵州茅台 600519、五粮液 000858（2025 年报） |
| 指标覆盖 | 30+ 核心科目、9 个比率 |

## 快速开始

```bash
pip install -e .
python scripts/fetch_report.py --code 600519 --year 2025 --out data/raw
fin-evidence --data data build \
  --pdf data/raw/600519_2025.pdf \
  --code 600519 --name "贵州茅台酒股份有限公司" --short-name "贵州茅台" --period 2025
fin-evidence --data data inspect --code 600519 --period 2025
fin-evidence --data data serve
```

MCP 客户端配置（stdio）：

```json
{
  "mcpServers": {
    "cn-fin-evidence": {
      "command": "python",
      "args": ["-m", "fin_evidence.server"],
      "env": {
        "PYTHONPATH": "/path/to/cn-fin-evidence-mcp/src",
        "FIN_EVIDENCE_DATA": "/path/to/cn-fin-evidence-mcp/data"
      }
    }
  }
}
```

## 工具

| 工具 | 作用 | 关键约束 |
|---|---|---|
| `list_companies` | 列出已收录公司与报告期 | 只返回元信息 |
| `get_statement` | 按报表读取科目行 | `statement` 限定三张合并报表；cursor 分页；单页最多 200 行 |
| `get_ratio` | 读取比率 | 每个比率带公式、输入值与证据编号 |
| `get_evidence` | 按证据编号取六元组 | 不存在即返回结构化错误 |
| `verify_fact` | 核对一个声称值 | 相对误差默认 1%；未披露则拒绝核对 |
| `get_quality_report` | 勾稽与质量报告 | pass / warning / fail 计数 |

返回统一为 `data`、`evidence`、`meta`、`quality` 四个区块；错误返回 `error.code`，不抛异常。

示例（`verify_fact` 命中）：

```json
{
  "data": {
    "verdict": "match",
    "metric": "cash",
    "claimed_value": 51690610946.5,
    "actual_value": 51690610946.5,
    "difference": 0.0,
    "unit": "元"
  },
  "evidence": {
    "evidence_id": "600519-2025-cash",
    "page": 56,
    "snippet": "货币资金151,690,610,946.5059,295,822,956.89"
  },
  "quality": {"status": "pass"}
}
```

## 设计：六层落地情况

| 层 | v0.1 做法 | 还没做 |
|---|---|---|
| 数据层 | 原生科目名 + 稳定指标键；披露值/计算值分开；单位与口径写入返回 | 母公司报表、TTM、追溯重述对比 |
| 溯源层 | 六元组 + 原文片段 + bbox；缺证据拒答 | 跨章节正文一致性校验 |
| 工具层 | 六个只读工具，按报表/维度拆分，双 Schema 结构化 | 多数据源适配、批量导出 |
| 校验层 | 4 项勾稽 + 0 值三分类 | 异常波动提示、行业口径校验 |
| 合规层 | 本地审计日志；数据源与授权状态在文档标注 | 防篡改签名、权限模型、持牌源适配 |
| 工程层 | 分页、截断、可组合、13 项契约测试 | 托管演示、基准集、CI |

## 数据与合规

- 示例数据来自上市公司公开年度报告，仅用于原型与研究。
- `scripts/fetch_report.py` 走公开公告接口；**不得**把该接口用于商业再分发。
- 生产环境应替换为持牌数据源（Wind、Choice、通联等）的适配层。
- 本项目不构成投资建议；所有数值以原始年报为准。

## 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

覆盖：六元组完整性、证据编号唯一、比率数值、4 项勾稽、分页、命中/不匹配、未知证据与未知指标拒答。

## 目录

```
src/fin_evidence/
  models.py      # 证据、比率、校验结果的数据契约
  mapping.py     # 科目别名与报表分段
  extract.py     # PDF 行还原、跨行科目合并、页码/bbox/片段
  ratios.py      # 比率公式与勾稽
  store.py       # 数据集与审计日志
  server.py      # MCP 工具
  cli.py         # build / inspect / serve
data/            # 已构建的示例数据集（JSON）
scripts/         # 年报下载
tests/           # 契约测试
```

## 路线图

- **v0.2**：20 家公司、100 个指标、跨章节一致性校验、扫描件 OCR、数据源适配层。
- **v0.3**：审计日志哈希链、托管演示、MCP Registry 发布、基准题集。
- **v1.0**：持牌数据源适配、多期对比、行业模板、可复现的评估报告。

## License

MIT
