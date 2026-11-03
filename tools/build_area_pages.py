"""Area price pages for search: one page per municipality with real house transactions.

For every municipality with at least 30 house (land and building, residential) sales in the last
three years of the MLIT archive, writes checker-site/area/<code>/index.html with the median price,
the middle half, typical land/floor area and age, medians by building age and by year, and the
latest sales, all computed from the public data (出典: 国土交通省 不動産情報ライブラリ). Prefecture
pages, an area index, sitemap.xml and robots.txt are written too. Pages link back to the checker.

  python tools/build_area_pages.py <All_*.zip> checker-site
"""
from datetime import date
import html
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pandas as pd

ORIGIN = 'https://okaidoku-checker.pages.dev'
MIN_SALES = 30
UNUSUAL = '調停|関係者間|隣地|瑕疵|その他事情|取壊し'
AGE_BANDS = [(0, 5, '築5年以内'), (6, 10, '築6〜10年'), (11, 20, '築11〜20年'), (21, 30, '築21〜30年'), (31, 40, '築31〜40年'), (41, 200, '築41年以上')]


def number(s):
    return pd.to_numeric(s.astype(str).str.replace('以上', '').str.replace(',', ''), errors='coerce')


def load(archive):
    cols = ['種類', '用途', '都道府県名', '市区町村コード', '市区町村名', '地区名', '取引価格（総額）', '面積（㎡）', '延床面積（㎡）', '建築年', '建物の構造', '取引時期', '取引の事情等']
    parts = []
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            parts.append(pd.read_csv(io.BytesIO(z.read(name)), encoding='cp932', usecols=cols, low_memory=False))
    df = pd.concat(parts, ignore_index=True)
    df = df[(df['種類'] == '宅地(土地と建物)') & df['用途'].astype(str).str.contains('住宅') & ~df['取引の事情等'].astype(str).str.contains(UNUSUAL)].copy()
    df['price'] = pd.to_numeric(df['取引価格（総額）'], errors='coerce')
    df['land'] = number(df['面積（㎡）'])
    df['floor'] = number(df['延床面積（㎡）'])
    df['built'] = pd.to_numeric(df['建築年'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    df['year'] = pd.to_numeric(df['取引時期'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    df['quarter'] = pd.to_numeric(df['取引時期'].astype(str).str.extract(r'第(\d)')[0], errors='coerce')
    df['age'] = df['year'] - df['built']
    df['code'] = df['市区町村コード'].map(lambda v: str(int(v)).zfill(5) if pd.notna(v) else None)
    return df.dropna(subset=['price', 'year', 'code'])[lambda d: d['price'] >= 1_000_000]


def man(yen):
    return f'{int(round(yen / 10000)):,}万円'


def page(title, description, canonical, body, crumbs):
    ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': ORIGIN + u} for i, (n, u) in enumerate(crumbs)]}
    nav = ' › '.join(f'<a href="{u}">{html.escape(n)}</a>' for n, u in crumbs[:-1]) + ' › ' + html.escape(crumbs[-1][0])
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{ORIGIN}{canonical}"><link rel="icon" href="/app-icon.png">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(description)}"><meta property="og:url" content="{ORIGIN}{canonical}"><meta property="og:image" content="{ORIGIN}/app-icon-512.png">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<link rel="stylesheet" href="/area/area.css">
</head><body><header class="bar"><a class="brand" href="/"><img src="/app-icon.png" alt="" width="36" height="36">お買い得物件チェッカー</a><a class="cta-s" href="/">物件をチェック</a></header>
<main><nav class="crumbs">{nav}</nav>{body}</main>
<footer><p>出典：国土交通省 不動産情報ライブラリ（不動産取引価格情報）をもとに、お買い得物件チェッカーが集計（土地と建物の取引のうち用途に住宅を含むもの。調停・競売等、関係者間取引などの特殊な事情がある取引は除外）。</p><p>掲載の数値は過去の取引の集計で、個別の物件の価格を示すものではありません。</p><p><a href="/">お買い得物件チェッカー</a> ・ <a href="/area/">地域の相場一覧</a></p></footer>
</body></html>
'''


def bars(rows):
    top = max(v for _, v, _ in rows)
    return '<div class="bars">' + ''.join(
        f'<div class="row"><span class="k">{html.escape(k)}</span><span class="b"><i style="width:{max(4, round(v / top * 100))}%"></i></span><span class="v">{man(v)}<small>（{n}件）</small></span></div>'
        for k, v, n in rows) + '</div>'


def city_page(code, g, recent_years):
    pref, name = g['都道府県名'].iloc[0], g['市区町村名'].iloc[0]
    q1, med, q3 = np.percentile(g['price'], [25, 50, 75])
    first, last = int(g['year'].min()), int(g['year'].max())
    age_rows = [(lab, float(np.median(s['price'])), len(s)) for lo, hi, lab in AGE_BANDS for s in [g[g['age'].between(lo, hi)]] if len(s) >= 5]
    year_rows = [(f'{y}年', float(np.median(s['price'])), len(s)) for y in recent_years for s in [g[g['year'] == y]] if len(s) >= 10]
    latest = g.sort_values(['year', 'quarter'], ascending=False).head(10)
    trs = ''.join(
        f"<tr><td>{int(r.year)}年{'第' + str(int(r.quarter)) + '四半期' if pd.notna(r.quarter) else ''}</td><td>{html.escape(str(r.地区名) if pd.notna(r.地区名) else '')}</td><td class='num'>{man(r.price)}</td>"
        f"<td class='num'>{'' if pd.isna(r.land) else f'{r.land:g}㎡'}</td><td class='num'>{'' if pd.isna(r.floor) else f'{r.floor:g}㎡'}</td><td class='num'>{'' if pd.isna(r.built) else f'{int(r.built)}年'}</td></tr>"
        for r in latest.itertuples())
    title = f'{name}（{pref}）の戸建ての相場｜実際の取引価格 {first}〜{last}年'
    desc = f'{pref}{name}で{first}〜{last}年に実際に取引された戸建て（土地と建物）{len(g)}件の価格の中央値は{man(med)}。築年数別・年別の目安と最近の取引例を、国土交通省のデータから集計。'
    land = g['land'].median(); floor = g['floor'].median(); age = g['age'].median()
    body = f'''<h1>{html.escape(name)}の戸建ての相場</h1>
<p class="lead">{html.escape(pref + name)}で{first}〜{last}年に実際に取引された戸建て（土地と建物）<b>{len(g):,}件</b>の集計です。</p>
<section class="stat"><div><span>取引価格の中央値</span><strong>{man(med)}</strong></div><div><span>真ん中の半分の取引</span><strong>{man(q1)}〜{man(q3)}</strong></div>
<div><span>土地・建物の広さ（中央値）</span><strong>{'' if pd.isna(land) else f'{land:g}㎡'}・{'' if pd.isna(floor) else f'{floor:g}㎡'}</strong></div><div><span>築年数（中央値）</span><strong>{'' if pd.isna(age) else f'{int(age)}年'}</strong></div></section>
{'<h2>築年数別の取引価格（中央値）</h2>' + bars(age_rows) if age_rows else ''}
{'<h2>年別の取引価格（中央値）</h2>' + bars(year_rows) if year_rows else ''}
<a class="cta" href="/?utm_source=area&utm_medium=internal&utm_campaign={code}">気になる{html.escape(name)}の物件の価格を、参考査定と比べる →</a>
<h2>最近の取引例</h2><div class="tablewrap"><table><thead><tr><th>時期</th><th>地区</th><th>価格</th><th>土地</th><th>建物</th><th>建築年</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="note">価格は取引総額。取引の個別の事情（建物の状態・接道・権利関係など）は反映していません。</p>'''
    crumbs = [('トップ', '/'), ('地域の相場', '/area/'), (pref, f'/area/{code[:2]}/'), (name, f'/area/{code}/')]
    return title, page(title, desc, f'/area/{code}/', body, crumbs), med


CSS = '''*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Noto Sans JP","Hiragino Sans","Yu Gothic",sans-serif;color:#14233b;background:#fff;line-height:1.75}
a{color:#1f5fd6}.bar{display:flex;justify-content:space-between;align-items:center;padding:10px 18px;border-bottom:1px solid #e3eaf6}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;text-decoration:none;color:#14233b}.brand img{border-radius:9px}
.cta-s{font-size:13px;font-weight:700;text-decoration:none;background:#1f5fd6;color:#fff;padding:7px 14px;border-radius:20px}
main{max-width:860px;margin:0 auto;padding:16px 18px 40px}.crumbs{font-size:12px;color:#6b7a90;margin-bottom:10px}
h1{font-size:28px;line-height:1.4;margin:6px 0 8px}h2{font-size:19px;margin:30px 0 10px;padding-left:10px;border-left:4px solid #1f5fd6}
.lead{color:#3d4b60}.stat{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:16px 0}.stat div{background:#eef3fd;border-radius:14px;padding:12px 14px}
.stat span{display:block;font-size:12px;color:#5f6f86}.stat strong{font-size:22px}
.bars .row{display:grid;grid-template-columns:110px 1fr 150px;gap:10px;align-items:center;font-size:14px;margin:6px 0}.bars .b{background:#eef3fd;border-radius:8px;height:16px;overflow:hidden}
.bars i{display:block;height:100%;background:#1f5fd6;border-radius:8px}.bars .v{font-weight:700}.bars small{font-weight:400;color:#6b7a90;margin-left:4px}
.cta{display:block;text-align:center;margin:28px 0 8px;background:#1f5fd6;color:#fff;text-decoration:none;font-weight:800;padding:14px;border-radius:14px}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e3eaf6;padding:7px 6px;text-align:left;white-space:nowrap}td.num{text-align:right}
.note{font-size:12px;color:#6b7a90}ul.cities{columns:3;padding-left:18px}footer{max-width:860px;margin:0 auto;padding:18px;font-size:11px;color:#6b7a90;border-top:1px solid #e3eaf6}
@media(max-width:600px){h1{font-size:23px}.stat{grid-template-columns:1fr}.bars .row{grid-template-columns:86px 1fr 118px;font-size:12px}ul.cities{columns:2}}'''


def build(archive, site):
    site = Path(site)
    df = load(archive)
    last = int(df['year'].max())
    years = [last - 2, last - 1, last]
    recent = df[df['year'].isin(years)]
    area = site / 'area'
    area.mkdir(exist_ok=True)
    (area / 'area.css').write_text(CSS, encoding='utf-8')
    built, by_pref = [], {}
    for code, g in recent.groupby('code'):
        if len(g) < MIN_SALES:
            continue
        title, text, med = city_page(code, g, years)
        (area / code).mkdir(exist_ok=True)
        (area / code / 'index.html').write_text(text, encoding='utf-8')
        # Compact sales list for the checker's "similar sales nearby": [year, quarter, district, 万円, land, floor, built]
        rows = [[int(r.year), None if pd.isna(r.quarter) else int(r.quarter), r.地区名 if isinstance(r.地区名, str) else '',
                 int(round(r.price / 10000)), None if pd.isna(r.land) else float(r.land), None if pd.isna(r.floor) else float(r.floor),
                 None if pd.isna(r.built) else int(r.built)] for r in g.sort_values(['year', 'quarter'], ascending=False).itertuples()]
        (area / code / 'sales.json').write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        built.append(f'/area/{code}/')
        by_pref.setdefault(code[:2], (g['都道府県名'].iloc[0], []))[1].append((code, g['市区町村名'].iloc[0], len(g), med))
    for pc, (pref, cities) in sorted(by_pref.items()):
        items = ''.join(f'<li><a href="/area/{c}/">{html.escape(n)}</a> <small>{man(m)}（{k}件）</small></li>' for c, n, k, m in sorted(cities))
        body = f'<h1>{html.escape(pref)}の戸建ての相場（市区町村別）</h1><p class="lead">{years[0]}〜{last}年に実際に取引された戸建て（土地と建物）の価格の中央値と件数です。</p><ul class="cities">{items}</ul><a class="cta" href="/?utm_source=area&utm_medium=internal&utm_campaign=pref{pc}">物件の価格を、参考査定と比べる →</a>'
        (area / pc).mkdir(exist_ok=True)
        (area / pc / 'index.html').write_text(page(f'{pref}の戸建ての相場（市区町村別）｜実際の取引価格', f'{pref}の市区町村ごとの戸建ての取引価格の中央値（{years[0]}〜{last}年、国土交通省のデータを集計）。', f'/area/{pc}/', body, [('トップ', '/'), ('地域の相場', '/area/'), (pref, f'/area/{pc}/')]), encoding='utf-8')
        built.append(f'/area/{pc}/')
    items = ''.join(f'<li><a href="/area/{pc}/">{html.escape(p)}</a> <small>{len(c)}市区町村</small></li>' for pc, (p, c) in sorted(by_pref.items()))
    body = f'<h1>地域の戸建ての相場</h1><p class="lead">都道府県を選ぶと、市区町村ごとの実際の取引価格（{years[0]}〜{last}年）を見られます。</p><ul class="cities">{items}</ul>'
    (area / 'index.html').write_text(page('地域の戸建ての相場｜実際の取引価格（都道府県・市区町村別）', '全国の市区町村ごとの戸建ての取引価格の中央値を、国土交通省のデータから集計。', '/area/', body, [('トップ', '/'), ('地域の相場', '/area/')]), encoding='utf-8')
    (area / 'codes.json').write_text(json.dumps(sorted(u.strip('/').split('/')[-1] for u in built if len(u.strip('/').split('/')[-1]) == 5)), encoding='utf-8')
    urls = ['/', '/sell/', '/area/'] + sorted(built)
    today = date.today().isoformat()
    (site / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(
        f'<url><loc>{ORIGIN}{u}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n', encoding='utf-8')
    (site / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n', encoding='utf-8')
    return len([u for u in built if len(u.strip('/').split('/')[-1]) == 5]), len(by_pref)


if __name__ == '__main__':
    cities, prefs = build(sys.argv[1], sys.argv[2])
    print('city pages', cities, 'prefecture pages', prefs)
