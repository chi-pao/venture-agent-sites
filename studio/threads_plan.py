# -*- coding: utf-8 -*-
"""ノボログ：次の日の Threads 投稿候補を自動で作る。

流れ（毎晩タスクスケジューラーが1回呼ぶ）:
  1. 楽天のランキングを、いくつかのジャンルで取る（アフィリエイトリンク付き）
  2. Claude Code（claude -p）に、のぼるさん目線の文を書いてもらう
     - 商品の事実は、楽天から取った情報だけを渡す（作り話をさせない）
  3. リンクの投稿（PR｜楽天市場…＋リンク＋取得日の価格）は、このプログラムが自分で付ける
     - AI にリンクを書かせないので、リンク違い・PR 書き忘れが起きない
  4. 決まりの確認をして、予定表に「候補」として入れる。確認用の一覧（Markdown）も作る

のぼるさんが一覧を見て OK した物だけ `py threads.py pick ID ...` で承認され、時間に投稿される。

使い方:
  py threads_plan.py                 明日の候補を作る
  py threads_plan.py --date 2026-11-14
  py threads_plan.py --products-only 楽天から取れるかだけ確かめる（AI は呼ばない）
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import affiliate as A  # noqa: E402
import threads as T  # noqa: E402
from engine import EngineError, extract_json  # noqa: E402

SLOTS = [
    ("07:00", "毎日のおなじみ", "楽天ランキングのメモ。リンクなし。売れている物から季節や暮らしの流れを一言で読む"),
    ("12:00", "紹介", "商品紹介。1本目＝商品写真つきのつかみ、2本目＝PR・ひとこと・リンク"),
    ("15:00", "質問・保存用まとめ", "リンクなし。返信したくなる質問か、保存したくなる表・まとめ"),
    ("19:00", "紹介", "商品紹介。1本目＝商品写真つきのつかみ、2本目＝PR・ひとこと・リンク"),
    ("21:00", "挑戦記・日常・予告", "リンクなし。48歳の挑戦の記録、暮らしの一言、明日の予告など"),
]
# 楽天のジャンル（間違っていても、そのジャンルが飛ばされるだけ）
# 2026-11-26 のぼるさんの決まり：メインは日用品（6〜7割）、サブは家電・ファッション。ほかのジャンルは一切出さない（楽天ROOM も）。
MAIN_GROUP = "日用品"
SUB_GROUPS = ("家電", "ファッション")
DEFAULT_GENRES = {"日用品": 215783, "家電": 562637, "ファッション（レディース）": 100371,
                  "ファッション（メンズ）": 551177, "ファッション（インナー・下着）": 100433, "ファッション（靴）": 558885}


def genre_group(label):
    """ジャンル名から「日用品／家電／ファッション」を返す。決めたジャンルでなければ None。"""
    g = str(label or "")
    if "インテリア" in g or "寝具" in g or "収納" in g:
        return None
    for name in (MAIN_GROUP,) + SUB_GROUPS:
        if name in g:
            return name
    if any(k in g for k in ("インナー", "下着", "靴", "バッグ")):
        return "ファッション"
    return None
PROMPT_PRODUCTS = 30


def load_full_cfg():
    """config.json に、secrets/rakuten.json（楽天のアプリID・アクセスキー・アフィリエイトID）を重ねる。"""
    cfg = {}
    for p in (HERE / "config.json", T.SECRETS / "rakuten.json"):
        if p.exists():
            cfg.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8-sig")).items() if v not in ("", None)})
    return cfg


# ---------- 1. 商品を集める ----------
def sold_counts(report=None):
    """楽天アフィリエイトの成果（rakuten_report.json）から、売れた商品ページの URL ごとの件数。"""
    if report is None:
        path = T.DATA / "rakuten_report.json"
        try:
            report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            report = {}
    out = {}
    for row in ((report.get("order") or {}).get("rows") or []):
        url = (row.get("item_url") or "").split("?")[0].rstrip("/") + "/"
        if url != "/":
            out[url] = out.get(url, 0) + 1
    return out


def past_products(items, cfg, limit=4, sold=None):
    """前に出して反応があった商品を、出し直しの候補にする（売れ筋は何度出してもよい。切り口は変える）。
    実際に売れた商品は「定番」として、反応の点数にかかわらず、短い間隔（threads_repeat_days_sold・既定2日）でくり返し出す。
    リンク（短縮URL）は前の物をそのまま使う。価格は前に取った日の物なので、その日付で書く。"""
    sold = sold_counts() if sold is None else sold
    days = int(cfg.get("threads_repeat_days", 3))
    days_sold = int(cfg.get("threads_repeat_days_sold", 2))
    upcoming = recent_codes(items, days=days)
    upcoming_sold = recent_codes(items, days=days_sold)
    best = {}
    for it in items:
        p, m = it.get("product"), it.get("metrics") or {}
        if it.get("status") != "投稿済み" or not p or not p.get("url") or "PENDING" in p.get("url", ""):
            continue
        if not genre_group(p.get("genre")):  # 決めたジャンル以外は、売れた物でも出さない
            continue
        n_sold = sold.get((p.get("item_url") or "").split("?")[0].rstrip("/") + "/", 0)
        gap = timedelta(days=days_sold if n_sold else days)
        if p.get("code") in (upcoming_sold if n_sold else upcoming) or T.now() - T.parse_time(it["posted_at"]) < gap:
            continue
        score = n_sold * 10000 + (m.get("clicks") or 0) * 50 + (m.get("replies") or 0) * 10 + (m.get("views") or 0)
        if not n_sold and score < int(cfg.get("threads_repeat_min_score", 30)):
            continue
        if score > best.get(p["code"], ({}, -1))[1]:
            past = {"出した日": it["posted_at"][:10], "前の1本目の書き出し": it["parts"][0].splitlines()[0][:60],
                    "表示": m.get("views"), "クリック": m.get("clicks"), "返信": m.get("replies")}
            if n_sold:
                past["楽天で売れた"] = f"{n_sold}件（定番。毎回ちがう切り口・ちがう型で何度も出す）"
            best[p["code"]] = (dict(p, past=past, fetched_at=it.get("made_at") or it["posted_at"]), score)
    return [p for p, _ in sorted(best.values(), key=lambda x: -x[1])][:limit]


def recent_codes(items, days=30):
    """最近出した・出す予定の商品は、また候補にしない。"""
    since = (T.now() - timedelta(days=days)).isoformat()
    return {it.get("product", {}).get("code") for it in items
            if it.get("product") and it["status"] in ("承認済み", "投稿済み")
            and (it.get("time") or it.get("posted_at") or "") >= since}


def gather(cfg, items, fetch=A.ranking):
    if fetch is A.ranking and not A.ready(cfg):
        raise A.RakutenError("楽天のアプリIDとアクセスキーがありません（secrets/rakuten.json に書く）")
    genres = cfg.get("threads_genres") or DEFAULT_GENRES
    min_reviews = int(cfg.get("threads_min_reviews", 20))
    skip = recent_codes(items, days=int(cfg.get("threads_repeat_days", 3)))
    seen, out, errors = set(), [], []
    for label, gid in genres.items():
        try:
            got = fetch(cfg, gid)
        except A.RakutenError as e:
            errors.append(f"{label}: {e}")
            continue
        for p in got[:20]:
            if not p["is_affiliate"] or not p["price"] or p["code"] in seen or p["code"] in skip:
                continue
            if p["reviews"] < min_reviews:
                continue
            seen.add(p["code"])
            out.append(dict(p, genre=label))
    if not out and errors:
        raise A.RakutenError(" / ".join(errors))
    return mix_by_share(out)[:PROMPT_PRODUCTS], errors


def mix_by_share(products):
    """日用品を2つ、サブ（家電・ファッション）を1つ、の順にくり返して並べる（日用品が約6〜7割）。
    決めたジャンル以外の物は入れない。"""
    main = [p for p in products if genre_group(p.get("genre")) == MAIN_GROUP]
    sub = [p for p in products if genre_group(p.get("genre")) in SUB_GROUPS]
    mixed = []
    while main or sub:
        for _ in range(2):
            if main:
                mixed.append(main.pop(0))
        if sub:
            mixed.append(sub.pop(0))
    return mixed


# ---------- 2. AI に文を書いてもらう ----------
def build_prompt(products, day, cfg, fetched=None):
    fetched = fetched or T.now()
    lines = []
    for i, p in enumerate(products):
        row = {"no": i, "ジャンル": p.get("genre"), "順位": p.get("rank"), "商品名": p["name"][:120],
               "価格": p.get("price_text") or p["price"],
               "送料": "送料無料" if p.get("postage") == 0 else ("送料別" if p.get("postage") == 1 else "商品ページで確認"),
               "レビュー": f"{p['reviews']}件" if p.get('reviews') else "（情報なし。書かない）", "ショップ": p.get("shop"),
               "説明": ((p.get("catch") or "") + " " + (p.get("caption") or ""))[:300]}
        if p.get("past"):
            row["前に出したとき"] = p["past"]  # 出し直しの商品。前と違う切り口で書く
        lines.append(json.dumps(row, ensure_ascii=False))
    slots = "\n".join(f"- {t}：{kind}（{how}）" for t, kind, how in SLOTS)
    events = cfg.get("threads_events") or "（公式に確かめたイベント情報はありません。日程は書かないこと）"
    rp = T.DATA / "threads_research.md"
    research = ""
    if rp.exists():
        research = ("## 最近の SNS の傾向（伸びている人の型と話題。文はまねせず、型と話題だけ取り入れる）\n"
                    + rp.read_text(encoding="utf-8")[:2500])
    import threads_learn as L
    learned = L.plan_section()
    if learned:
        research = learned + "\n\n" + research
    return f"""あなたは Threads アカウント「ノボログ」（@noborog.life）の投稿を書く担当です。
{day:%Y年%m月%d日}（{"月火水木金土日"[day.weekday()]}）に出す投稿の候補を、1つの時間につき3案ずつ、合計15案作ってください。
同じ時間の3案は、下の「型」から全部ちがう型にする（ワンパターンにしない）。
のぼるさんが各時間から1案ずつ選びます。

## ノボログはどんな人か
- 48歳。子育てを終えた、バツイチのシングルファザー。楽天で今売れてる物・セール情報を毎日調べている。
- 目線：「子育てしていた時にこれが欲しかった」「これは楽」「今これが欲しい」。買う前に知りたい違いと選び方をまとめる。
- この人物像は出しすぎない（10案のうち1〜2案で軽くふれる程度）。子どもの名前・学校・顔・住む地域・元の配偶者のことは書かない。

## 時間ごとの役わり
{slots}

## 紹介に使える商品（楽天市場のランキングから今取った情報。これ以外の事実は書かない）
{chr(10).join(lines)}

## 楽天のイベント
{events}

{research}

## 型（毎日まぜて使う）
- 深掘りスレッド：1本目のつかみ → 返信でつないだ2〜4本目で、選び方・よくある失敗・比べるところを1本に1つずつ深く話す → 最後にリンク。
  "thread" に途中の本文を2〜3本入れる。1本ごとに「続きは下へ👇」のように次を読みたくなる終わり方にする。
- 比べるスレッド：「AとB、どっちがいい？」→ 2本目にA、3本目にBの向く人 → 最後にリンク（または問いで終える）。
- 写真つき紹介：1本目＋リンクの2本だけ（今までの型）。
- 保存用一覧：日付や確かめることを1行1項目で5〜7行。リンクなし。
- 2択の問い・共感：3行以内。返信を集める。
- 朝のランキングメモ：数字は1つまで、問いで終える。

## 守ること（とても大事）
- 紹介の案は、上の商品の no を "product" に入れる。紹介の時間（12:00・19:00）の4案は、全部ちがう商品にする。
- ジャンルは「日用品」（メイン。紹介の6〜7割）と「家電」「ファッション」（サブ。残り）だけ。ほかのジャンルの物は一切紹介しない。
- 商品は、料率（報酬の率）が高い／同じ商品を扱うお店が多い定番／悩みがはっきりしている／消耗品や買い替えがある物、を優先する。
- 「前に出したとき」に「楽天で売れた」とある商品は、実際に売れた定番。毎日1案以上は必ずこれを使い、時刻・型・切り口を毎回変える
  （例：深掘りスレッドで選び方／比べるスレッドで別の物と比べる／保存用一覧の1行／季節の場面を変える）。
- 「前に出したとき」がある商品は、前に反応があった売れ筋。新しい商品でなくてよいので、1〜2案はこれを使う。
  ただし前と同じ書き出し・同じ困りごとにはしない。別の場面（例：収納なら「年末の片づけ」→「冬服の入れ替え」）、
  別の確かめること、保存用の一覧の中の1つ、などの切り口に変える。前の数字は "why" に書く（文には書かない）。
- 紹介の案は、書く前に次の順で考える（"target" と "style" に書く）。
  1. 誰に向けるか：年齢層と暮らし（例：「40〜50代・子どもが巣立った夫婦」「30代・共働きで小さい子がいる」）。
  2. その人の悩み：その人がふだん困っていること（例：「朝、のどがカラカラ」「布団に入るまでが寒い」）。
  3. どう助かるか：上の商品の情報にある仕様だけを根拠に、その悩みがどう楽になるか（例：「上から水を入れられる→重いタンクを運ばない」）。
     効果・効能（健康・美容・病気に効く）はうたわない。仕様にない良さは作らない。
  4. どの型で書くか：上の「ほかの人から取り入れる型」「伸びている人の型」から、その人に一番届く型を1つ選ぶ。
  1本目は、この人に話しかけるつもりで、悩み → 確かめること の順に書く。2本目のひとことは「こういう人に向く」を入れる。
- 紹介の案は、伸びている人と同じ「2本のスレッド」にする。
  - 1本目（"hook"）：商品ページの写真が4〜8枚、横にならんで付く（プログラムが付ける）。
    写真が中身を見せるので、文は短く強く（60〜200文字）。最初の1行で手が止まる書き方にする。型の例：
    「【速報】〜」「【朗報】〜」／「〜な人へ。」「〜してる人、ちょっと待って」／「え、まだ〜してるの？」／
    「これ知らないと損する」系（ただし事実だけ）／子育て・家事のあるある → 解決のヒント。
    選ぶときに見るところを1〜3行の箇条書きで入れてもよい。URL・「PR」は書かない。
  - 2本目（"pr_comment"）：1〜3行のひとこと（向いている人、選ぶときの注意、レビューで多い声など）。
    プログラムが頭に「PR｜」、後ろに「▽楽天市場の商品ページ＋リンク＋取得日の価格」を付ける。URL・価格は書かない。
- のぼるさんは、ここの商品をまだ使っていない。「使ってみた」「買ってよかった」「うちでは」など、使った体験は書かない。
  かわりに「レビューで多い声」「選ぶときに見るところ」「こういう人に向く」を書く。
- 数字は上の情報にある物だけ。効果・効能をうたわない（食品・健康・美容は特に）。
- 「最安」「No.1」「ナンバーワン」「絶対」は使わない。あおらない。「買って」「クリックして」と頼まない。
- 1本は500文字以内（目安150〜250文字）。ていねいすぎない、話しかける口調。絵文字は1本に0〜2個。
- 子育てのころの話は「あの頃こういうのがあったら楽だった」くらいの一般的な言い方にとどめ、具体的な出来事を作らない。
- 価格・送料は書かない（リンクの投稿に自動で入る）。レビュー件数と平均は2本目なら書いてよい。
- 紹介しない案（07:00・15:00・21:00）は文だけ（写真なし）。"parts" に1本（続けたいときは2本まで）。
- 毎日のおなじみ（07:00）は、上の商品の順位・ジャンルを材料に書く（リンクなし）。
  ランキングは {fetched:%m/%d %H:%M} に取った物なので、「昨日の夜のランキング」のように書く（「今日の朝」とは書かない）。
- 予告では、明日の具体的な投稿内容を約束しない（明日の候補はまだ決まっていないため）。
- 他の人の投稿の文をまねしない。
- 1本目には、商品名・順位・レビュー件数を書かない。季節の困りごと → 選ぶときに確かめること（サイズ・容量など）までで止める
  （1本目にリンクや商品の宣伝がある投稿は、ほかの人のデータでも反応がほぼ0。リンクは必ず2本目）。
- 案ごとに "topic"（トピックタグ）を1つ付ける。日本語の短い話題名（例：暮らしの知恵／収納／冬じたく／楽天ブラックフライデー）。
  Threads 公式が「1投稿に1つ。その話題に興味のある人に届きやすくなる」とすすめている。商品名・ブランド名はタグにしない。
- 「いいねして」「コメントして」「フォローして」と頼まない（Threads は、反応をねだる投稿をおすすめに出さない）。
  答えやすい問いで終えるのはよい。

## 出す形
次の JSON だけを ```json で囲んで出してください。
```json
{{"candidates": [
  {{"slot": "07:00", "kind": "毎日のおなじみ", "title": "一覧に出す短い題", "product": null, "topic": "冬じたく",
    "why": "なぜおすすめか", "parts": ["1本目の本文"]}},
  {{"slot": "12:00", "kind": "紹介", "title": "紹介：〇〇", "product": 3, "why": "なぜおすすめか",
    "target": {{"誰に": "40〜50代・子どもが巣立った家", "悩み": "冬の朝、のどがカラカラ", "どう助かるか": "上から給水で重いタンクを運ばなくてよい（仕様より）"}},
    "style": "「〜な人へ。」で始める呼びかけ型",
    "hook": "1本目（写真つきのつかみ）", "thread": ["深掘りスレッドのときだけ：2本目", "3本目"], "pr_comment": "2本目のひとこと（例：フローリングならフェルトの方を選んでね）"}}
]}}
```
"why" は、のぼるさんが選ぶための説明（1〜2文）。上の情報（順位・レビュー件数・季節・イベント）と、
伸びている人の型（写真＋短いつかみ、質問で返信を集める、保存される表 など）のどれに当たるかを根拠に書く。
売れると言い切らない。
"""


def ask_claude(prompt, cfg):
    exe = shutil.which(cfg.get("claude_cmd") or "claude")
    if not exe:
        raise EngineError("Claude Code（claude）が見つかりません")
    cmd = [exe, "-p", "--output-format", "json", "--max-turns", "3"]
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    proc = subprocess.run(cmd, input=prompt, text=True, encoding="utf-8", capture_output=True,
                          cwd=str(HERE / "data"), timeout=15 * 60)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise EngineError(f"Claude Code の返事を読めません: {(proc.stderr or proc.stdout)[:300]}") from None
    if out.get("is_error"):
        raise EngineError(f"Claude Code がエラー: {str(out.get('result'))[:300]}")
    return extract_json(str(out.get("result") or ""))


# ---------- 3. リンクを付けて、候補にする ----------
def link_part(p, day_fetched, comment=""):
    """2本目：PR＋ひとこと＋楽天市場のリンク＋取得日の価格（人気の人と同じ並び）。"""
    postage = "・送料無料" if p["postage"] == 0 else ""
    comment = (comment or "").strip()
    if T.LINK_RE.search(comment):
        comment = ""
    head = f"PR｜{comment}" if comment else "PR｜楽天市場で見つけた物"
    if p.get("fetched_at"):  # 出し直しの商品は、価格を取った日で書く
        day_fetched = T.parse_time(p["fetched_at"]) if isinstance(p["fetched_at"], str) else p["fetched_at"]
    price = p.get("price_text") or f"{p['price']:,}円"
    return (f"{head}\n\n▽楽天市場の商品ページ\n{p['url']}\n"
            f"※{day_fetched.month}月{day_fetched.day}日時点 {price}{postage}")


def to_items(answer, products, day, fetched_at):
    out = []
    used = set()
    for n, c in enumerate(answer.get("candidates", []), 1):
        parts = [s.strip() for s in c.get("parts", []) if isinstance(s, str) and s.strip()][:5]
        middle = [s.strip() for s in c.get("thread", []) if isinstance(s, str) and s.strip()][:3]
        if c.get("hook"):
            parts = [str(c["hook"]).strip()]
        if not parts:
            continue
        it = {"id": f"{day:%m%d}-{n:02d}", "title": c.get("title") or parts[0][:20], "why": c.get("why", ""),
              "kind": c.get("kind", ""), "slot": c.get("slot", ""), "status": "候補",
              "made_at": T.now().isoformat(), "for_date": f"{day:%Y-%m-%d}", "parts": parts}
        if c.get("topic"):
            it["topic"] = T.clean_topic(c["topic"])
        if isinstance(c.get("target"), dict):
            it["target"] = {k: str(v)[:80] for k, v in c["target"].items() if v}
        if c.get("style"):
            it["style"] = str(c["style"])[:80]
        idx = c.get("product")
        if isinstance(idx, int) and 0 <= idx < len(products):
            p = products[idx]
            it["parts"] = parts[:1] + middle + [link_part(p, fetched_at, c.get("pr_comment") or c.get("link_note", ""))]
            it["product"] = {k: p.get(k) for k in ("code", "name", "price", "shop", "item_url", "url",
                                                    "image", "reviews", "rating", "genre", "rank")}
            if p["code"] in used:
                it["problems_extra"] = ["ほかの案と同じ商品です"]
            used.add(p["code"])
        elif c.get("kind") == "紹介":
            continue  # 商品のない紹介は使えない
        it["problems"] = it.pop("problems_extra", [])
        out.append(it)
    return out


def review_md(items, day, errors):
    lines = [f"# ノボログ 投稿候補（{day:%m月%d日}分）", "",
             "各時間から1つずつ選んで、番号を送ってください（例：「01, 03, 06, 07, 10」）。",
             "文を直したい所があれば、そのまま書いてください。", ""]
    if errors:
        lines += ["> 楽天から取れなかったジャンル：" + "、".join(e.split(":")[0] for e in errors), ""]
    for slot, kind, _ in SLOTS:
        group = [it for it in items if it.get("slot") == slot]
        if not group:
            continue
        lines += [f"## {slot}　{kind}", ""]
        for it in group:
            lines.append(f"### {it['id'][-2:]}．{it['title']}")
            if it.get("product"):
                p = it["product"]
                lines.append(f"商品：{p['name'][:60]}（{p['price']:,}円・レビュー{p['reviews']}件・{p['genre']} {p['rank']}位）")
                lines.append(f"商品ページ：{p['item_url']}")
            if it.get("target"):
                lines.append("ねらい：" + "／".join(f"{k}：{v}" for k, v in it["target"].items()))
            if it.get("style"):
                lines.append(f"まねた型：{it['style']}")
            if it["problems"]:
                lines.append("**⚠ " + " / ".join(it["problems"]) + "**")
            lines.append("")
            for i, part in enumerate(it["parts"], 1):
                lines.append(f"**{i}本目**")
                lines.append("")
                lines.append("> " + part.replace("\n", "\n> "))
                lines.append("")
    return "\n".join(lines)


def make(day, cfg, items, fetch=A.ranking, ask=ask_claude):
    products, errors = gather(cfg, items, fetch)
    past = past_products(items, cfg)
    codes = {p["code"] for p in past}
    products = past + [p for p in products if p["code"] not in codes]
    if len(products) < 4:
        raise A.RakutenError(f"紹介できる商品が足りません（{len(products)}件）")
    answer = ask(build_prompt(products, day, cfg), cfg)
    new = to_items(answer, products, day, T.now())
    add_images(new, cfg)
    try:
        add_card_specs(new, cfg, ask)
        add_scenes(new, cfg, ask)
    except EngineError as e:  # カードの文が作れなくても、カードは1本目の文から作る
        T.log(f"カードの文を作れませんでした（1本目の文から作ります）: {e}")
    try:
        import threads_media
        # 動画は「企画書→キャラクターシート→背景シート→絵コンテ→動画」の手順を踏んでから作るので、
        # 毎晩の自動では作らない（紹介は商品写真のカルーセルで出す）。
        threads_media.make_for(new, video=bool(cfg.get("threads_auto_video", False)))
    except Exception as e:
        T.log(f"画像・動画を作れませんでした: {e}")
    for it in new:
        it["problems"] = T.check_rules(it["parts"], it.get("images")) + it["problems"]
    return new, errors


CARD_PROMPT = """Threads アカウント「ノボログ」の投稿に付ける、1枚の画像カード（縦長・黒地に白と黄色の文字）の中身を作ってください。
カードは投稿の文の「見出しと要点」だけを大きく見せる物です。文にない事実は足さないこと。

style は次のどれか：
- "ranking"：順位の一覧。points は「順位|短い商品名（20文字以内）」の形（例："3位|非常用の袋トイレ"）
- "question"：質問。title に質問（30文字以内）、points に選択肢（各18文字以内・番号は付けない）
- "list"：保存用のまとめ。points は「■見出し」と「→説明（30文字以内）」を交互に
- "note"：日記・ひとこと。title に一番伝えたい一文、points に短い文を2〜3個

label は左上の黄色い札の文字（例：今日の楽天メモ／教えて／保存用／ノボログ）。title は全角30文字以内で、あいさつ（おはようございます等）は入れない。

投稿：
{posts}

次の JSON だけを ```json で囲んで出してください。
```json
{{"cards": [{{"id": "投稿のid", "style": "ranking", "label": "今日の楽天メモ", "title": "…", "points": ["…"]}}]}}
```
"""


SCENE_PROMPT = """Threads の投稿に付ける「AI で作る写真・短い動画」の場面を、投稿ごとに1つ考えてください。
パソコンの画像 AI（FLUX）と動画 AI（Wan 2.2）に渡すので、英語で、1〜2文で書きます。

決まり：
- 投稿の話題に合う「日本の暮らしの一場面」。季節は今（11月・冬のはじめ）。
- 商品そのものは描かない（実物と違う絵で誤解させないため）。困っている様子や、使う場所・時間の雰囲気を描く。
  例：寒い寝室で布団にくるまる手元／湯気の立つ台所／積み上がった洗濯物／セール前にスマホを見るソファの夜
- 人は出してよいが、顔ははっきり写さない（手元・後ろ姿・小さく）。実在の人物・有名人・キャラクターは出さない。
- 文字・看板・ロゴ・ブランドは入れない。
- 動画になるので、ゆっくりした小さな動き（湯気・カーテン・手の動き）がある場面がよい。

投稿：
{posts}

次の JSON だけを ```json で囲んで出してください。
```json
{{"scenes": [{{"id": "投稿のid", "scene": "English prompt"}}]}}
```
"""


def add_scenes(items, cfg, ask=None):
    """各投稿の AI 画像・動画の場面（英語の指示文）を作る。"""
    ask = ask or ask_claude
    targets = [it for it in items if not it.get("scene")]
    if not targets:
        return
    posts = "\n\n".join(f"id: {it['id']}（{it.get('kind', '')}）\n{it['parts'][0]}" for it in targets)
    answer = ask(SCENE_PROMPT.format(posts=posts), cfg)
    by_id = {c.get("id"): c.get("scene") for c in answer.get("scenes", []) if isinstance(c, dict)}
    for it in targets:
        if by_id.get(it["id"]):
            it["scene"] = str(by_id[it["id"]])[:400]


def add_card_specs(items, cfg, ask=None):
    """紹介しない投稿のカードの中身（見出し・要点）を、AI にまとめてもらう。"""
    ask = ask or ask_claude
    targets = [it for it in items if not it.get("product")]
    if not targets:
        return
    posts = "\n\n".join(f"id: {it['id']}（{it.get('kind', '')}）\n{it['parts'][0]}" for it in targets)
    answer = ask(CARD_PROMPT.format(posts=posts), cfg)
    by_id = {c.get("id"): c for c in answer.get("cards", []) if isinstance(c, dict)}
    for it in targets:
        c = by_id.get(it["id"])
        if c and c.get("title") and c.get("style") in ("ranking", "question", "list", "note"):
            it["card_spec"] = {k: c.get(k) for k in ("style", "label", "title", "points")}


def add_images(items, cfg, get=None):
    """紹介の1本目に、商品ページの写真を付ける（加工しない。取れなければ楽天の一覧の写真）。"""
    if get is None:
        import threads_preview
        get = threads_preview.product_images
    n = int(cfg.get("threads_images", 6))
    for it in items:
        p = it.get("product")
        if not p:
            continue
        try:
            imgs = get(p["item_url"], n) if p.get("item_url") else []
        except Exception:
            imgs = []
        if not imgs and p.get("image"):
            imgs = [re.sub(r"_ex=\d+x\d+", "_ex=1000x1000", p["image"])]
        if imgs:
            it["images"] = imgs


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="ノボログの Threads 投稿候補を作る")
    ap.add_argument("--date")
    ap.add_argument("--products-only", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_full_cfg()
    day = datetime.fromisoformat(args.date) if args.date else (T.now() + timedelta(days=1))
    items = T.load_queue()
    try:
        if args.products_only:
            products, errors = gather(cfg, items)
            for i, p in enumerate(products):
                print(f"{i:2d} [{p['genre']} {p['rank']}位] {p['price']:,}円 レビュー{p['reviews']} {p['name'][:40]}")
            for e in errors:
                print("取れなかった:", e)
            return 0
        # その日のために作った候補（番号が MMDD- で始まる）があるかで見る。前の日の分を回しただけなら作る
        if any(it.get("id", "").startswith(f"{day:%m%d}-") for it in items):
            T.log(f"{day:%m/%d} 分の候補はもうあります（作り直すときは先に取り消す）")
            return 0
        new, errors = make(day, cfg, items)
    except (A.RakutenError, EngineError, OSError, subprocess.TimeoutExpired) as e:
        T.log(f"候補づくりが止まりました: {e}")
        return 1
    items = T.load_queue()  # 作っている間に変わっていてもいいように読み直す
    items += [it for it in new if it["id"] not in {x["id"] for x in items}]
    T.save_queue(items)
    md = T.DATA / f"threads_review_{day:%m%d}.md"
    md.write_text(review_md(new, day, errors), encoding="utf-8")
    try:
        import threads_preview
        html_path = T.DATA / f"threads_preview_{day:%m%d}.html"
        threads_preview.build(new, html_path, f"ノボログ 投稿プレビュー（{day.month}月{day.day}日分）")
    except Exception as e:  # 見た目のページが作れなくても候補は残す
        T.log(f"プレビューのページを作れませんでした: {e}")
    T.log(f"{day:%m/%d} 分の候補を{len(new)}件作りました（{md.name} / threads_preview_{day:%m%d}.html）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
