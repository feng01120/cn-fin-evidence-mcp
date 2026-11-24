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
        self.assertEqual(r['meta']['count'], 60)
        self.assertEqual(len({x['code'] for x in r['data']}), 20)
        self.assertIn('600519', {x['code'] for x in r['data']})
        self.assertIn('601088', {x['code'] for x in r['data']})

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

    def test_structured_evidence_has_no_page(self):
        r = srv.get_evidence('600519-2025-cash-structured')
        self.assertEqual(r['meta']['evidence_level'], 'structured')
        self.assertEqual(r['evidence'], [])
        self.assertEqual(r['quality']['status'], 'warning')
        self.assertIsNone(r['data']['page'])

    def test_quality_report_exposes_structured_overlay(self):
        r = srv.get_quality_report('600519', '2025')
        self.assertGreater(r['data']['structured_count'], 0)
        self.assertTrue(r['data']['structured_overlay'])
        self.assertIn('structured_status', r['quality'])

    def test_ratio_returns_evidence_objects(self):
        r = srv.get_ratio('600519', '2025', '毛利率')
        self.assertEqual(r['data']['ratios'][0]['value_type'], 'computed')
        self.assertGreaterEqual(len(r['evidence']), 2)
        for e in r['evidence']:
            self.assertTrue(e['evidence_id'])
            self.assertGreater(e['page'], 0)
            self.assertTrue(e['snippet'])

    def test_cash_flow_statement_stops_before_notes(self):
        r = srv.get_statement('002594', '2025', '合并现金流量表', limit=1)
        # 现金流量表正文约 60–70 行；超过 300 行说明扫进了附注/后续报表。
        self.assertLessEqual(r['meta']['total'], 300)
        self.assertGreater(r['meta']['total'], 0)

    def test_verify_match(self):
        r = srv.verify_fact('600519', '2025', 'cash', 51690610946.50)
        self.assertEqual(r['data']['verdict'], 'match')
        self.assertEqual(r['evidence'][0]['evidence_id'], '600519-2025-cash')

    def test_verify_mismatch(self):
        r = srv.verify_fact('600519', '2025', 'cash', 60000000000.0)
        self.assertEqual(r['data']['verdict'], 'mismatch')
        self.assertEqual(r['quality']['status'], 'fail')

    def test_evidence_by_metric(self):
        r = srv.get_evidence(stock_code='600519', period='2025', metric='revenue')
        self.assertEqual(r['data']['value'], 168838102514.79)
        self.assertEqual(r['evidence'][0]['page'], 61)
        self.assertIn('dataset_path', r['meta'])

    def test_unknown_evidence_refuses(self):
        r = srv.get_evidence('600519-2025-not_exist')
        self.assertEqual(r['error']['code'], 'EVIDENCE_NOT_FOUND')
        self.assertIsNone(r['data'])
        self.assertEqual(r['quality']['status'], 'fail')

    def test_unknown_metric_refuses(self):
        r = srv.verify_fact('600519', '2025', 'not_exist', 1.0)
        self.assertEqual(r['error']['code'], 'METRIC_NOT_FOUND')

    def test_path_traversal_refuses(self):
        r = srv.get_quality_report('../../etc', '2025')
        self.assertEqual(r['error']['code'], 'INVALID_CODE')
        r2 = srv.get_quality_report('600519', '../2024')
        self.assertEqual(r2['error']['code'], 'INVALID_PERIOD')
        r3 = srv.get_evidence('../../etc-2025-revenue')
        self.assertEqual(r3['error']['code'], 'EVIDENCE_NOT_FOUND')

    def test_small_value_tolerance_is_relative(self):
        # 每股收益 65.66，1% 容差约 0.66；旧实现的 1 元下限会误判 0.84 的偏差为 match
        r = srv.verify_fact('600519', '2025', 'basic_eps', 66.50)
        self.assertEqual(r['data']['verdict'], 'mismatch')

    def test_invalid_cursor_refuses(self):
        r = srv.get_statement('600519', '2025', cursor='abc')
        self.assertEqual(r['error']['code'], 'INVALID_CURSOR')

    def test_invalid_limit_refuses(self):
        r = srv.get_statement('600519', '2025', limit='abc')
        self.assertEqual(r['error']['code'], 'INVALID_LIMIT')

    def test_negative_tolerance_refuses(self):
        r = srv.verify_fact('600519', '2025', 'cash', 1.0, tolerance=-0.1)
        self.assertEqual(r['error']['code'], 'INVALID_TOLERANCE')

    def test_invalid_claim_refuses(self):
        r = srv.verify_fact('600519', '2025', 'cash', 'abc')
        self.assertEqual(r['error']['code'], 'INVALID_CLAIM')

    def test_shenhua_date_key_and_evidence_level(self):
        r = srv.get_evidence(stock_code='601088', period='2025', metric='cfo',
                             announce_date='2026-03-31')
        self.assertEqual(r['data']['value'], 75059.0)
        self.assertEqual(r['data']['company']['name'], '中国神华能源股份有限公司')
        self.assertEqual(r['data']['evidence_level'], 'verified')
        self.assertEqual(r['evidence'][0]['page'], 160)
        q = srv.get_quality_report('601088', '2025', announce_date='2026-03-31')
        self.assertEqual(q['data']['counts']['fail'], 0)
        self.assertEqual(q['data']['quality_gate'], 'pass')
        self.assertAlmostEqual(q['data']['coverage']['metric_coverage'], 0.9677, places=4)


if __name__ == '__main__':
    unittest.main()
