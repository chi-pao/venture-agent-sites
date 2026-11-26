# -*- coding: utf-8 -*-
"""ノボログ：投稿候補を「Threads に出たときの見た目」で確認するページを作る。

- 1本目→2本目→リンクの投稿を、Threads のスレッドと同じ並びで見せる。
- リンクの投稿には、Threads が出すのと同じような「リンクカード」（商品ページの画像と題）を付ける。
  画像と題は、商品ページの og:image / og:title から取る（Threads も同じ所を読む）。
- 画像はページの中に埋め込むので、スマホでもオフラインでも見られる。

使い方:
  py threads_preview.py 1114        11/14 分の候補（予定表の for_date か ID の頭）をページにする
  py threads_preview.py --ids 1113-01 1113-03 ...
"""
import argparse
import base64
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import threads as T  # noqa: E402

ICON = HERE / "assets" / "noborog_icon.png"
URL_RE = re.compile(r"https?://[^\s　）)」]+")
UA = {"User-Agent": "Mozilla/5.0 (compatible; noborog-preview)"}
SLOT_NAMES = {"07:00": "毎日のおなじみ", "12:00": "紹介", "15:00": "質問・保存用まとめ",
              "19:00": "紹介", "21:00": "挑戦記・日常・予告"}


# ---------- リンクカードの材料 ----------
def _get(url, limit=3_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.geturl(), r.headers.get_content_charset(), r.read(limit)


def _decode(raw, charset):
    for enc in filter(None, [charset, "utf-8", "euc-jp", "shift_jis"]):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def thumb(img_url):
    """楽天の画像は小さい版（400px）にして軽くする。"""
    m = re.match(r"https?://shop\.r10s\.jp/(.+)$", img_url or "")
    if m:
        return f"https://thumbnail.image.rakuten.co.jp/@0_mall/{m.group(1)}?_ex=400x400"
    return img_url


def product_images(item_url, n=8, size=1000):
    """楽天の商品ページの画像（ショップが並べた順）を n 枚まで。加工はしない。"""
    final, cs, raw = _get(item_url)
    text = raw.decode("latin-1")  # URL だけ取るので文字コードは問わない
    shop = urllib.parse.urlparse(final).path.strip("/").split("/")[0]
    m = re.search(r'"images":\[(.*?)\]', text, re.S)
    locs = re.findall(r'"location":"([^"]+)"', m.group(1)) if m else []
    out = []
    for loc in locs:
        if not re.search(r"\.(jpe?g|png)$", loc, re.I):
            continue
        url = f"https://thumbnail.image.rakuten.co.jp/@0_mall/{shop}/cabinet{loc}?_ex={size}x{size}"
        if url not in out:
            out.append(url)
        if len(out) >= n:
            break
    return out


def embed(url, cache):
    """プレビュー用に画像を小さくしてページに埋め込む。"""
    small = re.sub(r"_ex=\d+x\d+", "_ex=400x400", url)
    key = "img:" + small
    if key not in cache:
        try:
            _, _, img = _get(small, 1_500_000)
            cache[key] = {"data": "data:image/jpeg;base64," + base64.b64encode(img).decode()}
        except Exception as e:
            cache[key] = {"error": str(e)[:100]}
    return cache[key].get("data", "")


def scrape_product(item_url):
    """API がないときの予備：商品ページから名前・価格・レビュー件数・説明を取る。"""
    final, cs, raw = _get(item_url)
    text = _decode(raw, cs)
    def meta(pat):
        m = re.search(pat, text)
        return html.unescape(m.group(1)).strip() if m else ""
    name = re.sub(r"^【楽天市場】", "", meta(r'property="og:title" content="([^"]*)'))
    price = meta(r'itemprop="price" content="(\d+)')
    reviews = meta(r'itemprop="reviewCount" content="(\d+)')
    return {"name": name, "price": int(price) if price else 0, "reviews": int(reviews) if reviews else 0,
            "caption": meta(r'property="og:description" content="([^"]*)')[:300], "item_url": final.split("?")[0],
            "shop": urllib.parse.urlparse(final).path.strip("/").split("/")[0],
            "postage": 0 if "送料無料" in name else None}


def og_info(url, cache):
    if url in cache:
        return cache[url]
    info = {"url": url}
    try:
        final, cs, raw = _get(url)
        text = _decode(raw, cs)
        if not cs:
            m = re.search(r'charset=["\']?([\w-]+)', text[:3000], re.I)
            if m and m.group(1).lower() not in ("utf-8", "utf8"):
                text = _decode(raw, m.group(1))
        for key in ("title", "image", "description"):
            m = re.search(rf'<meta[^>]+property=["\']og:{key}["\'][^>]+content=["\']([^"\']*)', text, re.I) or \
                re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']og:{key}', text, re.I)
            if m:
                info[key] = html.unescape(m.group(1)).strip()
        info["domain"] = urllib.parse.urlparse(final).netloc
        if info.get("image"):
            _, _, img = _get(thumb(info["image"]), 1_500_000)
            info["image_data"] = "data:image/jpeg;base64," + base64.b64encode(img).decode()
    except Exception as e:  # 取れなくてもページは作る
        info["error"] = str(e)[:200]
    cache[url] = info
    return info


# ---------- 見た目 ----------
def body_html(text):
    out, last = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        u = m.group(0)
        shown = u if len(u) <= 34 else u[:31] + "…"
        out.append(f'<span class="link">{html.escape(shown)}</span>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out).replace("\n", "<br>")


def card_html(info):
    if not info:
        return ""
    title = info.get("title") or "楽天市場"
    title = re.sub(r"^【楽天市場】", "", title)
    img = f'<img src="{info["image_data"]}" alt="">' if info.get("image_data") else '<div class="noimg">画像なし</div>'
    return (f'<div class="card">{img}<div class="card-t"><div class="dom">{html.escape(info.get("domain", ""))}</div>'
            f'<div class="ttl">{html.escape(title[:90])}</div></div></div>')


def _local_data(path, mime):
    p = T.DATA / path
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def gallery_html(it, cache):
    """1本目に付く物を、Threads と同じ順（動画→写真カード→商品写真）で横にならべる。"""
    tiles = []
    v = it.get("video") or {}
    if v.get("local"):
        prev = str(Path(v["local"]).with_name("preview.mp4"))
        data = _local_data(prev, "video/mp4")
        if data:
            tiles.append(f'<video src="{data}" muted loop autoplay playsinline controls></video>')
    c = it.get("card") or {}
    if c.get("local"):
        data = _local_data(c["local"], "image/jpeg")
        if data:
            tiles.append(f'<img src="{data}" alt="">')
    tiles += [f'<img src="{embed(u, cache)}" alt="">' for u in (it.get("images") or [])]
    return f'<div class="gallery">{"".join(tiles)}</div>' if tiles else ""


def post_html(text, when, info, last, icon, gallery=""):
    return f"""<div class="post{' last' if last else ''}">
  <div class="side"><img class="av" src="{icon}" alt=""><div class="line"></div></div>
  <div class="main">
    <div class="head"><b>noborog.life</b><span class="when">{html.escape(when)}</span></div>
    <div class="text">{body_html(text)}</div>
    {gallery}
    {card_html(info)}
    <div class="acts"><span>♡</span><span>💬</span><span>🔁</span><span>➤</span></div>
  </div>
</div>"""


def item_html(it, cache, icon):
    links = []
    posts = []
    for i, part in enumerate(it["parts"]):
        m = URL_RE.search(part)
        info = og_info(m.group(0), cache) if m else None
        item_url = it.get("item_url") or (it.get("product") or {}).get("item_url")
        if not m and "（短縮URL）" in part and item_url:
            info = og_info(item_url, cache)  # リンクはまだだが、カードの見た目は先に見せる
        if m:
            links.append(info)
        when = it.get("slot") or ""
        gal = gallery_html(it, cache) if i == 0 else ""
        posts.append(post_html(part, when if i == 0 else "", info, i == len(it["parts"]) - 1, icon, gal))
    problems = T.check_rules(it["parts"], it.get("images"))
    if any("（短縮URL）" in p for p in it["parts"]):
        problems = problems or ["リンクがまだ入っていません"]
    status = ('<span class="ok">✓ 決まりチェック OK</span>' if not problems else
              '<span class="ng">⚠ ' + html.escape(" / ".join(problems)) + "</span>")
    counts = "・".join(f"{len(p)}字" for p in it["parts"])
    extra = []
    if it.get("video"):
        extra.append("動画")
    if it.get("card"):
        extra.append("写真カード")
    if it.get("images"):
        extra.append(f"商品写真{len(it['images'])}枚")
    if extra:
        counts += "／1本目に" + "・".join(extra)
    num = it["id"].split("-")[-1]
    prod = ""
    if it.get("product"):
        p = it["product"]
        prod = (f'<div class="meta">商品：{html.escape(p["name"][:50])}｜{p["price"]:,}円〜' +
                (f'｜レビュー{p["reviews"]}件' if p.get("reviews") else "") + '</div>')
    bad_link = [x for x in links if x and x.get("error")]
    if bad_link:
        status += '<span class="ng">⚠ リンク先を開けませんでした</span>'
    return f"""<section class="cand" id="c{num}">
  <div class="ch"><span class="num">{num}</span><div><div class="t">{html.escape(it.get('title', ''))}</div>
  <div class="meta">{html.escape(it.get('kind', ''))}｜{len(it['parts'])}本のスレッド（{counts}）</div>{prod}
  {f'<div class="why">💡 {html.escape(it["why"])}</div>' if it.get("why") else ""}
  {f'<div class="why">🎯 ' + html.escape("／".join(f"{k}：{v}" for k, v in it["target"].items())) + '</div>' if it.get("target") else ""}
  {f'<div class="why">✍️ まねた型：{html.escape(it["style"])}</div>' if it.get("style") else ""}
  {f'<div class="why">💰 楽天の料率：{html.escape(str((it.get("product") or {}).get("rate")))}</div>' if (it.get("product") or {}).get("rate") else ""}
  <div>{status}</div></div></div>
  <div class="phone">{''.join(posts)}</div>
</section>"""


CSS = """
:root{--bg:#f3f3f3;--fg:#000;--muted:#999;--panel:#fff;--line:#d9d9d9;--link:#0095f6;--ok:#16803c;--ng:#c62828}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#000;--fg:#f3f5f7;--muted:#777;--panel:#101010;--line:#333;--ok:#4ade80;--ng:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic UI",sans-serif;font-size:15px;line-height:1.45}
header{max-width:560px;margin:0 auto;padding:20px 16px 4px}h1{font-size:20px;margin:0 0 6px}
header p{margin:4px 0;color:var(--muted);font-size:13px}
h2{max-width:560px;margin:28px auto 8px;padding:0 16px;font-size:16px}
.cand{max-width:560px;margin:0 auto 22px;padding:0 16px}
.ch{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px}
.num{flex:none;width:34px;height:34px;border-radius:50%;background:var(--fg);color:var(--bg);display:grid;place-items:center;font-weight:700}
.t{font-weight:700}.why{margin:4px 0;padding:6px 10px;border-radius:8px;background:var(--panel);border:1px solid var(--line);font-size:13px}.meta{color:var(--muted);font-size:12px}.ok{color:var(--ok);font-size:12px;font-weight:600}
.ng{color:var(--ng);font-size:12px;font-weight:600;display:block}
.phone{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 14px 4px}
.post{display:flex;gap:10px}.side{display:flex;flex-direction:column;align-items:center;width:36px;flex:none}
.av{width:36px;height:36px;border-radius:50%;object-fit:cover;border:1px solid var(--line)}
.line{flex:1;width:2px;background:var(--line);margin:6px 0 4px;border-radius:2px}.post.last .line{display:none}
.main{flex:1;min-width:0;padding-bottom:10px}.head{display:flex;gap:6px;align-items:baseline}
.when{color:var(--muted);font-size:13px}.text{margin-top:2px;overflow-wrap:anywhere}
.link{color:var(--link)}
.gallery{display:flex;gap:6px;overflow-x:auto;margin-top:10px;scroll-snap-type:x mandatory;padding-bottom:4px}
.gallery video{flex:none;height:288px;width:230px;border-radius:10px;background:#000;scroll-snap-align:start}
.gallery img{flex:none;height:288px;width:230px;object-fit:contain;border-radius:10px;border:1px solid var(--line);
background:#fff;scroll-snap-align:start}
.card{margin-top:10px;border:1px solid var(--line);border-radius:12px;overflow:hidden;max-width:420px}
.card img{display:block;width:100%;aspect-ratio:1.91/1;object-fit:cover;background:#fff}
.noimg{aspect-ratio:1.91/1;display:grid;place-items:center;color:var(--muted);background:var(--bg)}
.card-t{padding:8px 12px}.dom{color:var(--muted);font-size:12px}
.ttl{font-weight:600;font-size:14px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.acts{display:flex;gap:18px;color:var(--muted);margin-top:8px;font-size:15px;filter:grayscale(1);opacity:.55}
"""


def _room_html():
    """楽天ROOM に載せる候補（data/room_candidates.json の「候補」）。OK の後に、のぼるさんの Chrome で載せる。"""
    p = T.DATA / "room_candidates.json"
    try:
        rows = [r for r in json.loads(p.read_text(encoding="utf-8")) if r.get("status") == "候補"]
    except (OSError, ValueError):
        return ""
    if not rows:
        return ""
    out = ["<h2>楽天ROOM に載せる候補（OK の番号を送ってください。例：「M1, M3」）</h2>"]
    for r in rows:
        img = f'<img src="{html.escape(r["image"])}" alt="" style="width:120px;border-radius:8px;float:right;margin-left:8px">' if r.get("image") else ""
        out.append(f"""<div class="cand"><div class="why">{img}<b>{html.escape(r.get("no", ""))}</b>　{html.escape(r.get("name", "")[:60])}<br>
💰 料率：{html.escape(str(r.get("rate") or "不明"))}　／　{html.escape(str(r.get("why", "")))}<br><br>
<b>オススメポイント：</b>{body_html(r.get("text", ""))}<div style="clear:both"></div></div></div>""")
    return "".join(out)


def _replies_html():
    try:
        import threads_replies
        return threads_replies.section_html(html.escape)
    except Exception:
        return ""


def page(items, title, cache):
    icon = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode() if ICON.exists() else ""
    groups = {}
    for it in items:
        groups.setdefault(it.get("slot") or "時間未定", []).append(it)
    body = []
    for slot in sorted(groups):
        name = SLOT_NAMES.get(slot, "")
        body.append(f"<h2>{html.escape(slot)}　{html.escape(name)}</h2>")
        body += [item_html(it, cache, icon) for it in groups[slot]]
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>{CSS}</style></head><body>
<header><h1>{html.escape(title)}</h1>
<p>Threads に出たときと同じ並びです（1本目の下に、2本目・リンクの投稿が続きます）。</p>
<p>リンクの下のカードは、Threads が商品ページから作る見た目に近づけた物です。実際の切り取り方は少し変わることがあります。</p>
<p>出したい番号を送ってください（例：「01, 03, 06, 07, 10」）。直したい所もそのまま書いてOKです。</p>
<p>作った時刻：{datetime.now():%m/%d %H:%M}</p></header>
{''.join(body)}
{_room_html()}
{_replies_html()}
</body></html>"""


def build(items, out_path, title):
    cache_path = T.DATA / "og_cache.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
    Path(out_path).write_text(page(items, title, cache), encoding="utf-8")
    cache_path.write_text(json.dumps({k: v for k, v in cache.items() if not v.get("error") and not k.startswith("img:")},
                                     ensure_ascii=False), encoding="utf-8")
    return out_path


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("mmdd", nargs="?")
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    items = T.load_queue()
    if a.ids:
        chosen = [T.find(items, i) for i in a.ids]
        tag = a.ids[0].split("-")[0]
    else:
        tag = a.mmdd or datetime.now().strftime("%m%d")
        chosen = [it for it in items if it["id"].startswith(tag + "-") and it["status"] != "取り消し"]
    if not chosen:
        print("その日の候補がありません")
        return 1
    day = f"{int(tag[:2])}月{int(tag[2:])}日"
    out = a.out or (T.DATA / f"threads_preview_{tag}.html")
    build(chosen, out, f"ノボログ 投稿プレビュー（{day}分）")
    print(f"作りました: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
