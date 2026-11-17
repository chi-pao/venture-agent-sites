"""町ごとの値段の目安: 件数の少ない町は上の段階に寄せること、学習では自分を含まないこと、サイトと同じ値になること。"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'checker_train'))
sys.path.insert(0, str(ROOT))
import town_prices as TP  # noqa: E402
from tests import test_auto_retrain as R  # noqa: E402


class TownPriceTests(unittest.TestCase):
    def frame(self):
        return R.rows(DistrictName=['大字際波'] * 3 + ['開'], price_yen=[2e7, 2e7, 2e7, 1e7], Area=[200.0] * 4)

    def test_small_towns_lean_on_the_municipality(self):
        t = TP.build(self.frame())
        glob = np.mean(np.log([1e5, 1e5, 1e5, 5e4]))
        muni = (np.log(1e5) * 3 + np.log(5e4) + glob * TP.K) / (4 + TP.K)
        self.assertAlmostEqual(t['35202'][''], muni, places=3)
        self.assertAlmostEqual(t['35202']['開'], (np.log(5e4) + muni * TP.K) / (1 + TP.K), places=3)
        self.assertEqual(TP.lookup(t, '35202', '不明町'), t['35202'][''])
        self.assertEqual(TP.lookup(t, '99999', '開'), t['*'][''])

    def test_training_values_leave_the_sale_itself_out(self):
        rows = self.frame()
        out = TP.add_out_of_fold(rows, folds=4, seed=0)
        full = TP.add_feature(rows, TP.build(rows))
        self.assertFalse(np.allclose(out[TP.FEATURE], full[TP.FEATURE]))

    def test_page_builds_the_same_feature(self):
        t = TP.build(self.frame())
        [d] = R.auto.site_inputs(R.rows(StationMinutes=[23]), None, t)
        self.assertAlmostEqual(d['townLogPpm'], t['35202']['大字際波'])
        script = ("import {features} from './checker-site/engine.mjs';"
                  f"console.log(JSON.stringify(features({json.dumps(d, ensure_ascii=False)}).TownLogPpm));")
        out = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertAlmostEqual(json.loads(out.stdout), d['townLogPpm'])


if __name__ == '__main__':
    unittest.main()
