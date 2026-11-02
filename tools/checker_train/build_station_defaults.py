"""Typical station minutes per municipality and district, for houses whose station minutes were left blank.

The 中古戸建て model uses station minutes. A blank field reaches it as "unknown", which in the
transaction data mostly means rural houses far from a station, and pulled 2025 estimates about
20% low. The page fills a blank with the median for the same district (3+ transactions), else
the municipality, taken from the same MLIT archive the model is trained on.

  python tools/checker_train/build_station_defaults.py <All_*.zip> checker-site/station-defaults.json
"""
import json
import sys

import numpy as np

sys.path.insert(0, __import__('os').path.dirname(__file__))
from train_used_house import load  # noqa: E402


def build(archive):
    data = load(archive).dropna(subset=['StationMinutes', 'MunicipalityCode'])
    out = {}
    for code, g in data.groupby('MunicipalityCode'):
        entry = {'': int(round(float(np.median(g['StationMinutes']))))}
        for district, d in g.dropna(subset=['DistrictName']).groupby('DistrictName'):
            if len(d) >= 3:
                entry[str(district)] = int(round(float(np.median(d['StationMinutes']))))
        out[code] = entry
    return out


if __name__ == '__main__':
    table = build(sys.argv[1])
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        json.dump(table, f, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print('municipalities', len(table), 'districts', sum(len(v) - 1 for v in table.values()))
