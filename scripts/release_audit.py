# -*- coding: utf-8 -*-
"""发布前的静态仓库审计：只读检查，不执行数据审计/测试。

输出 data/release_audit.json；用于人工发布报告和 CI 之外的发布清单。
"""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = DATA / 'release_audit.json'


def sh(*args):
    return subprocess.run(args, cwd=str(ROOT), text=True, capture_output=True)


def contains(path, pattern):
    if not path.exists():
        return False
    try:
        return re.search(pattern, path.read_text(encoding='utf-8', errors='ignore')) is not None
    except OSError:
        return False


def main():
    required = [
        'README.md', 'README.en.md', 'LICENSE', 'SECURITY.md', 'CONTRIBUTING.md',
        'DATA_SOURCES.md', 'THIRD_PARTY_LICENSES.md', 'pyproject.toml', 'Dockerfile',
        '.github/workflows/ci.yml', '.github/workflows/release.yml', 'docs/demo.gif',
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    tracked = sh('git', 'ls-files').stdout.splitlines()
    remote = sh('git', 'remote', '-v').stdout.strip()
    tags = sh('git', 'tag', '-l').stdout.splitlines()
    status = sh('git', 'status', '--porcelain').stdout.strip()
    pdf_tracked = [p for p in tracked if p.endswith('.pdf')]
    audit_tracked = [p for p in tracked if p.endswith('audit.jsonl')]
    raw_tracked = [p for p in tracked if p.startswith('data/raw/')]
    audit_report = json.loads((DATA / 'audit_report.json').read_text(encoding='utf-8'))
    acceptance = json.loads((DATA / 'acceptance_report.json').read_text(encoding='utf-8'))
    readme_links = []
    for name in ('README.md', 'README.en.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if link.startswith(('http://', 'https://', '#', 'mailto:')):
                continue
            target = link.split('#')[0]
            if target and not (ROOT / target).exists():
                readme_links.append({'readme': name, 'link': link})
    absolute_paths = []
    for p in tracked:
        path = ROOT / p
        if path.suffix.lower() in ('.pdf', '.jsonl') or not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if re.search(r'(/home/user|C:\\Users|/Users/)', text):
            absolute_paths.append(p)
    sensitive = []
    for p in tracked:
        if p.startswith('data/') or p.endswith(('.md', '.txt', '.json')):
            continue
        path = ROOT / p
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if re.search(r'ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH) PRIVATE KEY', text):
            sensitive.append(p)
    checks = {
        'required_files': {'status': 'pass' if not missing else 'fail', 'missing': missing},
        'git_clean': {'status': 'pass' if not status else 'warn', 'detail': status[:500]},
        'remote': {'status': 'pass' if remote else 'warn', 'detail': remote or 'no git remote configured'},
        'tag': {'status': 'pass' if tags else 'warn', 'detail': tags or 'no git tag'},
        'tracked_pdf': {'status': 'pass' if not pdf_tracked else 'fail', 'count': len(pdf_tracked)},
        'tracked_audit_log': {'status': 'pass' if not audit_tracked else 'fail', 'count': len(audit_tracked)},
        'tracked_raw_dir': {'status': 'pass' if not raw_tracked else 'fail', 'count': len(raw_tracked)},
        'readme_links': {'status': 'pass' if not readme_links else 'fail', 'broken': readme_links},
        'absolute_paths': {'status': 'pass' if not absolute_paths else 'warn', 'files': absolute_paths},
        'secret_patterns': {'status': 'pass' if not sensitive else 'fail', 'files': sensitive},
        'data_audit': {
            'status': 'pass' if audit_report.get('pass') and audit_report.get('error_count') == 0 else 'fail',
            'error_count': audit_report.get('error_count'),
            'warning_count': audit_report.get('warning_count'),
            'reviewed_material_count': audit_report.get('reviewed_material_count'),
            'pass': audit_report.get('pass'),
        },
        'acceptance': {
            'status': 'pass' if acceptance.get('acceptance') else 'fail',
            'acceptance': acceptance.get('acceptance'),
            'cross_source_gates': acceptance.get('cross_source_gates'),
        },
        'wheel_demo_data': {
            'status': 'pass' if (ROOT / 'src/fin_evidence/demo_data/601088/2025-12-31/2026-03-31/facts.json').exists() else 'fail',
        },
    }
    report = {
        'release': 'v0.2.4',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'checks': checks,
        'github_publish_blocked': bool(not remote or not tags),
        'local_release_ready': all(c['status'] != 'fail' for c in checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['local_release_ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
