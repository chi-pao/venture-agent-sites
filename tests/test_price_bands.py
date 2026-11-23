"""結果画面の価格の幅（price-bands.json）: 場所・築年数・査定額の区分がそろい、幅が実際の取引から外れていないこと。"""
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'checker_train'))
import build_bands as B  # noqa: E402


class PriceBandTests(unittest.TestCase):
    def test_bundled_bands(self):
        data = json.loads((ROOT / 'checker-site' / 'price-bands.json').read_text(encoding='utf-8'))
        self.assertEqual(data['edges'], [800, 1500, 2500, 4000])
        self.assertEqual(set(data['bands']['all']), {'0', '1', '2', '3', '4'})
        for key in ('都会', '中堅都市', '田舎'):
            for age in ('・築30年未満', '・築30年以上'):
                self.assertIn(key + age, data['bands'])
        for cell in data['bands'].values():
            for lo, hi, n in cell.values():
                self.assertTrue(0.3 < lo < 1 < hi < 2.5 and n >= B.MIN_N)
        self.assertEqual(data['classes']['13101'], '都会')
        self.assertEqual(data['classes']['35202'], '中堅都市')

    def test_area_class_and_buckets(self):
        stats = {'1': {'pop': 600000, 'density': 100}, '2': {'pop': 50000, 'density': 5000},
                 '3': {'pop': 150000, 'density': 500}, '4': {'pop': 20000, 'density': 50}}
        self.assertEqual([B.area_class(stats, c) for c in '1234'], ['都会', '都会', '中堅都市', '田舎'])
        self.assertEqual([B.bucket(v) for v in (500, 800, 1499, 3000, 9000)], [0, 1, 1, 3, 4])

    def test_small_cells_are_left_out(self):
        rng = np.random.default_rng(1)
        n = 400
        rows = pd.DataFrame({'MunicipalityCode': ['35202'] * n, 'BuildingAge': [40] * n,
                             'price_yen': rng.uniform(5e6, 7e6, n)})
        out = B.build(rows, {'35202': {'pop': 160000, 'density': 500}}, np.full(n, 6e6))
        cell = out['bands']['中堅都市・築30年以上']
        self.assertIn('0', cell)
        self.assertNotIn('中堅都市・築30年未満', [k for k, v in out['bands'].items() if v])


if __name__ == '__main__':
    unittest.main()
