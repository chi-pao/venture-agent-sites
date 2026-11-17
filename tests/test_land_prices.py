"""公示地価の手がかり: 町名のそろえ方、表の引き方、学習とサイトで同じ値になること。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'checker_train'))
sys.path.insert(0, str(ROOT))
import land_prices as L  # noqa: E402
from tests import test_auto_retrain as R  # noqa: E402


class LandPriceTests(unittest.TestCase):
    def test_town_names_from_addresses_and_districts_line_up(self):
        self.assertEqual(L.address_town('北海道　札幌市中央区南１条西９丁目１番'), '南')
        self.assertEqual(L.town_key('南一条西'), '南')
        self.assertEqual(L.address_town('山口県　宇部市大字際波字中尾１２３番'), '際波')
        self.assertEqual(L.town_key('大字際波'), '際波')
        self.assertEqual(L.address_town('山口県　下関市山の田中央町１２番３'), '山の田中央町')
        self.assertEqual(L.address_town('福岡県　糟屋郡粕屋町大字仲原２５５５番'), '仲原')

    def test_both_land_price_surveys_are_read(self):
        import tempfile
        def fc(props):
            return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': p, 'geometry': None} for p in props]}
        l01 = fc([{'L01_001': '35202', 'L01_008': 40000, 'L01_025': '山口県　宇部市大字際波字中尾１番', 'L01_028': '住宅'},
                  {'L01_001': '35202', 'L01_008': 90000, 'L01_025': '山口県　宇部市常盤町１丁目１番', 'L01_028': '店舗'}])
        l02 = fc([{'L02_020': '35202', 'L02_006': 42000, 'L02_022': '山口県　宇部市大字際波２番', 'L02_025': '住宅'}])
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, data in (('a.geojson', l01), ('b.geojson', l02)):
                path = Path(d) / name
                path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                paths.append(path)
            self.assertEqual(L.point_prices(*paths), {'35202': {'': 41000, '際波': 41000}})
            self.assertEqual(L.point_prices(paths[0]), {'35202': {'': 40000, '際波': 40000}})

    def test_site_table_keys_are_the_transaction_names(self):
        points = {'35202': {'': 30000, '際波': 41000}}
        table = L.site_table(points, R.rows(DistrictName=['大字際波', '開']))
        self.assertEqual(table, {'35202': {'': 30000, '大字際波': 41000}})

    def test_lookup_prefers_town_then_municipality(self):
        table = {'35202': {'': 30000, '大字際波': 41000}}
        self.assertEqual(L.lookup(table, '35202', '大字際波'), (41000, 2))
        self.assertEqual(L.lookup(table, '35202', '開'), (30000, 1))
        self.assertEqual(L.lookup(table, '99999', '開'), (None, 0))
        out = L.add_features(R.rows(DistrictName=['大字際波', '開'], MunicipalityCode=['35202', '99999']), table)
        self.assertAlmostEqual(out['LandPrice'][0], np.log(41000))
        self.assertTrue(np.isnan(out['LandPrice'][1]))
        self.assertEqual(out['LandPriceMatchLevel'].tolist(), [2, 0])
        self.assertAlmostEqual(out['LandValue'][0], np.log(41000) + np.log(238.0))

    def test_site_inputs_carry_land_price_and_the_page_builds_the_same_features(self):
        table = {'35202': {'': 30000, '大字際波': 41000}}
        [d] = R.auto.site_inputs(R.rows(StationMinutes=[23]), table)
        self.assertEqual((d['landPrice'], d['landPriceLevel']), (41000, 2))
        script = ("import {features} from './checker-site/engine.mjs';"
                  f"const f=features({json.dumps(d, ensure_ascii=False)});"
                  "console.log(JSON.stringify([f.LandPrice,f.LandPriceMatchLevel,f.LandValue]));")
        got = json.loads(subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True,
                                        capture_output=True, text=True).stdout)
        expected = L.add_features(R.rows(StationMinutes=[23]), table)
        self.assertAlmostEqual(got[0], expected['LandPrice'][0])
        self.assertEqual(got[1], 2)
        self.assertAlmostEqual(got[2], expected['LandValue'][0])

    def test_page_without_land_price_leaves_the_features_blank(self):
        script = ("import {features} from './checker-site/engine.mjs';"
                  "const f=features({type:'used_house',landArea:100,buildingArea:80,year:2000});"
                  "console.log(JSON.stringify([f.LandPrice,f.LandPriceMatchLevel,f.LandValue]));")
        out = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(out.stdout), [None, 0, None])

    def test_bundled_table_covers_every_municipality_with_sane_prices(self):
        table = json.loads((ROOT / 'checker-site' / 'land-prices.json').read_text(encoding='utf-8'))
        self.assertGreater(len(table), 1500)
        values = [v for e in table.values() for v in e.values()]
        self.assertTrue(all(isinstance(v, int) and 100 <= v <= 50_000_000 for v in values))
        self.assertTrue(all('' in e for e in table.values()))


if __name__ == '__main__':
    unittest.main()
