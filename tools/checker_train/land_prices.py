"""公示地価（国土数値情報 L01・無料）を、中古戸建ての査定の手がかりにする。

1. L01 の地点（住宅地だけ）から、市区町村ごと・町名ごとの地価（1㎡あたりの円、中央値）を求める。
2. 取引データにある町名（地区名）と、地点の住所の町名を同じ切り方でそろえて結びつける。
3. サイトが読む表 checker-site/land-prices.json を書く:
   {"市区町村コード": {"": 市区町村の地価, "取引データの町名": 町の地価, ...}}
   町の地価が分からない町は、市区町村の地価を使う（サイトも学習も同じ表を同じように引く）。

都道府県地価調査（L02・無料、7月1日時点）の地点も足すと、町まで分かる取引が約54%から約67%に増える。

データの取得（L01 は3月下旬、L02 は9月ごろに新しい年が出る。各20MB前後）:
  curl -O https://nlftp.mlit.go.jp/ksj/gml/data/L01/L01-25/L01-25_GML.zip && unzip L01-25_GML.zip
  curl -O https://nlftp.mlit.go.jp/ksj/gml/data/L02/L02-25/L02-25_GML.zip && unzip L02-25_GML.zip
  python tools/checker_train/land_prices.py --l01 L01-25_GML/L01-25.geojson --l02 L02-25.geojson --archive All.zip --site checker-site
"""
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

import numpy as np

FEATURES = ['LandPrice', 'LandPriceMatchLevel', 'LandValue']
_NUMBER = r'[0-9一二三四五六七八九十]'


def town_key(text):
    """住所や町名から、番地・丁目などを外した町の名前（例: 「南一条西」「南１条西９丁目」→「南」）。"""
    if not isinstance(text, str):
        return None
    a = unicodedata.normalize('NFKC', text).replace(' ', '').replace('　', '')
    a = re.sub(r'^(大字|字)', '', a)
    a = re.split(_NUMBER + r'+(丁目|番|号|地割|条|-)|[0-9]', a)[0]
    a = re.sub(r'字.*$', '', a)
    return a.strip() or None


def address_town(address):
    """L01 の所在地（「北海道　札幌市中央区大通西２８丁目２０３番１０」）から町の名前を取り出す。"""
    a = unicodedata.normalize('NFKC', address).replace(' ', '').replace('　', '')
    a = re.sub(r'^.+?[都道府県]', '', a, count=1)
    m = re.match(r'^(.+?郡.+?[町村]|.+?市.+?区|.+?[市区町村])', a)
    if m:
        a = a[m.end():]
    return town_key(a)


# 項目の名前: (市区町村コード, 1㎡あたりの価格, 所在地, 利用の現況)
FIELDS = {'L01': ('L01_001', 'L01_008', 'L01_025', 'L01_028'), 'L02': ('L02_020', 'L02_006', 'L02_022', 'L02_025')}


def point_prices(*geojsons):
    """{市区町村コード: {'': 中央値, 町の名前: 中央値}}（住宅地の地点だけ。L01・L02 のどちらも、両方も可）。"""
    muni, town = {}, {}
    features = []
    for path in geojsons:
        features += json.loads(Path(path).read_text(encoding='utf-8'))['features']
    for f in features:
        p = f['properties']
        kind = 'L02' if 'L02_020' in p else 'L01'
        code_k, price_k, addr_k, use_k = FIELDS[kind]
        code, price = str(p[code_k]).zfill(5), p[price_k]
        if not price or '住宅' not in str(p.get(use_k, '')):
            continue
        muni.setdefault(code, []).append(price)
        key = address_town(p[addr_k])
        if key:
            town.setdefault(code, {}).setdefault(key, []).append(price)
    out = {}
    for code, prices in muni.items():
        out[code] = {'': int(np.median(prices))}
        out[code].update({k: int(np.median(v)) for k, v in town.get(code, {}).items()})
    return out


def site_table(points, rows):
    """サイト用の表。町の地価は、取引データの町名をそのままキーにする（サイトは引くだけでよい）。"""
    table = {code: {'': e['']} for code, e in points.items()}
    pairs = rows[['MunicipalityCode', 'DistrictName']].dropna().drop_duplicates()
    for code, district in pairs.itertuples(index=False):
        price = (points.get(code) or {}).get(town_key(district))
        if price:
            table[code][str(district)] = price
    return table


def lookup(table, code, district):
    """(地価, 一致の段階)。段階は 2=町、1=市区町村、0=分からない。サイトの app.mjs と同じ引き方。"""
    e = table.get(code) or {}
    if isinstance(district, str) and district in e:
        return e[district], 2
    if '' in e:
        return e[''], 1
    return None, 0


def add_features(rows, table):
    rows = rows.copy()
    found = [lookup(table, c, d) for c, d in zip(rows['MunicipalityCode'], rows['DistrictName'])]
    price = np.array([np.nan if p is None else p for p, _ in found], dtype=float)
    rows['LandPrice'] = np.log(price)
    rows['LandPriceMatchLevel'] = [level for _, level in found]
    rows['LandValue'] = rows['LandPrice'] + np.log(rows['Area'].astype(float))
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--l01', required=True); p.add_argument('--l02'); p.add_argument('--archive', required=True); p.add_argument('--extra')
    p.add_argument('--site', type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import train_used_house as T
    table = site_table(point_prices(*[x for x in (a.l01, a.l02) if x]), T.load(a.archive, a.extra))
    (a.site / 'land-prices.json').write_text(json.dumps(table, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')
    print(len(table), '市区町村 /', sum(len(e) - 1 for e in table.values()), '町')


if __name__ == '__main__':
    main()
