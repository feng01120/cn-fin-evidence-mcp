# 第三方许可证与发布边界

本项目代码使用 MIT License。以下直接依赖的许可证需要单独遵守；它们不会被 MIT 重新授权。

| 组件 | 许可证 | 说明 |
|---|---|---|
| PyMuPDF (`pymupdf`) | **AGPL-3.0 或 Artifex 商业许可** | 年报纸面文本/坐标解析使用。闭源商业分发、SaaS 化或无法满足 AGPL 源码义务时，需要购买 Artifex 商业许可，或替换为 `pdfplumber`/`pdfminer.six` 等宽松许可实现。 |
| `pydantic` | MIT | 数据模型 |
| `mcp` | MIT | MCP Python SDK；本项目固定 `<2`，因为 2.x 将 `FastMCP` 迁移为 `MCPServer`。 |
| `requests` | Apache-2.0 | 年报/结构化源抓取 |

## 对 GitHub 开源发布的影响

- 以 MIT 代码 + AGPL 依赖发布是可以的，但必须在 README/Release 中明确 AGPL 依赖，不能宣称整个发行物都是 MIT。
- 如果目标是闭源商业产品，**PyMuPDF 是本项目最大的许可证阻断项**。
- 数据（年报 PDF）版权归原披露方；仓库只提交解析后的 JSON 证据，PDF 通过 Release 资产单独分发。

## 依赖清单复核

发布前在干净虚拟环境执行：

```bash
pip-licenses --format=table --with-urls
pip-audit
pip check
```

2026-11-24 的 v0.2.4 审计结果：90 个已安装包，0 个已知漏洞；直接依赖中只有 PyMuPDF 需要商业注意。
