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

    def test_score(self):
        s = auto.score(np.array([90.0, 150.0]), np.array([100.0, 100.0]))
        self.assertEqual((s['median_ape_pct'], s['within20_pct']), (30.0, 50.0))


if __name__ == '__main__':
    unittest.main()
