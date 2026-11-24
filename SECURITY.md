# 安全说明

## 运行边界

`cn-fin-evidence-mcp` 是本地只读 MCP server。默认行为：

- 不主动联网；只有构建/抓取脚本会访问巨潮、东方财富或新浪。
- 读取 `FIN_EVIDENCE_DATA` 指向的 JSON 数据集和 `data/raw` 下的 PDF。
- 不包含账号、Cookie、API key 或云凭证。
- 工具调用写入本地 `data/audit.jsonl`，只记录工具名和参数摘要，不记录完整返回内容。

## 不要把运行时日志公开

`data/audit.jsonl` 可能包含查询的股票代码、期间和指标名。发布 Release 或公开仓库前应删除该文件；仓库已默认忽略它。

## 数据不是投资建议

所有数值以原始年报为准。结构化源只用于交叉核对，缺页码证据时不得视为 verified。数据再分发限制见 [`DATA_SOURCES.md`](DATA_SOURCES.md)。

## 报告漏洞

如果发现路径穿越、任意文件读取、注入或数据泄露问题，请通过 GitHub Security Advisory 私下报告，不要先开公开 Issue。首次响应目标为 72 小时内。
