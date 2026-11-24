# -*- coding: utf-8 -*-
import unittest

from fin_evidence.extract import Word, Line, find_metric, _line_has_title
from fin_evidence.mapping import BY_KEY


def line(item, values=None, page=1):
    words = []
    cur = []
    for i, v in enumerate(values or []):
        w = Word(x0=300 + i * 100, x1=350 + i * 100, text=str(v), y=10)
        cur.append(w)
        words.append(w)
    label = Word(x0=80, x1=200, text=item, y=10) if item else None
    if label:
        words.insert(0, label)
    return Line(page=page, y=10, words=words, item=item, note='',
                current=cur, prior=[], raw=item, printed_page=page)


class TestFindMetricAnchor(unittest.TestCase):
    def test_multiline_label_takes_following_value_not_previous_row(self):
        lines = [
            line('资产处置收益'),
            line('（损失以“-”号填列）', [5397912.01]),
            line('三、营业利润（亏损以'),
            line('', [7490632003.88]),
            line('“-”号填列）'),
        ]
        found = find_metric([(1, lines)], BY_KEY['operating_profit'])
        self.assertIsNotNone(found)
        self.assertEqual(found[0], 7490632003.88)

    def test_combined_statement_continuation_is_not_parent_title(self):
        merged = line('合并及公司资产负债表(续)')
        self.assertFalse(_line_has_title(merged, '公司资产负债表'))
        self.assertTrue(_line_has_title(merged, '合并资产负债表'))


if __name__ == '__main__':
    unittest.main()
