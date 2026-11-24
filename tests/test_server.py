# -*- coding: utf-8 -*-
import importlib
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['FIN_EVIDENCE_DATA'] = str(ROOT / 'data')

import fin_evidence.server as srv
importlib.reload(srv)


class TestServer(unittest.TestCase):
    def test_list(self):
        r = srv.list_companies()
        self.assertEqual(r['meta']['count'], 2)
        self.assertEqual({x['code'] for x in r['data']}, {'600519', '000858'})

    def test_statement_pagination(self):
        r = srv.get_statement('600519', '2025', '合并资产负债表', limit=5)
        self.assertEqual(len(r['data']['items']), 5)
        self.assertEqual(r['meta']['next_cursor'], '5')
        r2 = srv.get_statement('600519', '2025', '合并资产负债表', cursor='5', limit=5)
        self.assertEqual(len(r2['data']['items']), 5)

    def test_second_company(self):
        r = srv.get_quality_report('000858', '2025')
        self.assertEqual(r['data']['counts']['fail'], 0)
        r2 = srv.verify_fact('000858', '2025', 'revenue', 40528509770.23)
        self.assertEqual(r2['data']['verdict'], 'match')

    def test_ratio(self):
        r = srv.get_ratio('600519', '2025', '毛利率')
        self.assertEqual(len(r['data']['ratios']), 1)
        self.assertAlmostEqual(r['data']['ratios'][0]['value'], 91.18, places=1)

    def test_verify_match(self):
        r = srv.verify_fact('600519', '2025', 'cash', 51690610946.50)
        self.assertEqual(r['data']['verdict'], 'match')
        self.assertEqual(r['evidence']['evidence_id'], '600519-2025-cash')

    def test_verify_mismatch(self):
        r = srv.verify_fact('600519', '2025', 'cash', 60000000000.0)
        self.assertEqual(r['data']['verdict'], 'mismatch')
        self.assertEqual(r['quality']['status'], 'fail')

    def test_unknown_evidence_refuses(self):
        r = srv.get_evidence('600519-2025-not_exist')
        self.assertEqual(r['error']['code'], 'EVIDENCE_NOT_FOUND')

    def test_unknown_metric_refuses(self):
        r = srv.verify_fact('600519', '2025', 'not_exist', 1.0)
        self.assertEqual(r['error']['code'], 'METRIC_NOT_FOUND')


if __name__ == '__main__':
    unittest.main()
