"""Map the town names a person can pick on the checker to the district names the models learned.

The town list (checker-site/towns.json) and the MLIT transaction data that trained the models
name the same places differently: 「際波」 vs 「大字際波」, 「月寒東二条」 vs 「月寒東２条」,
「弥富通」 vs 「彌富通」, and the data often records only the coarser area (「大久保町」 for the
picked 「大久保町茜」). An unmatched name reaches the model as an unknown district and the page
says 「学習時にない町名」.

For every municipality, each listed town is matched against the districts that occur in that
same municipality's transactions: first by a normalised name, then by the longest district whose
normalised name the town's starts with. Only names a model actually learned are kept, and only
entries that differ from the town name are written (checker-site/town-aliases.json).

  python tools/build_town_aliases.py <MLIT All_*.zip> checker-site
"""
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
import zipfile

import pandas as pd

KANJI_DIGITS = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
OLD_FORMS = str.maketrans({'彌': '弥', '澤': '沢', '濱': '浜', '邊': '辺', '邉': '辺', '嶋': '島', '齋': '斎', '齊': '斉',
                           '廣': '広', '國': '国', '藏': '蔵', '櫻': '桜', '瀨': '瀬', '龍': '竜', '舊': '旧', '圓': '円',
                           '縣': '県', '萬': '万', '與': '与', '壽': '寿', '眞': '真', '冨': '富', '﨑': '崎', '嵜': '崎',
                           'ヶ': 'ケ', 'ヵ': 'カ', 'が': 'ケ', 'ガ': 'ケ', 'の': 'ノ', '之': 'ノ'})
NUMBER = re.compile(r'[〇一二三四五六七八九十百]+(?=[条丁線号区番地])')
UNPLACED = {'（大字なし）', '(大字なし)', ''}


def kanji_number(text):
    total, current = 0, 0
    for ch in text:
        if ch == '百':
            total += (current or 1) * 100; current = 0
        elif ch == '十':
            total += (current or 1) * 10; current = 0
        else:
            current = current * 10 + KANJI_DIGITS[ch]
    return str(total + current)


def key(name):
    s = unicodedata.normalize('NFKC', str(name)).translate(OLD_FORMS)
    s = re.sub(r'\s', '', s)
    s = NUMBER.sub(lambda m: kanji_number(m.group()), s)
    s = s.replace('大字', '')
    s = re.sub(r'(^|[町村])字', r'\1', s)
    return s


def match(town, districts):
    """districts: {normalised key: district name} for one municipality."""
    k = key(town)
    if k in districts:
        return districts[k]
    best = max((d for d in districts if len(d) >= 2 and k.startswith(d)), key=len, default=None)
    return districts[best] if best else None


def learned_names(site):
    catalog = json.loads((site / 'models' / 'catalog.json').read_text(encoding='utf-8'))
    names = set()
    for group in ('models', 'previousModels'):
        for model in catalog.get(group, {}).values():
            for c in model['components']:
                if 'DistrictName' in c['categorical']:
                    names.update(c['categories'][c['categorical'].index('DistrictName')])
    return names


def districts_by_city(archive):
    out = {}
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            df = pd.read_csv(io.BytesIO(z.read(name)), encoding='cp932', usecols=['市区町村コード', '地区名'], low_memory=False)
            df = df.dropna()
            for code, district in zip(df['市区町村コード'], df['地区名'].astype(str)):
                out.setdefault(str(int(code)).zfill(5), set()).add(district)
    return out


def build(archive, site):
    site = Path(site)
    towns = json.loads((site / 'towns.json').read_text(encoding='utf-8'))
    learned = learned_names(site)
    by_city = districts_by_city(archive)
    aliases = {}
    for code, rows in towns.items():
        districts = {}
        for d in sorted(by_city.get(code, ()), key=len):
            if d in learned and d not in UNPLACED:
                districts.setdefault(key(d), d)
        for town, _reading in rows:
            if town in learned and key(town) in districts and districts[key(town)] == town:
                continue
            target = match(town, districts)
            if target and target != town:
                aliases.setdefault(code, {})[town] = target
    (site / 'town-aliases.json').write_text(json.dumps(aliases, ensure_ascii=False, separators=(',', ':'), sort_keys=True), encoding='utf-8')
    return aliases


if __name__ == '__main__':
    result = build(sys.argv[1], sys.argv[2])
    print('municipalities', len(result), 'aliases', sum(len(v) for v in result.values()))
