"""近くの似た取引: 築年数・広さが同じなら、遠い町や地価の大きく違う町より、同じ町・近い町の取引を選ぶこと。"""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent


def near(sales, d, home):
    script = ("import {nearestSales} from './checker-site/near.mjs';"
              f"console.log(JSON.stringify(nearestSales({json.dumps(sales, ensure_ascii=False)},{json.dumps(d)},"
              f"{json.dumps(home, ensure_ascii=False)},3).map(x=>[x.s[2],x.km===null?null:Math.round(x.km)])));")
    out = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


class NearSalesTests(unittest.TestCase):
    d = {'year': 1990, 'landArea': 238, 'buildingArea': 172}
    sales = [[2025, 1, '遠い町', 300, 238, 172, 1990], [2025, 1, '近い町', 1200, 230, 170, 1991],
             [2025, 1, '自分の町', 1500, 200, 150, 1985], [2025, 1, '位置不明の安い町', 200, 238, 172, 1990],
             [2025, 1, '位置不明で地価が近い町', 1400, 238, 172, 1990]]
    towns = {'遠い町': [34.10, 131.20], '近い町': [34.005, 131.21], '自分の町': [34.00, 131.205]}

    def test_same_and_close_towns_come_first(self):
        home = {'district': '自分の町', 'towns': self.towns, 'pos': self.towns['自分の町'],
                'landPrices': {'位置不明の安い町': 5000, '位置不明で地価が近い町': 30000}, 'landPrice': 30000}
        got = near(self.sales, self.d, home)
        self.assertEqual([g[0] for g in got], ['近い町', '自分の町', '位置不明で地価が近い町'])
        self.assertEqual(got[1][1], 0)

    def test_without_positions_the_land_price_decides(self):
        home = {'district': '', 'towns': {}, 'pos': None,
                'landPrices': {'位置不明の安い町': 5000, '位置不明で地価が近い町': 30000}, 'landPrice': 30000}
        names = [g[0] for g in near(self.sales, self.d, home)]
        self.assertLess(names.index('位置不明で地価が近い町'), len(names))
        self.assertNotIn('位置不明の安い町', names[:1])


if __name__ == '__main__':
    unittest.main()
