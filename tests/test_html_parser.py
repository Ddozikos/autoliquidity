import unittest
from collections import Counter
from pathlib import Path

from app.services.html_parser import parse_html

ROOT = Path(__file__).resolve().parents[1]


class FsspHtmlParserTests(unittest.TestCase):
    def test_multi_act_reference_document(self):
        path = ROOT / 'samples' / 'Пример ЗРД.html'
        if not path.exists():
            self.skipTest('user-provided reference files are not included in the distributable archive')
        rows = parse_html(path.read_bytes())
        self.assertEqual(len(rows), 12)
        self.assertEqual({row['doc_type'] for row in rows}, {'ban'})
        first = rows[0]
        self.assertEqual(first['vin'], '5TDDKRFH30S008927')
        self.assertEqual((first['make'], first['model'], first['year']), ('TOYOTA', 'HIGHLANDER', '2014'))
        self.assertAlmostEqual(first['debt_amount'], 82808.03)
        self.assertEqual(first['doc_number'], '66007/23/532219')

    def test_removed_restriction_is_not_a_ban(self):
        path = ROOT / 'samples' / 'fssp_100_dokumentov' / 'html' / '099_Toyota_Avensis.html'
        if not path.exists():
            self.skipTest('user-provided reference files are not included in the distributable archive')
        rows = parse_html(path.read_bytes())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['doc_type'], 'removal')
        self.assertEqual(rows[0]['vin'], 'JTNBE46KX73123456')
        self.assertEqual(rows[0]['plate'], 'Э555КК 799')
        self.assertAlmostEqual(rows[0]['debt_amount'], 415219.37)
        self.assertNotIn('price', rows[0])
        self.assertNotIn('demand', rows[0])

    def test_sample_corpus_has_no_unparsed_html_files(self):
        corpus = ROOT / 'samples' / 'fssp_100_dokumentov' / 'html'
        if not corpus.exists():
            self.skipTest('user-provided reference files are not included in the distributable archive')
        paths = sorted(corpus.glob('*.html'))
        self.assertEqual(len(paths), 100)
        rows = [row for path in paths for row in parse_html(path.read_bytes())]
        self.assertEqual(len(rows), 100)
        self.assertEqual(Counter(row['doc_type'] for row in rows), {'ban': 59, 'removal': 41})
        self.assertEqual(sum(row['debt_amount'] is None for row in rows), 0)
        # One source document deliberately masks its VIN; the parser must not
        # turn that mask into a plausible identifier.
        self.assertEqual(sum(row['vin'] is None for row in rows), 1)


if __name__ == '__main__':
    unittest.main()
