# -*- coding: utf-8 -*-
"""⑩物販・アフィリエイト部の道具：楽天の商品検索・ランキングと、商品まとめページづくり。

- 楽天ウェブサービス（Rakuten Developers）の API を、設定があるときだけ使う。
  2026年2月の仕様変更後の形：窓口は openapi.rakuten.co.jp、applicationId と accessKey の両方が必要、
  登録した Web サイトの URL を Referer として送る（2026-11-13 に窓口の返事で確認）。
- config.json に rakuten_app_id / rakuten_access_key / rakuten_affiliate_id / rakuten_site_url を書く。
  アフィリエイトIDを渡すと、紹介リンク（affiliateUrl）付きで返る。
- まとめページは PR 表記を一番上に出し、リンクには rel="sponsored nofollow" を付ける。価格は取得日時点と書く。
"""
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

SEARCH_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
RANKING_ENDPOINT = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
DEFAULT_ENDPOINT = SEARCH_ENDPOINT


class RakutenError(RuntimeError):
    pass


def ready(cfg):
    return bool(cfg.get("rakuten_app_id") and cfg.get("rakuten_access_key"))


def _get(cfg, endpoint, params):
    if not ready(cfg):
        raise RakutenError("楽天のアプリIDとアクセスキーがありません（secrets/rakuten.json か config.json に書く）")
    params = dict(params, applicationId=cfg["rakuten_app_id"], accessKey=cfg["rakuten_access_key"],
                  format="json", formatVersion=2)
    if cfg.get("rakuten_affiliate_id"):
        params["affiliateId"] = cfg["rakuten_affiliate_id"]
    headers = {"User-Agent": "venture-studio"}
    site = cfg.get("rakuten_site_url")
    if site:
        headers["Referer"] = site.rstrip("/") + "/"
        headers["Origin"] = site.rstrip("/")
    url = endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        for secret in (cfg.get("rakuten_app_id"), cfg.get("rakuten_access_key")):
            if secret:
                body = body.replace(secret, "***")
        raise RakutenError(f"楽天が {e.code} を返しました: {body}") from None
    except Exception as e:
        raise RakutenError(f"楽天につながりませんでした: {e}") from None


def _items(data):
    items = []
    for it in data.get("Items", []):
        it = it.get("Item", it)  # formatVersion=1 の形にも対応
        link = it.get("affiliateUrl") or it.get("itemUrl")
        if not link:
            continue
        images = it.get("mediumImageUrls") or []
        img = images[0] if images else ""
        img = img.get("imageUrl", "") if isinstance(img, dict) else img
        items.append({"name": it.get("itemName", ""), "price": it.get("itemPrice"), "shop": it.get("shopName", ""),
                      "url": link, "item_url": it.get("itemUrl", ""), "is_affiliate": bool(it.get("affiliateUrl")),
                      "code": it.get("itemCode", ""), "rank": it.get("rank"),
                      "caption": (it.get("itemCaption") or "")[:400], "catch": it.get("catchcopy", ""),
                      "postage": it.get("postageFlag"), "point_rate": it.get("pointRate"),
                      "reviews": it.get("reviewCount", 0) or 0, "rating": it.get("reviewAverage", 0) or 0,
                      "image": img})
    return items


def search(cfg, keyword, hits=10):
    """楽天市場で探す。レビューの多い順。戻り値は扱いやすい形の商品リスト。"""
    return _items(_get(cfg, cfg.get("rakuten_endpoint") or SEARCH_ENDPOINT,
                       {"keyword": keyword, "hits": hits, "sort": "-reviewCount", "availability": 1}))


def ranking(cfg, genre_id=None, page=1):
    """楽天市場ランキング（デイリー）。genre_id なしは総合。"""
    params = {"page": page}
    if genre_id:
        params["genreId"] = genre_id
    return _items(_get(cfg, RANKING_ENDPOINT, params))


def pick(items, min_reviews=30, limit=5):
    good = [i for i in items if (i["reviews"] or 0) >= min_reviews and i["price"]]
    return good[:limit]


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or datetime.now().strftime("%H%M%S")


def page_html(theme, items, fetched_at):
    esc = html.escape
    cards = []
    for it in items:
        cards.append(f"""<li class="item">
  {'<img src="' + esc(it['image']) + '" alt="" loading="lazy" width="128" height="128">' if it['image'] else ''}
  <div><p class="name">{esc(it['name'][:80])}</p>
  <p class="meta">{esc(it['shop'])}・{it['price']:,}円（{fetched_at}時点）・レビュー{it['reviews']}件</p>
  <a class="btn" href="{esc(it['url'])}" rel="sponsored nofollow noopener" target="_blank">楽天市場で見る</a></div>
</li>""")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(theme['title'])}｜選び方メモ</title>
<style>
:root{{--bg:#fff;--fg:#1d1d1f;--muted:#666;--accent:#bf0000;--card:#f5f5f7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--muted:#aaa;--card:#1d1d1f}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,"Hiragino Sans","Yu Gothic",sans-serif;line-height:1.7}}
main{{max-width:680px;margin:0 auto;padding:16px}}
.pr{{background:var(--card);border-left:4px solid var(--accent);padding:8px 12px;font-size:14px}}
.item{{display:flex;gap:12px;background:var(--card);border-radius:12px;padding:12px;margin:12px 0;list-style:none}}
.item img{{width:96px;height:96px;object-fit:contain;border-radius:8px;background:#fff}}
ul{{padding:0}} .name{{margin:0;font-weight:600}} .meta{{margin:4px 0;color:var(--muted);font-size:13px}}
.btn{{display:inline-block;background:var(--accent);color:#fff;padding:6px 14px;border-radius:999px;text-decoration:none;font-size:14px}}
</style></head><body><main>
<p class="pr">【PR】このページは広告（楽天アフィリエイト）を含みます。リンクから購入されると、運営者に報酬が支払われることがあります。</p>
<h1>{esc(theme['title'])}</h1>
<p>{esc(theme.get('audience', ''))}向けに、楽天市場でレビューの多い商品を集めました。価格・在庫は{fetched_at}時点のもので、変わることがあります。購入前に商品ページで確かめてください。</p>
<ul>{''.join(cards)}</ul>
<p class="meta">並び順はレビュー件数の多い順で、おすすめの順位ではありません。</p>
</main></body></html>
"""


def write_page(root, theme, items):
    fetched_at = datetime.now().strftime("%Y年%m月%d日")
    slug = datetime.now().strftime("%Y%m%d") + "-" + slugify(" ".join(theme.get("search_keywords", [])[:1]) or "picks")
    folder = Path(root) / "picks" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page_html(theme, items, fetched_at), encoding="utf-8")
    return slug, fetched_at
