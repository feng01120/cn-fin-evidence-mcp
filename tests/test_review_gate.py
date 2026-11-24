# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

import fin_evidence.server as srv
from fin_evidence.store import list_datasets, structured_fact

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


class TestReviewGate(unittest.TestCase):
    def test_reviewed_material_datasets_are_pass_with_restatement(self):
        datasets = list_datasets(DATA)
        gates = {d['cross_source_gate'] for d in datasets}
        self.assertEqual(gates, {'pass', 'pass_with_restatement'})
        expected = {
            ('002594', '2023'), ('300750', '2023'), ('600690', '2023'),
            ('601088', '2024'), ('601088', '2025'),
        }
        actual = {(d['code'], d['period']) for d in datasets
                  if d['cross_source_gate'] == 'pass_with_restatement'}
        self.assertEqual(actual, expected)
        for d in datasets:
            self.assertEqual(d['cross_source_review']['unreviewed'], [])

    def test_quality_and_comparison_expose_restatement_status(self):
        q = srv.get_quality_report('601088', '2025')
        self.assertEqual(q['quality']['status'], 'pass_with_restatement')
        self.assertEqual(q['quality']['unreviewed_material'], [])
        self.assertIn('total_assets', q['quality']['reviewed_material'])
        c = srv.get_source_comparison('601088', '2025', 'total_assets')
        self.assertEqual(c['quality']['status'], 'pass_with_restatement')
        self.assertEqual(c['data']['metrics']['total_assets']['status'], 'restatement_material')

    def test_reviewed_structured_fact_is_warning_not_fail(self):
        r = srv.get_evidence('601088-2025-total_assets-structured')
        self.assertEqual(r['quality']['status'], 'warning')
        self.assertIn('reviewed_restatement', r['quality']['checks'])
        self.assertEqual(r['evidence'], [])
        self.assertIsNone(r['data']['page'])
        self.assertTrue(r['meta']['reviewed_restatement'])

    def test_verify_fact_distinguishes_original_and_restated(self):
        origin = srv.verify_fact('601088', '2025', 'total_assets', 627761)
        self.assertEqual(origin['data']['verdict'], 'match')
        restated = srv.verify_fact('601088', '2025', 'total_assets', 903830)
        self.assertEqual(restated['data']['verdict'], 'restatement_match')
        self.assertEqual(restated['data']['restated_value'], 903830)
        self.assertEqual(restated['quality']['status'], 'warning')
        self.assertIn('restatement_not_current', restated['quality']['checks'])
        wrong = srv.verify_fact('601088', '2025', 'total_assets', 999999)
        self.assertEqual(wrong['quality']['status'], 'fail')

    def test_unreviewed_material_and_isolated_still_fail(self):
        meta = {'company': {'code': 'TEST'}, 'period': '2025',
                'report_date': '2025-12-31', 'announce_date': '2026-03-31'}
        material = {'metric': 'cash', 'value': 1, 'statement': '合并资产负债表',
                    'quality': {'status': 'fail', 'checks': ['no_page_evidence']},
                    'cross_check': {'status': 'restatement_material'}}
        self.assertEqual(structured_fact(meta, material, reviewed=False)['quality']['status'], 'fail')
        reviewed = structured_fact(meta, material, reviewed=True)
        self.assertEqual(reviewed['quality']['status'], 'warning')
        self.assertIn('reviewed_restatement', reviewed['quality']['checks'])
        isolated = dict(material, cross_check={'status': 'verified_isolated'})
        self.assertEqual(structured_fact(meta, isolated, reviewed=True)['quality']['status'], 'fail')

    def test_material_ledger_has_ten_confirmed_items(self):
        ledger = json.loads((DATA / 'material_review.json').read_text(encoding='utf-8'))
        self.assertEqual(ledger['summary']['total'], 10)
        self.assertEqual(ledger['summary']['confirmed_restatement'], 10)
        self.assertEqual(ledger['summary']['extraction_errors'], 0)
        self.assertEqual(ledger['summary']['gate_changes']['after']['error_count'], 0)
        self.assertTrue(ledger['summary']['gate_changes']['after']['acceptance'])
        for item in ledger['items']:
            self.assertEqual(item['review']['verdict'], 'confirmed_restatement')
            self.assertFalse(item['review']['extraction_error'])


if __name__ == '__main__':
    unittest.main()
