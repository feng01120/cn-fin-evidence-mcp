# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fin_evidence.server as srv
from fin_evidence.structured import build_overlay
from fin_evidence.subject import evaluate, evaluate_fact
from fin_evidence.store import load_dataset, structured_fact


class TestSubjectGuard(unittest.TestCase):
    def test_statement_and_alias_match(self):
        q = evaluate('revenue', '合并利润表', '营业收入')
        self.assertEqual(q.status, 'pass')
        self.assertIn('alias_match', q.checks)
        self.assertIn('statement_match', q.checks)

    def test_wrong_statement_is_fail(self):
        q = evaluate('revenue', '合并资产负债表', '营业收入')
        self.assertEqual(q.status, 'fail')
        self.assertTrue(any('预期在' in m for m in q.messages))

    def test_unknown_metric_is_fail(self):
        self.assertEqual(evaluate('not_exist', '合并利润表').status, 'fail')

    def test_structured_skips_chinese_alias(self):
        q = evaluate('revenue', '合并利润表', 'TOTAL_OPERATE_INCOME',
                     source_type='structured_api')
        self.assertEqual(q.status, 'pass')
        self.assertIn('statement_match', q.checks)

    def test_existing_subject_failure_stays_fail(self):
        fact = {'metric': 'cash', 'statement': '合并资产负债表', 'item_raw': '货币资金',
                'subject_check': {'status': 'fail', 'messages': ['bad']}}
        self.assertEqual(evaluate_fact(fact).status, 'fail')


class TestStructuredOverlay(unittest.TestCase):
    def test_structured_fact_has_no_page(self):
        meta = {'company': {'code': '600519', 'name': '贵州茅台'},
                'period': '2025', 'report_date': '2025-12-31', 'announce_date': '2026-04-17'}
        entry = {'metric': 'revenue', 'metric_name': '营业收入', 'value': 1.0,
                 'unit': '元', 'statement': '合并利润表', 'api_field': 'TOTAL_OPERATE_INCOME',
                 'report_name': 'RPT_DMSK_FN_INCOME', 'source_url': 'https://example.test'}
        f = structured_fact(meta, entry)
        self.assertEqual(f['evidence_level'], 'structured')
        self.assertIsNone(f['page'])
        self.assertEqual(f['snippet'], '')
        self.assertEqual(f['quality']['status'], 'warning')
        self.assertIn('no_page_evidence', f['quality']['checks'])

    def test_build_overlay_keeps_both_values(self):
        facts = [{'metric': 'revenue', 'value': 100.0, 'unit': '元'}]
        fetched = {'metrics': {
            'revenue': {'metric': 'revenue', 'value': 101.0, 'unit': '元',
                        'quality': {'status': 'warning', 'checks': ['no_page_evidence'],
                                    'messages': []}},
            'cash': {'metric': 'cash', 'value': 10.0, 'unit': '元',
                     'quality': {'status': 'warning', 'checks': ['no_page_evidence'],
                                 'messages': []}},
        }, 'provider': 'test', 'fetched_at': '', 'report_date': '2025-12-31', 'errors': []}
        out = build_overlay(facts, fetched)
        self.assertEqual(out['cross_check']['pass'], 1)
        self.assertEqual(out['cross_check']['missing'], 1)
        self.assertEqual(out['metrics']['revenue']['cross_check']['status'], 'pass')

    def test_server_falls_back_to_structured_without_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            d = base / '600519' / '2025-12-31' / '2026-04-17'
            d.mkdir(parents=True)
            (d / 'meta.json').write_text('''{
              "company": {"code": "600519", "name": "贵州茅台"},
              "period": "2025", "report_date": "2025-12-31",
              "announce_date": "2026-04-17", "source_file": "x.pdf",
              "source_sha256": "x", "page_count": 1, "extracted_at": "x",
              "statements": [], "fact_count": 0, "row_count": 0,
              "evidence_level": "verified"
            }''', encoding='utf-8')
            (d / 'facts.json').write_text('[]', encoding='utf-8')
            (d / 'structured.json').write_text('''{
              "metrics": {"revenue": {
                "metric": "revenue", "metric_name": "营业收入", "value": 1.0,
                "unit": "元", "statement": "合并利润表",
                "api_field": "TOTAL_OPERATE_INCOME", "report_name": "RPT_DMSK_FN_INCOME",
                "source_url": "https://example.test",
                "quality": {"status": "warning", "checks": ["no_page_evidence"], "messages": []}
              }}
            }''', encoding='utf-8')
            with patch.object(srv, 'BASE', base):
                r = srv.get_evidence(stock_code='600519', period='2025', metric='revenue')
                self.assertEqual(r['meta']['evidence_level'], 'structured')
                self.assertEqual(r['evidence'], [])
                self.assertEqual(r['quality']['status'], 'warning')
                v = srv.verify_fact('600519', '2025', 'revenue', 1.0)
                self.assertEqual(v['data']['verdict'], 'match')
                self.assertEqual(v['data']['evidence_level'], 'structured')
                self.assertEqual(v['evidence'], [])
                self.assertEqual(v['quality']['status'], 'warning')

    def test_load_dataset_exposes_structured_only_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            d = base / '600519' / '2025-12-31' / '2026-04-17'
            d.mkdir(parents=True)
            (d / 'meta.json').write_text('''{
              "company": {"code": "600519", "name": "贵州茅台"},
              "period": "2025", "report_date": "2025-12-31",
              "announce_date": "2026-04-17", "source_file": "x.pdf",
              "source_sha256": "x", "page_count": 1, "extracted_at": "x",
              "statements": [], "fact_count": 0, "row_count": 0
            }''', encoding='utf-8')
            (d / 'facts.json').write_text('[]', encoding='utf-8')
            (d / 'structured.json').write_text('''{
              "metrics": {"revenue": {
                "metric": "revenue", "metric_name": "营业收入", "value": 1.0,
                "unit": "元", "statement": "合并利润表",
                "api_field": "TOTAL_OPERATE_INCOME", "report_name": "RPT_DMSK_FN_INCOME",
                "source_url": "https://example.test",
                "quality": {"status": "warning", "checks": ["no_page_evidence"], "messages": []}
              }}
            }''', encoding='utf-8')
            ds = load_dataset(base, '600519', '2025', '2026-04-17')
            self.assertEqual(len(ds['structured_facts']), 1)
            self.assertIsNone(ds['structured_facts'][0]['page'])


if __name__ == '__main__':
    unittest.main()
