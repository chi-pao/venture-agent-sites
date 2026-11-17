"""町ごとの「土地1㎡あたりの売れた値段」の目安を、中古戸建ての査定の手がかりにする。

取引データから、町（なければ市区町村、なければ全国）の log(価格 ÷ 土地の広さ) の平均を、件数が少ないほど
上の段階の値に寄せて求める（件数 K 件分の重み）。サイトが読む表は checker-site/town-prices.json:
  {"市区町村コード": {"": 市区町村の値, "町名": 町の値, ...}}
学習では、その取引自身を含まない値を使う（5つに分け、他の4つから求める）。含めると答えを見たことになるため。
"""
import numpy as np
import pandas as pd

FEATURE = 'TownLogPpm'
K = 10


def build(rows):
    v = np.log(rows['price_yen'].to_numpy(float) / rows['Area'].to_numpy(float))
    g = pd.DataFrame({'c': rows['MunicipalityCode'].to_numpy(), 'd': rows['DistrictName'].to_numpy(), 'v': v})
    glob = float(v.mean())
    table = {}
    for code, c in g.dropna(subset=['c']).groupby('c'):
        base = (c['v'].sum() + glob * K) / (len(c) + K)
        e = {'': round(base, 4)}
        for d, x in c.dropna(subset=['d']).groupby('d'):
            e[str(d)] = round((x['v'].sum() + base * K) / (len(x) + K), 4)
        table[code] = e
    table['*'] = {'': round(glob, 4)}
    return table


def lookup(table, code, district):
    e = table.get(code)
    if e is None:
        return table.get('*', {}).get('')
    if isinstance(district, str) and district in e:
        return e[district]
    return e['']


def add_feature(rows, table):
    rows = rows.copy()
    rows[FEATURE] = [lookup(table, c, d) for c, d in zip(rows['MunicipalityCode'], rows['DistrictName'])]
    return rows


def add_out_of_fold(rows, folds=5, seed=0):
    """学習用: 各取引に、その取引を含まない残りの取引から作った値を付ける。"""
    rows = rows.copy()
    fold = np.random.default_rng(seed).integers(0, folds, len(rows))
    values = np.empty(len(rows))
    for k in range(folds):
        table = build(rows[fold != k])
        part = rows[fold == k]
        values[fold == k] = [lookup(table, c, d) for c, d in zip(part['MunicipalityCode'], part['DistrictName'])]
    rows[FEATURE] = values
    return rows
