# -*- coding: utf-8 -*-
"""按股票代码与年份，从东方财富公告接口查找并下载年度报告 PDF。

仅用于原型验证：数据源与使用权需自行确认，生产环境请替换为持牌数据源。
"""

import argparse
import re
from pathlib import Path

import requests

API = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def find_annual(code: str, year: int, pages: int = 5):
    target = '%d年年度报告' % year
    for page in range(1, pages + 1):
        params = {'sr': -1, 'page_size': 50, 'page_index': page, 'ann_type': 'A',
                  'client_source': 'web', 'stock_list': code, 'f_node': 0, 's_node': 0}
        data = requests.get(API, params=params, headers=HEADERS, timeout=20).json()
        items = data.get('data', {}).get('list', [])
        if not items:
            break
        for item in items:
            title = item.get('title', '')
            if target in title and '摘要' not in title and '英文' not in title \
                    and '半年度' not in title and '已取消' not in title:
                return item['notice_date'][:10], item['art_code'], title
    return None


def download(code: str, year: int, out_dir: Path) -> Path:
    found = find_annual(code, year)
    if not found:
        raise SystemExit('未找到 %s %s 年年度报告' % (code, year))
    date, art_code, title = found
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ('%s_%s.pdf' % (code, year))
    url = 'https://pdf.dfcfw.com/pdf/H2_%s_1.pdf' % art_code
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    if not resp.content.startswith(b'%PDF'):
        raise SystemExit('下载内容不是 PDF：%s' % url)
    path.write_bytes(resp.content)
    print('%s\t%s\t%s\t%s bytes' % (date, title, path, len(resp.content)))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--year', required=True, type=int)
    ap.add_argument('--out', default='data/raw')
    args = ap.parse_args()
    download(args.code, args.year, Path(args.out))


if __name__ == '__main__':
    main()
