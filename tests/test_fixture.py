# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

from fin_evidence.extract import normalize_label
from fin_evidence.models import Evidence, Company
from fin_evidence.ratios import compute_ratios

ROOT = Path(__file__).resolve().parents[1]


class TestNormalize(unittest.TestCase):
    def test_prefix_and_paren(self):
        self.assertEqual(normalize_label('其中：营业收入'), '营业收入')
        self.assertEqual(normalize_label('所有者权益（或股东权益）合计'), '所有者权益合计')
        self.assertEqual(normalize_label('五、净利润（净亏损以“－”号填列）'), '净利润')
        self.assertEqual(normalize_label('1.归属于母公司股东的净利润'), '归属于母公司股东的净利润')


class TestFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = ROOT / 'data' / '600519' / '2025'
        cls.facts = json.loads((d / 'facts.json').read_text(encoding='utf-8'))
        cls.ratios = json.loads((d / 'ratios.json').read_text(encoding='utf-8'))
        cls.checks = json.loads((d / 'checks.json').read_text(encoding='utf-8'))

    def test_six_tuple(self):
        for f in self.facts:
            self.assertTrue(f['company']['code'])
            self.assertEqual(f['period'], '2025')
            self.assertTrue(f['metric'])
            self.assertIsNotNone(f['value'])
            self.assertTrue(f['unit'])
            self.assertGreater(f['page'], 0)
            self.assertTrue(f['snippet'])
            self.assertTrue(f['evidence_id'])

    def test_unique_ids(self):
        ids = [f['evidence_id'] for f in self.facts]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ratios(self):
        by = {r['ratio']: r for r in self.ratios}
        self.assertAlmostEqual(by['gross_margin']['value'], 91.18, places=1)
        self.assertAlmostEqual(by['net_margin']['value'], 50.53, places=1)
        self.assertAlmostEqual(by['roe']['value'], 34.46, places=1)
        self.assertAlmostEqual(by['debt_ratio']['value'], 16.42, places=1)
        self.assertAlmostEqual(by['current_ratio']['value'], 5.09, places=1)
        for r in self.ratios:
            self.assertTrue(r['formula'])
            self.assertTrue(r['inputs'])
            self.assertTrue(r['evidence'])

    def test_ratio_missing_prior_is_warning(self):
        facts = [Evidence(**f) for f in self.facts]
        for f in facts:
            if f.metric == 'equity_parent':
                f.prior_value = None
        ratios = compute_ratios(Company(code='600519', name='贵州茅台'), '2025', facts)
        roe = next(r for r in ratios if r.ratio == 'roe')
        self.assertIsNone(roe.value)
        self.assertEqual(roe.quality.status, 'warning')

    def test_checks(self):
        self.assertEqual(len([c for c in self.checks if c['status'] == 'fail']), 0)
        names = {c['check'] for c in self.checks if c['status'] == 'pass'}
        self.assertEqual(names, {'balance_identity', 'total_le_identity',
                                 'cash_flow_identity', 'cash_roll', 'growth_anomaly'})


if __name__ == '__main__':
    unittest.main()
