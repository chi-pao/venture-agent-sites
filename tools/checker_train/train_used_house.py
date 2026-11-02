"""Train the 中古戸建て model for checker-site from the MLIT transaction archive and export it.

The model uses only what the page can supply: land and floor area, building age, transaction
period, station minutes, prefecture, municipality, district, structure and city planning.
The target is log(price in 万円) so the existing runtime ('v8_log_man' postprocess) reads it.

  # holdout check: train on transactions up to 2024, score on 2025 against the live model
  python tools/checker_train/train_used_house.py --archive All.zip --until 2024 --out /tmp/cand
  # release: train on everything
  python tools/checker_train/train_used_house.py --archive All.zip --until 2025 --out /tmp/release

Writes <out>/used_house.dat, <out>/component.json (the catalog component) and
<out>/parity.json (Python predictions for fixed rows, to compare with the JavaScript runtime).
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from lightgbm import LGBMRegressor
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

NUMS = ['Area', 'TotalFloorArea', 'BuildingAge', 'TransactionYear', 'Quarter', 'StationMinutes',
        'LogArea', 'LogTotalFloorArea', 'LandBuildingRatio']
CATS = ['Prefecture', 'MunicipalityCode', 'DistrictName', 'Structure', 'CityPlanning']
UNUSUAL = '調停|関係者間|隣地|瑕疵|その他事情|取壊し'
PARAMS = dict(n_estimators=1500, learning_rate=0.05, num_leaves=127, min_child_samples=20, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, objective='l1', random_state=42, verbose=-1, n_jobs=4)


def number(series):
    return pd.to_numeric(series.astype(str).str.replace('以上', '').str.replace(',', ''), errors='coerce')


# Column names of the 不動産情報ライブラリ API (data/mlit_*.csv from fetch_mlit.py) -> the archive's names.
API_COLUMNS = {'Type': '種類', 'PriceCategory': '価格情報区分', 'Prefecture': '都道府県名', 'Municipality': '市区町村名',
               'MunicipalityCode': '市区町村コード', 'DistrictName': '地区名', 'TimeToNearestStation': '最寄駅：距離（分）',
               'TradePrice': '取引価格（総額）', 'Area': '面積（㎡）', 'TotalFloorArea': '延床面積（㎡）', 'BuildingYear': '建築年',
               'Structure': '建物の構造', 'CityPlanning': '都市計画', 'Period': '取引時期', 'Use': '用途', 'Remarks': '取引の事情等'}


def load(archive, extra_dir=None):
    parts = []
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            parts.append(pd.read_csv(io.BytesIO(z.read(name)), encoding='cp932', low_memory=False))
    extra = sorted(Path(extra_dir).glob('mlit_*.csv')) if extra_dir else []
    for path in extra:
        parts.append(pd.read_csv(path, encoding='utf-8-sig', low_memory=False).rename(columns=API_COLUMNS))
    df = pd.concat(parts, ignore_index=True)
    for column in API_COLUMNS.values():
        if column not in df:
            df[column] = np.nan
    # The archive and the API can both carry the same quarter; keep one copy of each transaction.
    if extra:
        df = df.drop_duplicates(subset=['市区町村コード', '地区名', '取引価格（総額）', '面積（㎡）', '延床面積（㎡）', '建築年', '取引時期', '種類'])
    df = df[(df['種類'] == '宅地(土地と建物)') & df['用途'].astype(str).str.contains('住宅')]
    df = df[~df['取引の事情等'].astype(str).str.contains(UNUSUAL)]
    land, floor = number(df['面積（㎡）']), number(df['延床面積（㎡）'])
    built = pd.to_numeric(df['建築年'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    year = pd.to_numeric(df['取引時期'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    quarter = pd.to_numeric(df['取引時期'].astype(str).str.extract(r'第(\d)')[0], errors='coerce')
    out = pd.DataFrame({
        'Area': land, 'TotalFloorArea': floor, 'BuildingAge': (year - built).clip(lower=0),
        'TransactionYear': year, 'Quarter': quarter, 'StationMinutes': pd.to_numeric(df['最寄駅：距離（分）'], errors='coerce'),
        'Prefecture': df['都道府県名'].astype(str),
        'MunicipalityCode': df['市区町村コード'].map(lambda v: str(int(v)).zfill(5) if pd.notna(v) else np.nan),
        'DistrictName': df['地区名'], 'Structure': df['建物の構造'], 'CityPlanning': df['都市計画'],
        'price_yen': pd.to_numeric(df['取引価格（総額）'], errors='coerce')})
    out = out.dropna(subset=['Area', 'TotalFloorArea', 'BuildingAge', 'TransactionYear', 'Quarter', 'price_yen'])
    out = out[(out['Area'] > 0) & (out['TotalFloorArea'] > 0) & (out['price_yen'] >= 1_000_000)].copy()
    out['LogArea'] = np.log1p(out['Area'])
    out['LogTotalFloorArea'] = np.log1p(out['TotalFloorArea'])
    out['LandBuildingRatio'] = out['Area'] / out['TotalFloorArea']
    for c in CATS:
        out[c] = out[c].where(out[c].notna(), np.nan).astype(object)
    return out.reset_index(drop=True)


def pipeline():
    pre = ColumnTransformer([
        ('num', Pipeline([('fill', SimpleImputer(strategy='constant', fill_value=-1))]), NUMS),
        ('cat', Pipeline([('fill', SimpleImputer(strategy='constant', fill_value='不明')),
                          ('encode', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1))]), CATS)])
    return Pipeline([('pre', pre), ('lgb', LGBMRegressor(**PARAMS))])


def fit(train, weight=None):
    pipe = pipeline()
    extra = {} if weight is None else {'lgb__sample_weight': np.asarray(weight)}
    pipe.fit(train[NUMS + CATS], np.log(train['price_yen'] / 10000),
             lgb__categorical_feature=list(range(len(NUMS), len(NUMS) + len(CATS))), **extra)
    return pipe


def predict_yen(pipe, frame):
    return np.exp(pipe.predict(frame[NUMS + CATS])) * 10000


def export(pipe, path, public_path):
    """Same binary layout as chi-pao/- export_sites_model.py and checker-site/model-runtime.mjs."""
    pre = pipe.named_steps['pre']; model = pipe.named_steps['lgb']
    num = pre.named_transformers_['num']; cat = pre.named_transformers_['cat']
    dump = model.booster_.dump_model()
    data = bytearray(); roots = []; category_sets = []; lookup = {}

    def emit(n):
        index = len(data) // 16
        if 'leaf_value' in n:
            data.extend(struct.pack('<dihh', float(n['leaf_value']), -1, -1, 0)); return index
        if n.get('missing_type') == 'Zero':
            raise ValueError('Unsupported zero-missing split')
        flags = 0
        if n['decision_type'] == '==':
            members = tuple(int(v) for v in str(n['threshold']).split('||'))
            if members not in lookup:
                lookup[members] = len(category_sets); category_sets.append(list(members))
            threshold = lookup[members]; flags = 1 | (2 if n.get('default_left') else 0)
        elif n['decision_type'] == '<=':
            threshold = float(n['threshold'])
        else:
            raise ValueError('Unsupported split')
        data.extend(struct.pack('<dihh', threshold, -1, int(n['split_feature']), flags))
        assert emit(n['left_child']) == index + 1
        right = emit(n['right_child']); struct.pack_into('<i', data, index * 16 + 8, right); return index

    for tree in dump['tree_info']:
        roots.append(emit(tree['tree_structure']))
    packed = gzip.compress(bytes(data), compresslevel=9, mtime=0)
    if len(packed) >= 25_000_000:
        raise ValueError('Export exceeds the browser model limit')
    path.write_bytes(packed)
    return {'path': public_path, 'sha256': hashlib.sha256(packed).hexdigest(), 'bytes': len(packed), 'nodes': len(data) // 16,
            'algorithm': 'lightgbm', 'postprocess': 'v8_log_man', 'baseline': 0, 'log': False, 'roots': roots, 'weight': 1,
            'numeric': NUMS, 'numericDefaults': [float(v) for v in num.steps[0][1].statistics_],
            'categorical': CATS, 'categoricalDefaults': [str(v) for v in cat.steps[0][1].statistics_],
            'categories': [[str(v) for v in c] for c in cat.steps[-1][1].categories_], 'categoricalSplits': category_sets}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', required=True); p.add_argument('--until', type=int, required=True)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--public-path', default='models/used_house.dat')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    data = load(a.archive)
    train = data[data['TransactionYear'] <= a.until]
    pipe = fit(train)
    component = export(pipe, a.out / 'used_house.dat', a.public_path)
    (a.out / 'component.json').write_text(json.dumps(component, ensure_ascii=False), encoding='utf-8')
    sample = data.sample(64, random_state=3)
    rows = [{k: (None if (isinstance(v, float) and not np.isfinite(v)) else v) for k, v in r.items()}
            for r in sample[NUMS + CATS].astype(object).where(sample[NUMS + CATS].notna(), None).to_dict('records')]
    (a.out / 'parity.json').write_text(json.dumps({'rows': rows, 'expected': predict_yen(pipe, sample).tolist()}, ensure_ascii=False), encoding='utf-8')
    data.to_pickle(a.out / 'rows.pkl')
    print(json.dumps({'train_rows': len(train), 'until': a.until, 'bytes': component['bytes'], 'nodes': component['nodes']}))


if __name__ == '__main__':
    main()
