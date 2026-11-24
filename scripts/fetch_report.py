# -*- coding: utf-8 -*-
"""按股票代码与年份，从巨潮资讯官方公告接口查找并下载年度报告 PDF。

仅用于公开年报的原型验证；数据使用权需自行确认，生产环境请替换为持牌数据源。
"""

import argparse
import datetime
from pathlib import Path

import requests

QUERY_API = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
STOCK_API = 'http://www.cninfo.com.cn/new/data/szse_stock.json'
STATIC = 'https://static.cninfo.com.cn/'
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice',
    'X-Requested-With': 'XMLHttpRequest',
}


def resolve_org(code: str) -> str:
    data = requests.get(STOCK_API, headers=HEADERS, timeout=30).json()
    for item in data.get('stockList', []):
        if item.get('code') == code:
            return item['orgId']
    raise SystemExit('巨潮股票列表中没有 %s' % code)


def column_for(code: str) -> str:
    if code.startswith('6'):
        return 'sse'
    if code.startswith(('0', '3')):
        return 'szse'
    return 'bj'


def find_annual(code: str, year: int, pages: int = 3, org: str = None):
    org = org or resolve_org(code)
    payload = {
        'pageNum': 1, 'pageSize': 30, 'column': column_for(code), 'tabName': 'fulltext',
        'plate': '', 'stock': '%s,%s' % (code, org), 'searchkey': '', 'secid': '',
        'category': 'category_ndbg_szsh', 'trade': '',
        'seDate': '%d-01-01~%d-12-31' % (year, year + 1),
        'sortName': '', 'sortType': '', 'isHLtitle': 'true',
    }
    for page in range(1, pages + 1):
        payload['pageNum'] = page
        resp = requests.post(QUERY_API, data=payload, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('announcements') or []
        if not items:
            break
        for item in items:
            title = item.get('announcementTitle', '')
            if ('%d年年度报告' % year) not in title and ('%d年度报告' % year) not in title:
                continue
            if any(k in title for k in ('摘要', '英文', '更正', '问询', '意见')):
                continue
            return item['announcementTime'], item['adjunctUrl'], title
    return None


def download(code: str, year: int, out_dir: Path, org: str = None) -> dict:
    found = find_annual(code, year, org=org)
    if not found:
        raise SystemExit('未找到 %s %s 年年度报告（巨潮年报分类）' % (code, year))
    ts, adjunct, title = found
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ('%s_%s.pdf' % (code, year))
    url = STATIC + adjunct.lstrip('/')
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=120)
    resp.raise_for_status()
    if not resp.content.startswith(b'%PDF'):
        raise SystemExit('下载内容不是 PDF：%s' % url)
    path.write_bytes(resp.content)
    return {'path': str(path), 'announce_date': datetime.datetime.fromtimestamp(
        ts / 1000, datetime.timezone(datetime.timedelta(hours=8))).date().isoformat(),
        'title': title, 'source_url': url, 'bytes': len(resp.content)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--code', required=True)
    ap.add_argument('--year', required=True, type=int)
    ap.add_argument('--out', default='data/raw')
    args = ap.parse_args()
    if not (len(args.code) == 6 and args.code.isdigit()):
        raise SystemExit('股票代码必须是 6 位数字')
    result = download(args.code, args.year, Path(args.out))
    print('%s\t%s\t%s\t%s bytes' % (result['announce_date'], result['title'],
                                      result['path'], result['bytes']))


if __name__ == '__main__':
    main()
