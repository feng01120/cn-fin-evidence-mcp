# GitHub 发布清单

当前状态：**已发布**。

- 仓库：https://github.com/feng01120/cn-fin-evidence-mcp
- Release：https://github.com/feng01120/cn-fin-evidence-mcp/releases/tag/v0.2.4
- 默认分支：`main`
- 版本标签：`v0.2.4`，指向 `44beb07`
- 可见性：Public

## 已完成的发布动作

1. 创建公开仓库并推送 `main`。
2. 推送 annotated tag `v0.2.4`。
3. GitHub Actions `ci` 在 Python 3.10 / 3.11 / 3.12 全部通过。
4. GitHub Actions `release` 构建 wheel/sdist，`twine check` 与安装冒烟通过，并自动创建 Release。
5. 手动补传完整离线包、源码包、审计报告与校验和。
6. 用 `SHA256SUMS` 与 `SHA256SUMS.github` 下载后逐项复核，全部一致。

## Release 资产

- `cn_fin_evidence-0.2.4-py3-none-any.whl`
- `cn_fin_evidence-0.2.4.tar.gz`
- `cn-fin-evidence-mcp-v0.2.4-60datasets-with-pdf.zip`
- `cn-fin-evidence-mcp-v0.2.4-source.zip`
- `RELEASE_AUDIT.md`
- `release_audit.json`
- `SHA256SUMS`
- `SHA256SUMS.github`

## 复现检查

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/audit_data.py
PYTHONPATH=src python scripts/accept_20.py
PYTHONPATH=src python scripts/smoke_mcp.py
python scripts/release_audit.py
```

## 发布后

- README badge 已指向本仓库。
- 监控 Issue 中关于数据口径、安装失败、MCP 客户端兼容和 AGPL 的提问。
- 先不要批量开 `good first issue`，等外部用户跑通后再收口。

## 不要做

- 不要 force push 已发布 tag。
- 不要把 `data/raw`、`data/audit.jsonl`、PDF、虚拟环境或 `dist/` 提交进 git。
- 不要在未确认 PyMuPDF 商业许可前宣称“可闭源商用”。
- 不要把 OAuth token、设备码或个人邮箱写进仓库。
