# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fin_evidence.server as srv
from fin_evidence.sina import build_comparison, parse_report
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

    def test_build_overlay_classifies_later_filing_as_restatement(self):
        facts = [{'metric': 'revenue', 'value': 100.0, 'unit': '元'}]
        fetched = {'metrics': {
            'revenue': {'metric': 'revenue', 'value': 108.0, 'unit': '元',
                        'api_notice_date': '2025-03-28',
                        'quality': {'status': 'warning', 'checks': ['no_page_evidence'],
                                    'messages': []}},
        }, 'provider': 'eastmoney', 'fetched_at': '', 'report_date': '2024-12-31', 'errors': []}
        out = build_overlay(facts, fetched, '2024-03-28')
        self.assertEqual(out['cross_check']['restatement'], 1)
        self.assertEqual(out['metrics']['revenue']['cross_check']['status'], 'restatement')
        self.assertTrue(out['metrics']['revenue']['cross_check']['later_filing'])

    def test_build_overlay_material_restatement_is_warning(self):
        facts = [{'metric': 'revenue', 'value': 100.0, 'unit': '元'}]
        fetched = {'metrics': {
            'revenue': {'metric': 'revenue', 'value': 150.0, 'unit': '元',
                        'api_notice_date': '2025-03-28',
                        'quality': {'status': 'warning', 'checks': ['no_page_evidence'],
                                    'messages': []}},
        }, 'provider': 'eastmoney', 'fetched_at': '', 'report_date': '2024-12-31', 'errors': []}
        out = build_overlay(facts, fetched, '2024-03-28')
        self.assertEqual(out['metrics']['revenue']['cross_check']['status'], 'restatement_material')
        self.assertEqual(out['cross_check']['restatement_material'], 1)

    def test_sina_tsv_parser_selects_exact_report_date(self):
        text = (
            '报表日期\t20251231\t20250930\t19700101\t\n'
            '单位\t元\t元\t\t\n'
            '一、营业总收入\t172054171890.91\t130903889634.88\t0\t\n'
            '销售商品、提供劳务收到的现金\t183990403487.80\t138791719991.59\t0\t\n'
            '基本每股收益(元/股)\t65.660000\t51.530000\t0\t\n'
        )
        parsed = parse_report(text, '2025-12-31', '合并利润表', '600519', 'https://example.test')
        self.assertEqual(parsed['metrics']['total_revenue']['value'], 172054171890.91)
        self.assertEqual(parsed['metrics']['basic_eps']['value'], 65.66)

    def test_three_source_comparison_marks_verified_isolated(self):
        facts = [{'metric': 'revenue', 'value': 200.0, 'unit': '元'}]
        east = {'metrics': {'revenue': {'metric': 'revenue', 'value': 100.0, 'unit': '元',
                                        'api_notice_date': '2025-03-28'}}}
        sina = {'metrics': {'revenue': {'metric': 'revenue', 'value': 100.0, 'unit': '元',
                                        'source_label': '营业收入', 'source_url': 'https://x'}}}
        out = build_comparison(facts, east, sina, '2024-03-28')
        self.assertEqual(out['rows']['revenue']['status'], 'verified_isolated')

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
