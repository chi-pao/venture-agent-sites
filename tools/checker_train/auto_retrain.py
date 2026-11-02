"""Monthly self-improvement for the 中古戸建て model: try candidates, keep only a clear win.

1. Load the MLIT archive plus any newer quarters fetched by fetch_mlit.py.
2. Hold out the latest two quarters; train each candidate recipe on everything before them.
3. Score every candidate and the model the site serves now on the same held-out sales, all through
   the site's own JavaScript runtime (tools/checker_eval/predict.mjs), with blank station minutes
   filled the way the page fills them.
4. If the best candidate beats the live model clearly (median error at least 0.3 points lower and
   no more than 1 point fewer sales within ±20%), retrain that recipe on all data, check that
   Python and JavaScript agree, and write it into checker-site/ with a fresh station table and a
   comparison report. Otherwise change nothing.

  python tools/checker_train/auto_retrain.py --archive All.zip --extra data/mlit --site checker-site --work /tmp/retrain
Writes <work>/summary.md and, under GitHub Actions, changed=true|false to $GITHUB_OUTPUT.
"""
import argparse
from datetime import date
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train_used_house as T  # noqa: E402

ROOT = HERE.parent.parent
PREDICT = ROOT / 'tools' / 'checker_eval' / 'predict.mjs'
# Candidate recipes. 'decay' weights a sale by decay**(years before the newest training quarter);
# 'fill' gives blank station minutes in training the area's typical value, as the page does.
RECIPES = {
    'base': {'decay': None, 'fill': False},
    'recent': {'decay': 0.8, 'fill': False},
    'filled': {'decay': None, 'fill': True},
    'recent+filled': {'decay': 0.8, 'fill': True},
}
MIN_GAIN, MAX_WITHIN_LOSS = 0.3, 1.0


def period(frame):
    return frame['TransactionYear'] * 4 + frame['Quarter'] - 1


def months(index):
    """'2026年1〜6月' style label for a period index (year*4+quarter-1) range."""
    return index // 4, index % 4 * 3


def period_label(first, last):
    (y1, m1), (y2, m2) = months(first), months(last)
    return f'{y1}年{m1 + 1}〜{m2 + 3}月' if y1 == y2 else f'{y1}年{m1 + 1}月〜{y2}年{m2 + 3}月'


def month_end(index):
    year, month = months(index)
    return f'{year}年{month + 3}月'


def station_table(rows):
    g = rows.dropna(subset=['StationMinutes', 'MunicipalityCode'])
    table = {}
    for code, c in g.groupby('MunicipalityCode'):
        entry = {'': int(round(float(np.median(c['StationMinutes']))))}
        for district, d in c.dropna(subset=['DistrictName']).groupby('DistrictName'):
            if len(d) >= 3:
                entry[str(district)] = int(round(float(np.median(d['StationMinutes']))))
        table[code] = entry
    return table


def fill_station(rows, table):
    rows = rows.copy()
    blank = rows['StationMinutes'].isna()
    rows.loc[blank, 'StationMinutes'] = [
        (table.get(c) or {}).get(str(d), (table.get(c) or {}).get('', np.nan))
        for c, d in zip(rows.loc[blank, 'MunicipalityCode'], rows.loc[blank, 'DistrictName'])]
    return rows


def site_inputs(rows):
    """The page's input objects for these sales (station minutes already filled where possible)."""
    out = []
    for r in rows.itertuples(index=False):
        d = {'type': 'used_house', 'prefecture': r.Prefecture, 'city': r.MunicipalityCode, 'price': 1,
             'district': r.DistrictName if isinstance(r.DistrictName, str) else '',
             'year': int(r.TransactionYear - r.BuildingAge), 'landArea': float(r.Area), 'buildingArea': float(r.TotalFloorArea)}
        if isinstance(r.Structure, str):
            d['structure'] = r.Structure
        if isinstance(r.CityPlanning, str):
            d['planning'] = r.CityPlanning
        if pd.notna(r.StationMinutes):
            d['stationMinutes'] = int(r.StationMinutes)
        out.append(d)
    return out


def predict_site(site, inputs, work):
    path = work / 'inputs.json'
    path.write_text(json.dumps(inputs, ensure_ascii=False), encoding='utf-8')
    result = subprocess.run(['node', str(PREDICT), str(site), str(path)], check=True, capture_output=True, text=True)
    return np.array(json.loads(result.stdout), dtype=float) * 10000


def score(pred, actual):
    e = np.abs(pred - actual) / actual
    return {'n': int(len(actual)), 'median_ape_pct': round(float(np.median(e) * 100), 2),
            'within20_pct': round(float((e <= .2).mean() * 100), 2), 'mae_yen': round(float(np.abs(pred - actual).mean())),
            'median_actual_over_estimate': round(float(np.median(actual / pred)), 3)}


def site_with(site, component, dat, work):
    """A copy of the site whose used_house model is the given component (categorical splits inline)."""
    copy = work / 'site'
    if copy.exists():
        shutil.rmtree(copy)
    copy.mkdir()
    for p in site.iterdir():
        if p.name != 'models':
            os.symlink(p.resolve(), copy / p.name)
    (copy / 'models').mkdir()
    for p in (site / 'models').iterdir():
        if p.name != 'catalog.json':
            os.symlink(p.resolve(), copy / 'models' / p.name)
    shutil.copy(dat, copy / component['path'])
    catalog = json.loads((site / 'models' / 'catalog.json').read_text(encoding='utf-8'))
    catalog['models']['used_house'] = dict(catalog['models']['used_house'], components=[component])
    (copy / 'models' / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
    return copy


def train(rows, recipe, table):
    if recipe['fill']:
        rows = fill_station(rows, table)
    weight = None
    if recipe['decay']:
        weight = recipe['decay'] ** ((period(rows).max() - period(rows)) / 4)
    return T.fit(rows, weight)


def install(pipe, rows, site, table, report, work):
    """Write the winning model into the site: binary, split table, catalog entry, station table."""
    stamp = date.today().strftime('%Y%m%d')
    models = site / 'models'
    # Name the files after their content so a browser can never pair a cached old file with a new hash.
    staging = models / 'used_house-staging.dat'
    component = T.export(pipe, staging, 'models/used_house-staging.dat')
    name = f"used_house-{stamp}-{component['sha256'][:8]}"
    dat = models / f'{name}.dat'
    staging.replace(dat)
    component['path'] = f'models/{name}.dat'
    # Python vs the site's JavaScript runtime on fixed rows, before anything is published.
    sample = rows.sample(64, random_state=3)
    (work / 'component.json').write_text(json.dumps(component, ensure_ascii=False), encoding='utf-8')
    shutil.copy(dat, work / 'used_house.dat')
    feature_rows = sample[T.NUMS + T.CATS].astype(object).where(sample[T.NUMS + T.CATS].notna(), None).to_dict('records')
    (work / 'parity.json').write_text(json.dumps({'rows': feature_rows, 'expected': T.predict_yen(pipe, sample).tolist()}, ensure_ascii=False), encoding='utf-8')
    subprocess.run(['node', str(ROOT / 'tools' / 'checker_eval' / 'parity.mjs'), str(site), str(work)], check=True)
    splits = gzip.compress(json.dumps(component.pop('categoricalSplits'), separators=(',', ':')).encode(), compresslevel=9, mtime=0)
    split_path = f'models/{name}-{hashlib.sha256(splits).hexdigest()[:8]}.splits.json.gz'
    (site / split_path).write_bytes(splits)
    component.update(splitsPath=split_path, splitsSha256=hashlib.sha256(splits).hexdigest(), splitsBytes=len(splits))
    catalog_path = models / 'catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    old = catalog['models']['used_house']
    report_path = f'models/used-house-comparison-{stamp}.json'
    (site / report_path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    best = report['candidates'][report['winner']]
    catalog['models']['used_house'] = {
        'name': f'中古戸建て・取引価格モデル（{date.today().year}年{date.today().month}月更新）', 'trainedAt': date.today().isoformat(),
        'sourceSha256': component['sha256'], 'releaseKind': 'time_holdout',
        'metrics': {k: best[k] for k in ('n', 'median_ape_pct', 'mae_yen', 'within20_pct')},
        'comparisonReport': report_path, 'validation': report['validation'], 'components': [component]}
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (site / 'station-defaults.json').write_text(json.dumps(table, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')
    # The replaced model's files are no longer referenced (the fallback is the small baseline).
    for c in old['components']:
        for key in ('path', 'splitsPath'):
            if c.get(key) and c[key] not in (component['path'], split_path) and (site / c[key]).exists():
                (site / c[key]).unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', required=True); p.add_argument('--extra'); p.add_argument('--site', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True); p.add_argument('--holdout-quarters', type=int, default=2)
    p.add_argument('--holdout-sample', type=int, default=20000)
    a = p.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    data = T.load(a.archive, a.extra)
    last = int(period(data).max())
    hold = data[period(data) > last - a.holdout_quarters]
    before = data[period(data) <= last - a.holdout_quarters]
    hold = hold.sample(min(a.holdout_sample, len(hold)), random_state=11)
    train_table = station_table(before)
    hold_inputs = site_inputs(fill_station(hold, train_table))
    actual = hold['price_yen'].to_numpy(float)
    report = {'holdout': f'{len(hold)} sales from the latest {a.holdout_quarters} quarters (period index > {last - a.holdout_quarters})',
              'validation': {'trainedThrough': month_end(last - a.holdout_quarters),
                             'holdout': period_label(last - a.holdout_quarters + 1, last)},
              'live': score(predict_site(a.site, hold_inputs, a.work), actual), 'candidates': {}}
    print('live', report['live'], flush=True)
    for name, recipe in RECIPES.items():
        pipe = train(before, recipe, train_table)
        cand = a.work / name
        cand.mkdir(exist_ok=True)
        component = T.export(pipe, cand / 'used_house.dat', 'models/used_house-candidate.dat')
        site = site_with(a.site, component, cand / 'used_house.dat', a.work)
        report['candidates'][name] = score(predict_site(site, hold_inputs, a.work), actual)
        print(name, report['candidates'][name], flush=True)
    winner = min(report['candidates'], key=lambda n: report['candidates'][n]['median_ape_pct'])
    report['winner'] = winner
    live, best = report['live'], report['candidates'][winner]
    changed = best['median_ape_pct'] <= live['median_ape_pct'] - MIN_GAIN and best['within20_pct'] >= live['within20_pct'] - MAX_WITHIN_LOSS
    report['adopted'] = changed
    if changed:
        full_table = station_table(data)
        install(train(data, RECIPES[winner], full_table), data, a.site, full_table, report, a.work)
    lines = ['# 中古戸建てモデルの自動学習', '', f"- 検証: {report['holdout']}",
             f"- 公開中のモデル: 誤差中央値 {live['median_ape_pct']}% / ±20%以内 {live['within20_pct']}%", '']
    lines += [f"- 候補 {n}: 誤差中央値 {s['median_ape_pct']}% / ±20%以内 {s['within20_pct']}%" for n, s in report['candidates'].items()]
    lines += ['', f"- 結論: {'候補 ' + winner + ' を採用（全データで学習し直してサイトに書き込み済み）' if changed else '入れ替えなし（はっきりした改善がない）'}"]
    (a.work / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (a.work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n'.join(lines))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == '__main__':
    main()
