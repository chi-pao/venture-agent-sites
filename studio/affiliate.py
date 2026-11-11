# -*- coding: utf-8 -*-
"""⑩物販・アフィリエイト部の道具：楽天の商品検索と、商品まとめページづくり。

- 楽天ウェブサービスの「楽天市場商品検索API」を、設定（rakuten_app_id）があるときだけ使う。
  アプリIDは楽天ウェブサービスで無料登録して取る。アフィリエイトIDを渡すと、紹介リンク（affiliateUrl）付きで返る。
- 仕様（URL・項目名）は以前の公開版に合わせた。2026-11-11 は公式ページが混雑で開けず未確認。
  変わっていたら config.json の rakuten_endpoint で直せる。
- まとめページは PR 表記を一番上に出し、リンクには rel="sponsored nofollow" を付ける。価格は取得日時点と書く。
"""
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"


class RakutenError(RuntimeError):
    pass


def search(cfg, keyword, hits=10):
    """楽天市場で探す。レビューの多い順。戻り値は扱いやすい形の商品リスト。"""
    params = {"applicationId": cfg["rakuten_app_id"], "keyword": keyword, "hits": hits,
              "sort": "-reviewCount", "formatVersion": 2, "availability": 1}
    if cfg.get("rakuten_affiliate_id"):
        params["affiliateId"] = cfg["rakuten_affiliate_id"]
    url = (cfg.get("rakuten_endpoint") or DEFAULT_ENDPOINT) + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "venture-studio"}),
                                    timeout=20) as res:
            data = json.load(res)
    except Exception as e:
        raise RakutenError(f"楽天の商品検索に失敗: {e}") from e
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
                      "url": link, "is_affiliate": bool(it.get("affiliateUrl")),
                      "reviews": it.get("reviewCount", 0), "rating": it.get("reviewAverage", 0), "image": img})
    return items


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
