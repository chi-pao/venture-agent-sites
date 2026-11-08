"""The monthly retraining must fill blank station minutes the way the page does and build the page's inputs."""
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'checker_train'))
spec = importlib.util.spec_from_file_location('auto_retrain', ROOT / 'tools' / 'checker_train' / 'auto_retrain.py')
auto = importlib.util.module_from_spec(spec); spec.loader.exec_module(auto)


def rows(**columns):
    base = {'MunicipalityCode': '35202', 'DistrictName': '大字際波', 'StationMinutes': np.nan, 'Prefecture': '山口県',
            'TransactionYear': 2025, 'Quarter': 2, 'BuildingAge': 25, 'Area': 238.0, 'TotalFloorArea': 172.0,
            'Structure': '木造', 'CityPlanning': np.nan, 'price_yen': 1.78e7}
    n = max(len(v) for v in columns.values())
    return pd.DataFrame({k: columns.get(k, [v] * n) for k, v in base.items()})


class AutoRetrainTests(unittest.TestCase):
    def test_station_table_uses_district_with_three_sales_else_municipality(self):
        table = auto.station_table(rows(DistrictName=['大字際波'] * 3 + ['大字東岐波'] * 2, StationMinutes=[20, 23, 30, 5, 7]))
        self.assertEqual(table['35202']['大字際波'], 23)
        self.assertNotIn('大字東岐波', table['35202'])
        self.assertEqual(table['35202'][''], 20)

    def test_blank_station_minutes_are_filled_and_entered_ones_kept(self):
        table = {'35202': {'': 15, '大字際波': 23}}
        out = auto.fill_station(rows(DistrictName=['大字際波', '開', '開'], StationMinutes=[np.nan, np.nan, 9]), table)
        self.assertEqual(out['StationMinutes'].tolist(), [23, 15, 9])

    def test_site_inputs_match_the_page(self):
        [d] = auto.site_inputs(rows(StationMinutes=[23]))
        self.assertEqual(d, {'type': 'used_house', 'prefecture': '山口県', 'city': '35202', 'price': 1, 'district': '大字際波',
                             'year': 2000, 'landArea': 238.0, 'buildingArea': 172.0, 'structure': '木造', 'stationMinutes': 23})

    def test_candidates_are_judged_against_the_served_recipe_retrained_alike(self):
        def c(ape, within):
            return {'median_ape_pct': ape, 'within20_pct': within}
        report = {'live': c(12.0, 63.0), 'candidates': {'filled': c(20.2, 49.7), 'filled+land': c(19.8, 50.4)}}
        self.assertEqual(auto.decide(report, 'filled'), ('filled+land', True))
        report['candidates']['filled+land'] = c(20.0, 50.0)
        self.assertEqual(auto.decide(report, 'filled'), ('filled+land', False))
        report['candidates']['filled+land'] = c(19.8, 48.0)
        self.assertEqual(auto.decide(report, 'filled'), ('filled+land', False))
        self.assertEqual(auto.decide(report, 'filled+land'), ('filled+land', False))
        self.assertEqual(auto.decide(report, 'unknown'), ('filled+land', False))

    def test_period_labels(self):
        self.assertEqual(auto.period_label(2026 * 4, 2026 * 4 + 1), '2026年1〜6月')
        self.assertEqual(auto.period_label(2025 * 4 + 3, 2026 * 4), '2025年10月〜2026年3月')
        self.assertEqual(auto.month_end(2025 * 4 + 3), '2025年12月')

    def test_score(self):
        s = auto.score(np.array([90.0, 150.0]), np.array([100.0, 100.0]))
        self.assertEqual((s['median_ape_pct'], s['within20_pct']), (30.0, 50.0))



class FetchMlitTests(unittest.TestCase):
    def test_gzip_and_plain_api_bodies_decode(self):
        import gzip, json
        spec = importlib.util.spec_from_file_location('fetch_mlit', ROOT / 'tools' / 'checker_train' / 'fetch_mlit.py')
        fetch = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetch)
        body = json.dumps({'status': 'OK', 'data': [{'TradePrice': '17800000', 'DistrictName': '大字際波'}]}, ensure_ascii=False).encode()
        self.assertEqual(json.loads(fetch.decode(gzip.compress(body)))['data'][0]['DistrictName'], '大字際波')
        self.assertEqual(json.loads(fetch.decode(body))['status'], 'OK')

    def test_quarters_are_the_latest_ones_in_order(self):
        from datetime import datetime
        spec = importlib.util.spec_from_file_location('fetch_mlit', ROOT / 'tools' / 'checker_train' / 'fetch_mlit.py')
        fetch = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetch)
        self.assertEqual(fetch.quarters(3, datetime(2026, 11, 2)), [(2026, 1), (2026, 2), (2026, 3)])


if __name__ == '__main__':
    unittest.main()
