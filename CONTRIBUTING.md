# Contributing

欢迎提交可复现的问题、数据口径修正和新的年报样本。

## 开发流程

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
fin-evidence --data data demo
```

## 提交前检查

1. 不提交 `data/raw/` 下的 PDF、`data/audit.jsonl` 或任何凭证。
2. 新增/修改抽取逻辑时，必须补一个能回查到页码和原文的 fixture。
3. 修改质量门语义时，必须同步更新 `docs/SPEC.md`、`docs/AUDIT.md` 和回归测试。
4. 保持工具返回结构为 `data` / `evidence` / `meta` / `quality`，错误走 `error.code`。
5. 数据集变更必须同时更新 `data/audit_report.json` 和 `data/acceptance_report.json`。

## 数据贡献

新增公司请优先选择文本型年报 PDF；扫描件暂不进入 verified 链路。提交时附上公司代码、报告期、公告日、源 URL 和 PDF SHA-256。
