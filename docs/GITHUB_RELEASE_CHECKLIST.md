# GitHub 发布清单

当前状态：本地 release candidate 已通过；**尚未创建 GitHub remote，也未推送**。以下命令需要你确认仓库名/可见性后执行。

## 1. 建仓库

```bash
cd cn-fin-evidence-mcp
git remote add origin git@github.com:<owner>/cn-fin-evidence-mcp.git
git push -u origin main
```

建议仓库描述：

> A-share financial-statement evidence MCP: every number traces back to an annual-report page, or it is refused.

Topics：

`mcp` `finance` `a-share` `annual-report` `evidence` `llm` `python` `financial-data`

## 2. 打 tag 并发布

```bash
git tag -a v0.2.4 -m "v0.2.4: reviewed restatements pass_with_restatement; GitHub release shape"
git push origin v0.2.4
```

`release.yml` 会自动构建 wheel/sdist 并挂到 GitHub Release。完整 PDF 包和 `SHA256SUMS` 需要手动上传到同一个 Release：

- `dist/cn-fin-evidence-mcp-v0.2.4-60datasets-with-pdf.zip`
- `dist/SHA256SUMS`

## 3. 发布前最后检查

```bash
python -m unittest discover -s tests -v          # 52/52
PYTHONPATH=src python scripts/audit_data.py      # 0 error / 75 warning
PYTHONPATH=src python scripts/accept_20.py       # acceptance=true
python scripts/smoke_mcp.py                      # MCP stdio
python scripts/release_audit.py                  # 静态仓库审计
```

## 4. 发布后

- 在 README 顶部换成真实 CI badge：`https://github.com/<owner>/cn-fin-evidence-mcp/actions/workflows/ci.yml/badge.svg`
- 在 Release 说明里贴 demo GIF 和已知限制。
- 先不要开 `good first issue`，等外部用户跑通后再收口。
- 监控 Issue 中关于数据口径、安装失败和 AGPL 的提问。

## 5. 不要做

- 不要 force push 已发布 tag。
- 不要把 `data/raw`、`data/audit.jsonl`、PDF、虚拟环境或 `dist/` 提交进 git。
- 不要在未确认 PyMuPDF 商业许可前宣称“可闭源商用”。
