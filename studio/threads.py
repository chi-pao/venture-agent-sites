# -*- coding: utf-8 -*-
"""ノボログの Threads 自動投稿。

流れ:
  候補（AI が作る）→ のぼるさんが選ぶ → 承認済み（時間つき）→ 時間になったら自動で投稿

守ること:
  - 「承認済み」の物しか投稿しない。
  - 1日の投稿は config の threads_max_per_day 本まで（決まりは5本）。
  - リンクを入れる投稿は、「PR」と「楽天市場」の両方を書く（楽天のガイドライン）。
  - 1本目にはリンクを入れない（表示が伸びにくいため）。
  - 予定の時間から3時間以上すぎた物は、出さずに「期限切れ」にする（パソコンが寝ていた時など）。

合いことば（アクセストークン）は secrets/threads_token.txt に置く。GitHub には上がらない。

使い方:
  py threads.py check            つながりの確認（投稿はしない）
  py threads.py test             投稿の下書きを作れるかだけ確かめる（公開はしない）
  py threads.py list [--all]     予定の一覧
  py threads.py add FILE.json    候補をまとめて入れる
  py threads.py approve ID HH:MM [--date YYYY-MM-DD]   承認して時間を決める
  py threads.py pick ID [ID ...]  選んだ候補を、候補に書いてある日・時間でまとめて承認する
  py threads.py cancel ID        取り消す
  py threads.py run [--dry]      時間になった物を投稿する（タスクスケジューラーが10分ごとに呼ぶ）
  py threads.py refresh          合いことばを延長する（run の中でも7日ごとに自動で行う）
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _add_user_site():
    """Windows の予約（タスク スケジューラ）からは、Claude アプリの中で本人用に入れた部品が見えない。
    部品（Pillow・playwright）は C:/AI/noborog-pylib にも入れてあるので、そこを読む。"""
    import os
    import site
    for p in (site.getusersitepackages(), "C:/AI/noborog-pylib"):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_add_user_site()

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SECRETS = HERE / "secrets"
QUEUE = DATA / "threads_queue.json"
LOG = DATA / "threads_log.txt"
TOKEN_FILE = SECRETS / "threads_token.txt"
STATE_FILE = SECRETS / "threads_state.json"
API = "https://graph.threads.net/v1.0"
JST = timezone(timedelta(hours=9))

DEFAULTS = {"threads_max_per_day": 5, "threads_same_product_gap_hours": 4, "threads_late_limit_hours": 3, "threads_publish_wait_seconds": 8}
LINK_RE = re.compile(r"(a\.r10\.to|rakuten\.co\.jp|hb\.afl\.rakuten|amazon\.co\.jp|amzn\.to|https?://)", re.I)
AMAZON_RE = re.compile(r"(amazon\.co\.jp|amzn\.to)", re.I)
ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/|^)([A-Z0-9]{10})(?:[/?#]|$)")
BANNED = ["最安", "No.1", "No1", "ナンバーワン", "絶対"]
STATUSES = ["候補", "承認済み", "投稿済み", "失敗", "期限切れ", "取り消し"]


class ThreadsError(RuntimeError):
    pass


# ---------- 小物 ----------
def now():
    return datetime.now(JST)


def log(msg):
    DATA.mkdir(parents=True, exist_ok=True)
    line = f"{now():%Y-%m-%d %H:%M:%S} {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def load_cfg():
    cfg = dict(DEFAULTS)
    p = HERE / "config.json"
    if p.exists():
        try:
            cfg.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k.startswith("threads_")})
        except ValueError:
            pass
    return cfg


def load_queue():
    if not QUEUE.exists():
        return []
    return json.loads(QUEUE.read_text(encoding="utf-8"))


def save_queue(items):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(QUEUE)


def parse_time(s):
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=JST)


# ---------- 決まりの確認 ----------
def check_rules(parts, images=None):
    """守れていない所の一覧を返す（空なら OK）。images は1本目に付ける画像の URL。"""
    problems = []
    images = images or []
    if len(images) > 20:
        problems.append(f"画像は20枚までです（{len(images)}枚）")
    if any(not str(u).startswith("https://") for u in images):
        problems.append("画像の URL が https で始まっていません")
    if not parts or not all(isinstance(p, str) and p.strip() for p in parts):
        return ["本文が空です"]
    for i, text in enumerate(parts, 1):
        if len(text) > 500:
            problems.append(f"{i}本目が500文字を超えています（{len(text)}文字）")
        if "（短縮URL）" in text or "(短縮URL)" in text:
            problems.append(f"{i}本目：短縮URLがまだ入っていません")
        for w in BANNED:
            if w in text:
                problems.append(f"{i}本目に使わない言葉「{w}」があります")
        if LINK_RE.search(text):
            if i == 1:
                problems.append("1本目にリンクがあります（2本目以降に入れる）")
            if "PR" not in text[:20]:
                problems.append(f"{i}本目：リンクがあるのに、最初に「PR」がありません")
            if AMAZON_RE.search(text) and "Amazon" not in text:
                problems.append(f"{i}本目：リンク先が Amazon だとわかる言葉がありません")
            if re.search(r"a\.r10\.to|rakuten", text, re.I) and "楽天市場" not in text:
                problems.append(f"{i}本目：リンク先が楽天市場だとわかる言葉がありません")
    return problems


# ---------- 合いことば ----------
def read_token():
    if not TOKEN_FILE.exists():
        raise ThreadsError(f"合いことばのファイルがありません: {TOKEN_FILE}")
    tok = TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
    if not tok:
        raise ThreadsError("合いことばのファイルが空です")
    return tok


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    st = {}
    if TOKEN_FILE.exists():
        st["token_saved_at"] = datetime.fromtimestamp(TOKEN_FILE.stat().st_mtime, JST).isoformat()
    return st


def save_state(st):
    SECRETS.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- Threads API ----------
def _call(method, path, params, token, base=API):
    params = dict(params, access_token=token)
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{base}/{path}?{data.decode()}")
    else:
        req = urllib.request.Request(f"{base}/{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        body = body.replace(token, "***")
        raise ThreadsError(f"Threads が {e.code} を返しました: {body}") from None
    except urllib.error.URLError as e:
        raise ThreadsError(f"つながりませんでした: {e.reason}") from None


class Client:
    def __init__(self, token, call=_call, sleep=time.sleep, wait=8):
        self.token, self.call, self.sleep, self.wait = token, call, sleep, wait
        self._uid = None

    @property
    def uid(self):
        if not self._uid:
            st = load_state()
            self._uid = st.get("user_id") or self.me()["id"]
        return self._uid

    def me(self):
        return self.call("GET", "me", {"fields": "id,username"}, self.token)

    def quota(self):
        r = self.call("GET", f"{self.uid}/threads_publishing_limit", {"fields": "quota_usage,config"}, self.token)
        return r["data"][0]

    @staticmethod
    def _media_params(m, carousel=False):
        url = m if isinstance(m, str) else m["url"]
        video = (not isinstance(m, str)) and m.get("type") == "video"
        p = {"media_type": "VIDEO", "video_url": url} if video else {"media_type": "IMAGE", "image_url": url}
        if carousel:
            p["is_carousel_item"] = "true"
        return p

    def create(self, text, reply_to=None, images=None, topic=None):
        """文だけ・写真/動画1つ・2つ以上（カルーセル）の投稿の下書きを作る。
        images は URL（写真）か {"type": "video"|"image", "url": ...} のリスト。
        topic はトピックタグ（1投稿に1つ。Threads 公式が「その話題に興味のある人に届きやすくなる」とすすめている）。"""
        media = list(images or [])
        if len(media) == 1:
            p = dict(self._media_params(media[0]), text=text)
        elif media:
            kids = [self.call("POST", f"{self.uid}/threads", self._media_params(m, True), self.token)["id"]
                    for m in media]
            for kid in kids:
                self.wait_ready(kid)
            p = {"media_type": "CAROUSEL", "children": ",".join(kids), "text": text}
        else:
            p = {"media_type": "TEXT", "text": text}
        if reply_to:
            p["reply_to_id"] = reply_to
        tag = clean_topic(topic)
        if tag:
            p["topic_tag"] = tag
        cid = self.call("POST", f"{self.uid}/threads", p, self.token)["id"]
        if media:
            self.wait_ready(cid)
        return cid

    def wait_ready(self, cid, tries=60):
        """写真・動画の下書きは Threads 側の準備が終わるまで待つ（最大で約3分）。"""
        for _ in range(tries):
            st = self.call("GET", cid, {"fields": "status,error_message"}, self.token)
            if st.get("status") == "FINISHED":
                return
            if st.get("status") in ("ERROR", "EXPIRED"):
                raise ThreadsError(f"写真・動画の準備に失敗しました: {st.get('error_message') or st.get('status')}")
            self.sleep(3)
        raise ThreadsError("写真・動画の準備が終わりませんでした")

    def publish(self, creation_id):
        self.sleep(self.wait)
        return self.call("POST", f"{self.uid}/threads_publish", {"creation_id": creation_id}, self.token)["id"]

    def refresh(self):
        r = self.call("GET", "refresh_access_token", {"grant_type": "th_refresh_token"}, self.token,
                      base="https://graph.threads.net")
        return r["access_token"], r.get("expires_in")


def maybe_refresh(client, force=False):
    st = load_state()
    saved = parse_time(st["token_saved_at"]) if st.get("token_saved_at") else now()
    age = now() - saved
    if not force and age < timedelta(days=7):
        return False
    if age < timedelta(hours=24):
        log("合いことばの延長：作ってから24時間たっていないので、まだできません")
        return False
    new_token, expires = client.refresh()
    TOKEN_FILE.write_text(new_token, encoding="utf-8")
    client.token = new_token
    st["token_saved_at"] = now().isoformat()
    if expires:
        st["token_expires_at"] = (now() + timedelta(seconds=int(expires))).isoformat()
    save_state(st)
    log(f"合いことばを延長しました（あと約{int(expires or 0) // 86400}日）")
    return True


# ---------- 投稿 ----------
def posted_today(items, day):
    return sum(1 for it in items if it["status"] == "投稿済み" and it.get("posted_at", "")[:10] == day)


def attachments(it):
    """1本目に付ける物：動画（あれば先頭）→ 写真カード → 楽天の商品写真。最大20個。"""
    media = []
    for key, kind in (("video", "video"), ("card", "image")):
        m = it.get(key)
        if m:
            if not m.get("url"):
                raise ThreadsError(f"{it['id']} の{'動画' if kind == 'video' else '写真カード'}をまだ公開場所に置いていません")
            media.append({"type": kind, "url": m["url"]})
    media += list(it.get("images") or [])
    return media[:20]


def clean_topic(topic):
    """トピックタグの形を整える（# はいらない。「.」「&」は使えない。50文字まで）。"""
    tag = re.sub(r"[.&#＃]", "", str(topic or "")).strip()
    return tag[:50]


def post_item(client, it):
    """1本目から順に出す。途中で失敗したら、次の回はその続きから出す。"""
    ids = it.setdefault("posted_ids", [])
    for i in range(len(ids), len(it["parts"])):
        reply_to = ids[-1] if ids else None
        first = i == 0
        cid = client.create(it["parts"][i], reply_to, attachments(it) if first else None,
                            it.get("topic") if first else None)
        ids.append(client.publish(cid))
    it["status"] = "投稿済み"
    it["posted_at"] = now().isoformat()
    it.pop("error", None)


def run(client, items, cfg, dry=False, at=None):
    at = at or now()
    day = at.strftime("%Y-%m-%d")
    late = timedelta(hours=cfg["threads_late_limit_hours"])
    done = []
    due = sorted((it for it in items if it["status"] in ("承認済み", "失敗") and it.get("time")),
                 key=lambda it: it["time"])
    for it in due:
        t = parse_time(it["time"])
        if t > at:
            continue
        if at - t > late and not it.get("posted_ids"):
            it["status"] = "期限切れ"
            log(f"{it['id']} は予定（{t:%m/%d %H:%M}）から時間がたちすぎたので出しませんでした")
            continue
        if it["status"] == "失敗" and it.get("tries", 0) >= 3:
            continue
        problems = check_rules(it["parts"], it.get("images"))
        if problems:
            it["status"] = "失敗"
            it["tries"] = 3  # 直さない限り何度やっても同じなので、もう試さない
            it["error"] = " / ".join(problems)
            log(f"{it['id']} は決まりに合わないので出しませんでした: {it['error']}")
            continue
        if posted_today(items, day) >= cfg["threads_max_per_day"]:
            log(f"{it['id']}：今日はもう{cfg['threads_max_per_day']}本出したので、出しませんでした")
            continue
        if dry:
            log(f"[練習] {it['id']} を出すところでした：{it['parts'][0][:30]}…")
            continue
        try:
            post_item(client, it)
            log(f"{it['id']} を投稿しました（{len(it['parts'])}本）：{it['parts'][0][:30]}…")
            done.append(it["id"])
        except ThreadsError as e:
            it["status"] = "失敗"
            it["tries"] = it.get("tries", 0) + 1
            it["error"] = str(e)
            log(f"{it['id']} の投稿に失敗しました（{it['tries']}回目）: {e}")
    return done


# ---------- コマンド ----------
def find(items, item_id):
    for it in items:
        if it["id"] == item_id:
            return it
    raise ThreadsError(f"{item_id} が見つかりません")


def cmd_add(args):
    items = load_queue()
    new = json.loads(Path(args.file).read_text(encoding="utf-8"))
    have = {it["id"] for it in items}
    added = 0
    for it in new:
        if it["id"] in have:
            continue
        it.setdefault("status", "候補")
        it["problems"] = check_rules(it["parts"], it.get("images"))
        items.append(it)
        added += 1
    save_queue(items)
    print(f"{added}件の候補を入れました")


PACE_SLOTS = ["10:00", "14:00", "21:00"]  # 人気の投稿者の投稿が多い時間（朝10時台・昼14時台・夜21時台）


def spread_time(items, it, t, gap_hours=4, max_per_day=None, min_gap_minutes=90, slots=None):
    """人気の投稿者のペース（1日2〜5回・朝/昼/夕/夜）に合わせて、予定を空いている時間へずらす。
    - 同じ商品は gap_hours あける
    - ほかの投稿と min_gap_minutes 以上あける
    - 1日 max_per_day 回まで（あふれたら次の日の空き枠へ）"""
    code = (it.get("product") or {}).get("code")
    slots = slots or PACE_SLOTS
    taken = [(parse_time(x["time"]), (x.get("product") or {}).get("code")) for x in items
             if x is not it and x.get("status") in ("承認済み", "投稿済み") and x.get("time")]

    def ok(c):
        if any(abs(c - o) < timedelta(minutes=min_gap_minutes) for o, _ in taken):
            return False
        if code and gap_hours and any(oc == code and abs(c - o) < timedelta(hours=gap_hours) for o, oc in taken):
            return False
        if max_per_day and sum(1 for o, _ in taken if o.date() == c.date()) >= max_per_day:
            return False
        return True

    if ok(t) and f"{t:%H:%M}" in slots:
        return t
    for day in range(0, 30):  # 同じ日の後ろの枠 → 次の日の枠
        d = (t + timedelta(days=day)).date()
        for hm in slots:
            c = parse_time(f"{d:%Y-%m-%d}T{hm}")
            if c >= t and ok(c):
                return c
    return t


def cmd_approve(args):
    items = load_queue()
    it = find(items, args.id)
    problems = check_rules(it["parts"], it.get("images"))
    if problems:
        raise ThreadsError("決まりに合わない所があります: " + " / ".join(problems))
    date = args.date or now().strftime("%Y-%m-%d")
    t = parse_time(f"{date}T{args.time}")
    cfg = load_cfg()
    moved = spread_time(items, it, t, cfg.get("threads_same_product_gap_hours", 4), cfg.get("threads_max_per_day"), slots=cfg.get("threads_pace_slots"))
    if moved != t:
        log(f"{it['id']}：ほかの投稿や同じ商品と近いので、{t:%m/%d %H:%M} → {moved:%m/%d %H:%M} にずらしました")
        t = moved
    it["time"] = t.isoformat()
    it["status"] = "承認済み"
    it.pop("error", None)
    it["tries"] = 0
    save_queue(items)
    log(f"{it['id']} を承認しました（{t:%m/%d %H:%M} に投稿）")


def cmd_pick(args):
    """候補に入っている for_date と slot の時間で承認する。決まりに合わない物があれば何もしない。"""
    items = load_queue()
    chosen = [find(items, i) for i in args.ids]
    bad = []
    for it in chosen:
        problems = check_rules(it["parts"], it.get("images"))
        if problems:
            bad.append(f"{it['id']}: " + " / ".join(problems))
        elif not (it.get("for_date") and it.get("slot")):
            bad.append(f"{it['id']}: 日にちか時間がありません（approve で時間を決めてください）")
        elif parse_time(f"{it['for_date']}T{it['slot']}") < now() - timedelta(minutes=5):
            bad.append(f"{it['id']}: 予定の時間（{it['for_date']} {it['slot']}）をもう過ぎています")
    if bad:
        raise ThreadsError("承認しませんでした：" + " ／ ".join(bad))
    cfg = load_cfg()
    for it in chosen:
        t = parse_time(f"{it['for_date']}T{it['slot']}")
        moved = spread_time(items, it, t, cfg.get("threads_same_product_gap_hours", 4), cfg.get("threads_max_per_day"), slots=cfg.get("threads_pace_slots"))
        if moved != t:
            log(f"{it['id']}：ほかの投稿や同じ商品と近いので、{t:%m/%d %H:%M} → {moved:%m/%d %H:%M} にずらしました")
            t = moved
        it.update(time=t.isoformat(), status="承認済み", tries=0)
        it.pop("error", None)
        log(f"{it['id']} を承認しました（{t:%m/%d %H:%M} に投稿）")
    save_queue(items)
    ensure_media(items)
    save_queue(items)


def ensure_media(items):
    """承認済みの投稿の動画・写真カードが、まだ公開場所にないなら置く。"""
    need = [it for it in items if it["status"] in ("承認済み", "失敗")
            and any((it.get(k) or {}).get("local") and not (it.get(k) or {}).get("url") for k in ("video", "card"))]
    if not need:
        return
    try:
        import threads_media
        cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8")) if (HERE / "config.json").exists() else {}
        done = threads_media.upload(items, cfg)
        log(f"動画・写真カードを{len(done)}件、公開場所に置きました")
    except Exception as e:
        log(f"動画・写真カードを公開場所に置けませんでした（次の回にもう一度）: {e}")


def amazon_link(asin_or_url, tag):
    """ASIN か Amazon の商品ページの URL から、アソシエイトのリンク（tag 付き）を作る。"""
    text = str(asin_or_url or "").strip()
    m = ASIN_RE.search(text)
    if not m:
        raise ThreadsError(f"Amazon の商品番号（ASIN・10けた）が見つかりません: {text[:80]}")
    if not tag:
        raise ThreadsError("config.json に threads_amazon_tag（例: noborog-22）がありません")
    return f"https://www.amazon.co.jp/dp/{m.group(1)}?tag={tag}"


AMAZON_BLOCK = "\n\n▽Amazon の商品ページ\n{url}\n※Amazon の価格はリンク先で確かめてね"


def add_amazon(it, asin_or_url, tag):
    """紹介の2本目の楽天リンクの後ろに、Amazon のリンクを足す（同じ商品が Amazon にもある時だけ）。"""
    if len(it.get("parts", [])) < 2:
        raise ThreadsError(f"{it['id']} は2本目（リンクの投稿）がありません")
    url = amazon_link(asin_or_url, tag)
    second = re.sub(r"\n\n▽Amazon の商品ページ\n\S+\n※[^\n]*", "", it["parts"][1])
    it["parts"][1] = second + AMAZON_BLOCK.format(url=url)
    it.setdefault("product", {})["amazon_url"] = url
    return it


def cmd_amazon(args):
    items = load_queue()
    it = find(items, args.id)
    if it["status"] == "投稿済み":
        raise ThreadsError("もう投稿済みです")
    add_amazon(it, args.asin, load_cfg().get("threads_amazon_tag"))
    problems = check_rules(it["parts"], it.get("images"))
    if problems:
        raise ThreadsError(" / ".join(problems))
    save_queue(items)
    log(f"{it['id']} の2本目に Amazon のリンクを足しました（{it['product']['amazon_url']}）")


def cmd_cancel(args):
    items = load_queue()
    it = find(items, args.id)
    if it["status"] == "投稿済み":
        raise ThreadsError("もう投稿済みです。消すときは Threads の画面から消してください")
    it["status"] = "取り消し"
    save_queue(items)
    log(f"{it['id']} を取り消しました")


def cmd_list(args):
    items = load_queue()
    for it in sorted(items, key=lambda x: (x.get("time") or "9", x["id"])):
        if not args.all and it["status"] in ("投稿済み", "取り消し", "期限切れ"):
            continue
        when = parse_time(it["time"]).strftime("%m/%d %H:%M") if it.get("time") else "--"
        print(f"{it['id']:<10} {it['status']:<5} {when}  {it.get('title', it['parts'][0][:25])}")


def cmd_check(args):
    c = Client(read_token())
    me = c.me()
    st = load_state()
    st["user_id"] = me["id"]
    save_state(st)
    q = c.quota()
    print(f"つながっています：@{me['username']}（今日の投稿 {q['quota_usage']} / 上限 {q['config']['quota_total']}）")


def cmd_test(args):
    c = Client(read_token())
    cid = c.create("（テスト）これは公開しない下書きです")
    print(f"下書きを作れました（公開はしていません）: {cid}")


def cmd_run(args):
    cfg = load_cfg()
    items = load_queue()
    if not any(it["status"] in ("承認済み", "失敗") for it in items):
        return
    c = Client(read_token(), wait=cfg["threads_publish_wait_seconds"])
    try:
        maybe_refresh(c)
    except ThreadsError as e:
        log(f"合いことばの延長に失敗しました: {e}")
    if not args.dry:
        ensure_media(items)
    run(c, items, cfg, dry=args.dry)
    save_queue(items)


def cmd_refresh(args):
    maybe_refresh(Client(read_token()), force=True)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="ノボログの Threads 自動投稿")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("test")
    sub.add_parser("refresh")
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("add"); p.add_argument("file")
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("time"); p.add_argument("--date")
    p = sub.add_parser("pick"); p.add_argument("ids", nargs="+")
    p = sub.add_parser("cancel"); p.add_argument("id")
    p = sub.add_parser("amazon"); p.add_argument("id"); p.add_argument("asin")
    p = sub.add_parser("run"); p.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)
    try:
        {"check": cmd_check, "test": cmd_test, "refresh": cmd_refresh, "list": cmd_list, "add": cmd_add,
         "approve": cmd_approve, "pick": cmd_pick, "cancel": cmd_cancel, "amazon": cmd_amazon, "run": cmd_run}[args.cmd](args)
    except ThreadsError as e:
        log(f"止まりました: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
