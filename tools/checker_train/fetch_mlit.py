"""Fetch recent quarters of MLIT real-estate transactions (不動産情報ライブラリ API, XIT001).

Needs the free API key in MLIT_API_KEY (register at https://www.reinfolib.mlit.go.jp/).
Saves data/mlit_<pref code>_<year>_Q<quarter>.csv with the API's column names; files already
present are skipped. Quarters that are not published yet come back empty and are not saved.

  MLIT_API_KEY=... python tools/checker_train/fetch_mlit.py --out data/mlit --quarters 6
"""
import argparse
from datetime import datetime
import gzip
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

API = 'https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001'


def quarters(count, now=None):
    now = now or datetime.now()
    index = now.year * 4 + (now.month - 1) // 3
    return [((index - k) // 4, (index - k) % 4 + 1) for k in range(count, 0, -1)]


def decode(body):
    """The API answers gzip-compressed JSON (urllib does not undo Content-Encoding)."""
    if body[:2] == b'\x1f\x8b':
        body = gzip.decompress(body)
    return body.decode('utf-8')


def fetch(key, area, year, quarter):
    url = API + '?' + urllib.parse.urlencode({'area': area, 'year': year, 'quarter': quarter, 'language': 'ja'})
    request = urllib.request.Request(url, headers={'Ocp-Apim-Subscription-Key': key, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(decode(response.read()))
            rows = payload.get('data', []) if isinstance(payload, dict) else []
            return rows if isinstance(rows, list) else []
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            if exc.code in (401, 403):
                raise RuntimeError('API key was rejected') from exc
            if attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt + 1))
    return []


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=Path('data/mlit'))
    p.add_argument('--quarters', type=int, default=6)
    a = p.parse_args()
    key = os.environ.get('MLIT_API_KEY', '').strip()
    if not key:
        print('MLIT_API_KEY is not set; no new quarters fetched.')
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    saved = failed = 0
    for year, quarter in quarters(a.quarters):
        for pref in range(1, 48):
            path = a.out / f'mlit_{pref:02d}_{year}_Q{quarter}.csv'
            if path.exists():
                continue
            try:
                rows = fetch(key, f'{pref:02d}', year, quarter)
            except Exception as exc:  # reported, and the run continues with what it has
                print('failed', pref, year, quarter, type(exc).__name__)
                failed += 1
                continue
            if rows:
                if not saved:
                    print('columns', sorted(rows[0].keys()))  # to check the mapping in train_used_house.API_COLUMNS
                pd.DataFrame(rows).to_csv(path, index=False, encoding='utf-8-sig')
                saved += len(rows)
            time.sleep(0.5)
    print(json.dumps({'saved_rows': saved, 'failed_requests': failed}))
    return 1 if failed and not saved else 0


if __name__ == '__main__':
    sys.exit(main())
