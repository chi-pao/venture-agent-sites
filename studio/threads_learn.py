# -*- coding: utf-8 -*-
"""ノボログ：投稿の成績を集めて、ほかの人と比べ、次の投稿づくりに活かす。

毎日やること（py threads_learn.py all）
1. 自分の投稿の成績（Threads API）：表示・いいね・返信・再投稿・引用・シェア、リンクのクリック数。
2. 楽天アフィリエイトの成績（専用ブラウザ）：日ごとのクリック・売上・成果報酬、ショップ別、注文。
3. ほかのアフィリエイターの投稿（専用ブラウザ）：決めた言葉で Threads を検索し、
   見張るアカウントの最近の投稿も見て、いいね・返信・再投稿の数と文の型を集める。
4. 分析（Claude Code）：自分とほかを比べて「効いたこと・効かなかったこと・取り入れる型・次にやること」
   を data/threads_learnings.md に書く。threads_plan.py はこれを読んで次の候補を作る。

専用ブラウザは C:/AI/noborog-browser に置く、ノボログ専用の Chrome の入れ物。
最初に一度だけ `py threads_learn.py login` で開き、Threads と楽天アフィリエイトに
本人がログインしておく（パスワードはこちらでは扱わない）。ログインが切れたら、その部分だけ飛ばして記録する。
ほかの人の文は「型」を学ぶためだけに使い、文そのものは写さない。
"""
import argparse
import json
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

import threads as T

HERE = Path(__file__).resolve().parent
PROFILE = Path("C:/AI/noborog-browser")
OWN_FILE = "threads_metrics.json"
RAKUTEN_FILE = "rakuten_report.json"
OTHERS_FILE = "threads_others.json"
LEARN_MD = "threads_learnings.md"
LEARN_JSON = "threads_learnings.json"
POST_METRICS = "views,likes,replies,reposts,quotes,shares"
# Threads はログインなしだと、空白を含む検索は結果が出ないので、1語で書く
DEFAULT_QUERIES = ["楽天ROOM", "楽天おすすめ", "楽天購入品", "買ってよかった", "ブラックフライデー", "便利グッズ",
                   "楽天ランキング", "楽天アフィリエイト"]
SHORT_RE = re.compile(r"https://a\.r10\.to/\w+")


def _p(name):
    return T.DATA / name


def load(name, default):
    p = _p(name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return default


def save(name, data):
    _p(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 1. 自分の投稿の成績 ----------
def _values(res):
    out = {}
    for m in res.get("data", []):
        vals = m.get("values") or []
        if vals:
            out[m["name"]] = sum(v.get("value", 0) for v in vals)
        elif m.get("total_value"):
            out[m["name"]] = m["total_value"].get("value", 0)
    return out


def link_clicks(client, days=30):
    """リンクごとのクリック数（直近 days 日の合計）。"""
    until = int(time.time())
    res = client.call("GET", f"{client.uid}/threads_insights",
                      {"metric": "clicks", "since": until - days * 86400, "until": until}, client.token)
    clicks = {}
    for m in res.get("data", []):
        for v in m.get("link_total_values") or []:
            clicks[v["link_url"]] = clicks.get(v["link_url"], 0) + int(v.get("value", 0))
    return clicks


def collect_own(client, items):
    """投稿済みの1本ずつに成績を付け、アカウント全体の数字も残す。"""
    try:
        clicks = link_clicks(client)
    except T.ThreadsError as e:
        T.log(f"成績：クリック数を取れませんでした: {e}")
        clicks = {}
    n = 0
    me = None
    for it in items:
        if it.get("status") != "投稿済み" or not it.get("posted_ids"):
            continue
        parts = []
        for pid in it["posted_ids"]:
            try:
                parts.append(_values(client.call("GET", f"{pid}/insights", {"metric": POST_METRICS}, client.token)))
            except T.ThreadsError as e:
                parts.append({"error": str(e)[:100]})
        links = sorted({u for p in it["parts"] for u in SHORT_RE.findall(p)})
        m = {k: sum(p.get(k, 0) for p in parts) for k in POST_METRICS.split(",")}
        m["views"] = parts[0].get("views", 0) if parts else 0  # 表示は1本目で見る
        # Threads の「返信」には、自分で続けた2本目（PR とリンク）も入る。ほかの人からの返信だけを数え直す
        try:
            if me is None:
                me = client.me().get("username", "")
            res = client.call("GET", f"{it['posted_ids'][0]}/replies", {"fields": "username"}, client.token)
            m["replies"] = sum(1 for r in res.get("data", []) if r.get("username") != me)
        except T.ThreadsError:
            m["replies"] = max(0, m["replies"] - (len(it["posted_ids"]) - 1))
        m["clicks"] = sum(clicks.get(u, 0) for u in links)
        m["parts"] = parts
        m["checked_at"] = T.now().isoformat()
        it["metrics"] = m
        n += 1
    acct = load(OWN_FILE, {"days": {}, "followers": {}, "links": {}})
    try:
        until = int(time.time())
        res = client.call("GET", f"{client.uid}/threads_insights",
                          {"metric": "views", "since": until - 30 * 86400, "until": until}, client.token)
        for m in res.get("data", []):
            for v in m.get("values") or []:
                acct["days"][v["end_time"][:10]] = {"views": v.get("value", 0)}
        res = client.call("GET", f"{client.uid}/threads_insights", {"metric": "followers_count"}, client.token)
        acct["followers"][T.now().strftime("%Y-%m-%d")] = _values(res).get("followers_count", 0)
    except T.ThreadsError as e:
        T.log(f"成績：アカウントの数字を取れませんでした: {e}")
    acct["links"] = clicks
    save(OWN_FILE, acct)
    T.log(f"成績：投稿{n}件の数字を更新しました（クリックのあったリンク{sum(1 for v in clicks.values() if v)}本）")
    return n


# ---------- 2・3. 専用ブラウザで集める ----------
EXTRACT_JS = r"""() => [...document.querySelectorAll('div[data-pressable-container="true"]')].map(el => {
  const link = [...el.querySelectorAll('a[href*="/post/"]')].map(a => a.getAttribute('href'))[0] || '';
  const count = name => { for (const s of el.querySelectorAll('svg')) {
      const t = s.querySelector('title'); if (t && t.textContent.includes(name)) {
        for (const b of [s.parentElement && s.parentElement.parentElement, s.closest('[role="button"]')]) {
          const v = b && b.innerText.trim(); if (v && /^[\d.,]+\s*(万|千|K|M)?$/.test(v)) return v; }
        return ''; } } return ''; };
  const body = [...el.querySelectorAll('span[dir="auto"]')].map(s => s.innerText).join('\n');
  return {link, user: (link.match(/@([^/]+)/) || [])[1] || '', time: el.querySelector('time')?.getAttribute('datetime') || '',
          likes: count('いいね'), replies: count('コメント') || count('返信'), reposts: count('再投稿'), shares: count('シェア'),
          media: el.querySelectorAll('img[alt]:not([alt*="プロフィール"]), video').length,
          text: (body || el.innerText).slice(0, 600)};
})"""


def num(s):
    """「1.2万」「3,456」「12」を数にする。"""
    s = str(s or "0").replace(",", "").strip()
    m = re.match(r"([\d.]+)\s*(万|千|K|M)?", s)
    if not m:
        return 0
    v = float(m.group(1))
    return int(v * {"万": 10000, "千": 1000, "K": 1000, "M": 1000000}.get(m.group(2), 1))


def clean_post(p, source):
    return {"link": p["link"], "user": p["user"], "time": p["time"], "likes": num(p["likes"]),
            "replies": num(p["replies"]), "reposts": num(p["reposts"]), "shares": num(p["shares"]),
            "media": p.get("media", 0), "text": p["text"], "source": source}


def merge_others(store, posts, keep_days=30):
    now = T.now()
    for p in posts:
        if not p["link"] or p["user"] == "noborog.life":
            continue
        old = store.get(p["link"], {})
        p["first_seen"] = old.get("first_seen", now.isoformat())
        p["seen_at"] = now.isoformat()
        store[p["link"]] = p
    cut = (now - timedelta(days=keep_days)).isoformat()
    return {k: v for k, v in store.items() if v.get("seen_at", "") >= cut}


def open_browser(pw, headless=True):
    PROFILE.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(str(PROFILE), channel="chrome", headless=headless,
                                                 locale="ja-JP", viewport={"width": 1280, "height": 1600})


def collect_rakuten(page):
    page.goto("https://affiliate.rakuten.co.jp/report/", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    data = page.evaluate("""async () => { const o = {};
      for (const k of ['summary', 'shop', 'order']) {
        const r = await fetch('/api/report/' + k + '?duration=90');
        const t = await r.text(); try { o[k] = JSON.parse(t); } catch (e) { o[k] = null; } }
      return o; }""")
    if not data.get("summary"):
        raise RuntimeError("楽天アフィリエイトにログインしていないようです（py threads_learn.py login）")
    data["fetched_at"] = T.now().isoformat()
    save(RAKUTEN_FILE, data)
    rows = data["summary"].get("rows", {}).get("data", [])
    T.log(f"楽天：90日でクリック{sum(r['clicks'] for r in rows)}・売上{sum(r['sales'] for r in rows)}件"
          f"・成果報酬{sum(r['rewards'] for r in rows)}円")
    return data


def collect_others(page, cfg):
    from urllib.parse import quote
    store = load(OTHERS_FILE, {})
    got = []
    targets = [(f"https://www.threads.com/search?q={quote(q)}&serp_type=default", f"検索:{q}")
               for q in cfg.get("threads_watch_queries") or DEFAULT_QUERIES]
    targets += [(f"https://www.threads.com/@{u}", f"見張り:@{u}") for u in cfg.get("threads_watch_accounts") or []]
    for url, source in targets:
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
            for _ in range(3):
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1200)
            posts = [clean_post(p, source) for p in page.evaluate(EXTRACT_JS)]
            got += posts
        except Exception as e:  # 1つ失敗しても残りは集める
            T.log(f"ほかの人：{source} を読めませんでした: {str(e)[:120]}")
    if not got:
        raise RuntimeError("Threads の投稿を1件も読めませんでした（ログインが切れているかもしれません）")
    save(OTHERS_FILE, merge_others(store, got))
    T.log(f"ほかの人：{len(got)}件の投稿を集めました")
    return got


def collect_browser(cfg, headless=True):
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as pw:
        ctx = open_browser(pw, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for name, fn in (("楽天", lambda: collect_rakuten(page)), ("ほかの人", lambda: collect_others(page, cfg))):
            try:
                fn()
            except Exception as e:
                errors.append(f"{name}: {str(e)[:200]}")
                T.log(f"{name}の数字を集められませんでした: {str(e)[:200]}")
        ctx.close()
    return errors


def login():
    """専用ブラウザを開く。本人が Threads と楽天アフィリエイトにログインして、閉じる。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = open_browser(pw, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.threads.com/login")
        ctx.new_page().goto("https://affiliate.rakuten.co.jp/report/")
        print("開いたブラウザで、Threads と楽天アフィリエイトにログインしてください。終わったらブラウザを閉じてください。")
        try:
            while ctx.pages:
                time.sleep(1)
        except Exception:
            pass


# ---------- 4. 比べて、策を練る ----------
def own_rows(items, days=30):
    cut = (T.now() - timedelta(days=days)).isoformat()
    rows = []
    for it in items:
        if it.get("status") != "投稿済み" or it.get("posted_at", "") < cut:
            continue
        m = it.get("metrics") or {}
        media = "動画" if it.get("video") else ("カード" if it.get("card") else ("写真" if it.get("images") else "文だけ"))
        rows.append({"id": it["id"], "posted_at": it["posted_at"][:16], "slot": it.get("slot"), "kind": it.get("kind"),
                     "title": it.get("title"), "media": media, "parts": len(it["parts"]), "topic": it.get("topic"),
                     "first_part": it["parts"][0][:160], "shop": (it.get("product") or {}).get("name", "")[-30:],
                     "genre": (it.get("product") or {}).get("genre"),
                     **{k: m.get(k) for k in ("views", "likes", "replies", "reposts", "quotes", "shares", "clicks")}})
    return rows


def top_others(store, n=25, days=14):
    cut = (T.now() - timedelta(days=days)).isoformat()
    posts = [p for p in store.values() if (p.get("time") or "") >= cut[:10]]
    posts.sort(key=lambda p: p["likes"] + 3 * p["replies"] + 2 * p["reposts"], reverse=True)
    return posts[:n]


def rakuten_brief(data):
    if not data:
        return "（まだ取れていない）"
    rows = (data.get("summary") or {}).get("rows", {}).get("data", [])
    recent = [r for r in rows if r["clicks"] or r["sales"]]
    shops = (data.get("shop") or {}).get("rows", [])
    orders = (data.get("order") or {}).get("rows", [])
    return json.dumps({"取得": data.get("fetched_at", "")[:16], "日ごと（動きのあった日）": recent[-30:],
                       "ショップ別": [{k: s.get(k) for k in ("shop_name", "clicks", "sales", "rewards")} for s in shops[:20]],
                       "注文": orders[:20]}, ensure_ascii=False)


ANALYZE_PROMPT = """あなたは Threads アカウント「ノボログ」（@noborog.life、楽天アフィリエイト）の分析担当です。
下の数字を比べて、次の投稿づくりで何を変えるかを決めてください。

## 自分の投稿（直近30日。views=表示, clicks=楽天リンクのクリック）
{own}

## アカウント全体（日ごとの表示・フォロワー）
{acct}

## 楽天アフィリエイトの成績（直近90日）
{rakuten}

## ほかの楽天アフィリエイターで反応の多い投稿（直近14日、上位）
{others}

## 前回の分析
{prev}

## 考え方
- 数が少ないうちは言い切らない。「まだ{n}本なので傾向の段階」のように、確かさも書く。
- 自分の数字と、ほかの人の伸びている投稿の「型」（1行目のつかみ、文の長さ、質問、一覧、写真の枚数、
  リンクを何本目に置くか、投稿の時間、話題）を比べる。
- ほかの人の文は写さない。型だけを取り出して、ノボログ（48歳・子育てを終えたシングルファザー、出しすぎない）に合う形にする。
- 使った体験の作り話、最安・No.1・絶対、ほかの人の名前を出す案は入れない。
- 「次にやること」は、次の候補づくりでそのまま使える具体的な指示にする（例：12:00 は質問型を1案入れる）。
- 一番の目的は「見られる → リンクが押される → 売れる」。表示が多い型と、クリック・売上（楽天のショップ別・注文）に
  つながった型を分けて考え、売上につながる方を優先する。
- 売れ筋の商品は、新しい商品でなくても何度出してよい。反応があった商品は、次にどの切り口（別の困りごと・別の場面・
  保存用の一覧の中で・質問の答えとして など）で出し直すとよいかを next_rules か try_next に書く。
- リンクは2本目（自分の返信）に置く形を基本にする（ほかの人のデータで、1本目にリンクがある投稿は反応がほぼ0）。
- 1投稿に1つトピックタグを付ける。どのタグの投稿が見られたかも見る。

## 答え方
JSON だけで答える。
{{"summary": "今の状況を2〜3文",
  "numbers": "大事な数字をひとことで（例：7日で表示120・クリック3・売上0）",
  "what_works": ["効いていること"], "what_doesnt": ["効いていないこと"],
  "steal": [{{"from": "どんな投稿から（アカウント名は書かない）", "pattern": "取り入れる型", "how": "ノボログでの使い方"}}],
  "next_rules": ["次の候補づくりで守る具体的な指示（5つまで）"],
  "try_next": ["試してみる新しいこと（2つまで）"],
  "confidence": "低|中|高"}}
"""


def analyze(cfg, items, ask=None):
    import threads_plan as P
    ask = ask or P.ask_claude
    own = own_rows(items)
    acct = load(OWN_FILE, {})
    prev = load(LEARN_JSON, {})
    others = [{k: p[k] for k in ("time", "likes", "replies", "reposts", "media", "source")} | {"text": p["text"][:300]}
              for p in top_others(load(OTHERS_FILE, {}))]
    prompt = ANALYZE_PROMPT.format(
        own=json.dumps(own, ensure_ascii=False), n=len(own),
        acct=json.dumps({"days": dict(sorted(acct.get("days", {}).items())[-14:]),
                         "followers": acct.get("followers", {})}, ensure_ascii=False),
        rakuten=rakuten_brief(load(RAKUTEN_FILE, None)), others=json.dumps(others, ensure_ascii=False),
        prev=json.dumps({k: prev.get(k) for k in ("summary", "next_rules", "try_next")}, ensure_ascii=False) if prev else "（はじめて）")
    res = ask(prompt, cfg)
    res["made_at"] = T.now().isoformat()
    res["own_posts"] = len(own)
    save(LEARN_JSON, res)
    _p(LEARN_MD).write_text(learn_md(res, own), encoding="utf-8")
    T.log(f"分析：{res.get('numbers', '')}")
    return res


def learn_md(res, own):
    L = [f"# 成績と次の手（{res['made_at'][:16].replace('T', ' ')}）", "",
         f"**今の状況**：{res.get('summary', '')}", "", f"**数字**：{res.get('numbers', '')}（確かさ：{res.get('confidence', '')}）", ""]
    for title, key in (("効いていること", "what_works"), ("効いていないこと", "what_doesnt"),
                       ("次の候補づくりで守ること", "next_rules"), ("試すこと", "try_next")):
        L += [f"## {title}"] + [f"- {x}" for x in res.get(key) or []] + [""]
    L += ["## ほかの人から取り入れる型"]
    L += [f"- {s.get('pattern')}（{s.get('from')}）→ {s.get('how')}" for s in res.get("steal") or []]
    L += ["", "## 投稿ごとの数字", "", "| 投稿 | 時間 | 形 | 表示 | いいね | 返信 | クリック |", "|---|---|---|---|---|---|---|"]
    for r in own:
        L.append(f"| {r['id']} {r['title']} | {r['posted_at'][5:]} | {r['media']} | {r['views'] or 0} | "
                 f"{r['likes'] or 0} | {r['replies'] or 0} | {r['clicks'] or 0} |")
    return "\n".join(L) + "\n"


def plan_section():
    """threads_plan のお願い文に入れる『前回までの成績から決めたこと』。"""
    res = load(LEARN_JSON, None)
    if not res:
        return ""
    lines = ["## これまでの成績から決めたこと（必ず反映する。数が少ないうちは参考程度）",
             f"状況：{res.get('summary', '')}"]
    lines += [f"- {x}" for x in res.get("next_rules") or []]
    lines += [f"- 試す：{x}" for x in res.get("try_next") or []]
    lines += [f"- 取り入れる型：{s.get('pattern')} → {s.get('how')}" for s in res.get("steal") or []]
    return "\n".join(lines)


# ---------- コマンド ----------
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stdout is None or sys.stderr is None:
        # 予約（pyw）で動くときは画面の出口がない。ブラウザ部品が困らないよう、捨て場所を渡す
        import os
        sink = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or sink
        sys.stderr = sys.stderr or sink
    ap = argparse.ArgumentParser(description="ノボログの成績集めと分析")
    ap.add_argument("cmd", choices=["login", "own", "browser", "analyze", "all"])
    ap.add_argument("--show", action="store_true", help="専用ブラウザを画面に出して動かす")
    args = ap.parse_args(argv)
    if args.cmd == "login":
        return login()
    import threads_plan as P
    cfg = P.load_full_cfg()
    if args.cmd in ("own", "all"):
        items = T.load_queue()
        try:
            collect_own(T.Client(T.read_token()), items)
            got = {it["id"]: it["metrics"] for it in items if it.get("metrics")}
            fresh = T.load_queue()  # 集めている間に自動投稿が書いた分を消さないよう、読み直して数字だけ足す
            for it in fresh:
                if it["id"] in got:
                    it["metrics"] = got[it["id"]]
            T.save_queue(fresh)
        except T.ThreadsError as e:
            T.log(f"成績：Threads の数字を取れませんでした: {e}")
    if args.cmd in ("browser", "all"):
        try:
            collect_browser(cfg, headless=not args.show)
        except Exception as e:  # ブラウザが動かなくても、分析は続ける
            T.log(f"専用ブラウザが動きませんでした: {str(e)[:200]}")
    if args.cmd in ("analyze", "all"):
        try:
            analyze(cfg, T.load_queue())
        except Exception as e:
            T.log(f"分析に失敗しました: {str(e)[:200]}")
            raise
        print(_p(LEARN_MD).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
