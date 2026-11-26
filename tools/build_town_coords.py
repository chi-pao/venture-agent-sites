"""結果画面の「近くの似た取引」を、家に近い町から選ぶための町の位置（緯度・経度）の表を作る。

公示地価（L01）と都道府県地価調査（L02）の地点（どちらも国土数値情報・無料）の住所から町の名前を取り出し、
町ごとの地点の平均の位置を、その町の位置とする。checker-site/area/<市区町村コード>/towns.json に
{"取引データの町名": [緯度, 経度], ...} を書く（キーは sales.json と land-prices.json の町名）。

  python tools/build_town_coords.py --l01 L01-25.geojson --l02 L02-25.geojson --site checker-site
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / 'checker_train'))
import land_prices as L  # noqa: E402


def town_points(*geojsons):
    """{(市区町村コード, 町の名前): (緯度, 経度)}（地点の平均）。"""
    acc = defaultdict(list)
    for path in geojsons:
        for f in json.loads(Path(path).read_text(encoding='utf-8'))['features']:
            p, g = f['properties'], f.get('geometry') or {}
            if g.get('type') != 'Point':
                continue
            code_k, _, addr_k, _ = L.FIELDS['L02' if 'L02_020' in p else 'L01']
            town = L.address_town(p[addr_k])
            if town:
                lon, lat = g['coordinates'][:2]
                acc[(str(p[code_k]).zfill(5), town)].append((lat, lon))
    return {k: tuple(round(float(x), 5) for x in np.mean(v, axis=0)) for k, v in acc.items()}


def town_table(points, code, names):
    out = {}
    for name in sorted(set(names)):
        pos = points.get((code, L.town_key(name)))
        if pos:
            out[name] = list(pos)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--l01', required=True); p.add_argument('--l02'); p.add_argument('--site', type=Path, required=True)
    a = p.parse_args()
    points = town_points(*[x for x in (a.l01, a.l02) if x])
    land = json.loads((a.site / 'land-prices.json').read_text(encoding='utf-8'))
    found = total = 0
    for sales_path in sorted((a.site / 'area').glob('*/sales.json')):
        code = sales_path.parent.name
        sales = json.loads(sales_path.read_text(encoding='utf-8'))
        names = [s[2] for s in sales if s[2]] + [k for k in land.get(code, {}) if k]
        table = town_table(points, code, names)
        found += sum(1 for s in sales if s[2] in table); total += len(sales)
        (sales_path.parent / 'towns.json').write_text(json.dumps(table, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'位置が分かった取引: {found}/{total}（{found / max(total, 1):.0%}）')


if __name__ == '__main__':
    main()
