"""結果画面の「価格の幅」を、場所（都会・中堅都市・田舎）と築年数・査定額ごとに測り直す。

直近2四半期より前の取引で学習した、公開中と同じ作り方のモデルで、直近2四半期の実際の取引を査定し、
「実際の価格 ÷ 査定額」の真ん中の半分（25〜75%）を区分ごとに求める。件数が少ない区分は、上の区分の値を使う。
場所の区分は、国勢調査（2020年）の市区町村の人口と人口密度（muni-stats.json）から決める。

  python tools/checker_train/build_bands.py --archive All.zip --site checker-site
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import auto_retrain as A  # noqa: E402
import train_used_house as T  # noqa: E402

PRICE_EDGES = [800, 1500, 2500, 4000]  # 査定額（万円）の区切り。extras.mjs と同じ
OLD_AGE = 30
MIN_N = 300


def area_class(stats, code):
    s = stats.get(code)
    if not s:
        return '中堅都市'
    if s['pop'] >= 500000 or (s.get('density') or 0) >= 4000:
        return '都会'
    return '中堅都市' if s['pop'] >= 100000 else '田舎'


def bucket(estimate_man):
    return int(np.searchsorted(PRICE_EDGES, estimate_man, side='right'))


def quartiles(ratio):
    lo, hi = np.quantile(ratio, [.25, .75])
    return [round(float(lo), 2), round(float(hi), 2), int(len(ratio))]


def build(rows, stats, pred_yen):
    est = pred_yen / 10000
    ratio = rows['price_yen'].to_numpy(float) / pred_yen
    cls = np.array([area_class(stats, c) for c in rows['MunicipalityCode']])
    old = (rows['BuildingAge'].to_numpy(float) >= OLD_AGE)
    b = np.array([bucket(e) for e in est])
    bands = {'all': {str(k): quartiles(ratio[b == k]) for k in range(len(PRICE_EDGES) + 1) if (b == k).sum() >= MIN_N}}
    for c in ('都会', '中堅都市', '田舎'):
        for o in (False, True):
            key = c + ('・築30年以上' if o else '・築30年未満')
            sel = (cls == c) & (old == o)
            cell = {}
            for k in range(len(PRICE_EDGES) + 1):
                m = sel & (b == k)
                if m.sum() >= MIN_N:
                    cell[str(k)] = quartiles(ratio[m])
            if sel.sum() >= MIN_N:
                cell['*'] = quartiles(ratio[sel])
            bands[key] = cell
    return {'edges': PRICE_EDGES, 'oldAge': OLD_AGE, 'bands': bands,
            'classes': {code: area_class(stats, code) for code in sorted(set(rows['MunicipalityCode'].dropna()) | set(stats))
                        if len(code) == 5 and not code.endswith('000')}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', required=True); p.add_argument('--extra'); p.add_argument('--site', type=Path, required=True)
    a = p.parse_args()
    stats = json.loads((HERE / 'muni-stats.json').read_text(encoding='utf-8'))
    data = T.load(a.archive, a.extra)
    per = A.period(data); last = int(per.max())
    before, hold = data[per <= last - 2], data[per > last - 2]
    table = A.station_table(before)
    pipe = A.train(before, A.RECIPES['filled'], table)
    hold = A.fill_station(hold, table)
    out = build(hold, stats, T.predict_yen(pipe, hold))
    out['measured'] = {'trainedThrough': A.month_end(last - 2), 'holdout': A.period_label(last - 1, last), 'n': int(len(hold))}
    (a.site / 'price-bands.json').write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for k, v in out['bands'].items():
        print(k, v)


if __name__ == '__main__':
    main()
