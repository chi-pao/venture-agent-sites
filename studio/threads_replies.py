# -*- coding: utf-8 -*-
"""自分の投稿にもらった返信に、返事の下書きを作って、OK が出た物だけ出す。

流れ:
  fetch  ：投稿済みの投稿（14日以内）の会話を見て、まだ答えていない、ほかの人の返信を集める（R1, R2… の番号）
  draft  ：毎朝の候補づくり（Claude）が、返事の下書きを書く
  見本ページに「返信の下書き」として出る → のぼるさんが OK
  ok     ：予約（kind=返信、相手の返信につなげる）に入れて、すぐ出す。クラウドに切りかえ後は sync で送る
決まり：勝手には出さない。売りこみ・リンク・使った体験は書かない。短く、相手の言葉を受けて返す。
"""
import json
from datetime import timedelta

import threads as T

FILE = T.DATA / "threads_replies.json"


def load():
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else []


def save(rows):
    T.DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def find(rows, no):
    no = str(no).upper()
    no = no if no.startswith("R") else "R" + no
    for r in rows:
        if r["no"] == no:
            return r
    raise T.ThreadsError(f"{no} という返信はありません")


def new_replies(conv, me, known):
    """会話の中から、自分以外の人の返信で、自分がまだ答えていない物を返す。"""
    answered = {(x.get("replied_to") or {}).get("id") for x in conv if x.get("username") == me}
    return [x for x in conv if x.get("username") and x.get("username") != me
            and x["id"] not in answered and x["id"] not in known]


def fetch(client, items, rows, days=14, at=None):
    at = at or T.now()
    me = client.me().get("username")
    known = {r["id"] for r in rows}
    nums = [int(r["no"][1:]) for r in rows] or [0]
    added = []
    for it in items:
        if it.get("status") != "投稿済み" or not it.get("posted_ids") or it.get("kind") == "返信":
            continue
        if not it.get("posted_at") or at - T.parse_time(it["posted_at"]) > timedelta(days=days):
            continue
        r = client.call("GET", f"{it['posted_ids'][0]}/conversation",
                        {"fields": "id,text,username,timestamp,replied_to"}, client.token)
        for x in new_replies(r.get("data", []), me, known):
            nums.append(max(nums) + 1)
            row = {"no": f"R{max(nums)}", "id": x["id"], "item": it["id"], "post": it["parts"][0][:80],
                   "user": x["username"], "text": x.get("text", ""), "at": x.get("timestamp"),
                   "status": "新着", "draft": ""}
            rows.append(row)
            known.add(x["id"])
            added.append(row)
    return added


def cmd_fetch():
    rows = load()
    added = fetch(T.Client(T.read_token()), T.load_queue(), rows)
    save(rows)
    T.log(f"返信：まだ答えていない新しい返信が{len(added)}件ありました")


def cmd_list():
    for r in load():
        if r["status"] in ("新着", "下書き"):
            print(f"{r['no']} [{r['status']}] @{r['user']}：{r['text'][:60]}")
            if r["draft"]:
                print(f"    返事の下書き：{r['draft']}")


def set_draft(no, text):
    rows = load()
    r = find(rows, no)
    problems = T.check_rules([text])
    if T.LINK_RE.search(text):
        problems.append("返事にリンクは入れません")
    if problems:
        raise T.ThreadsError(" / ".join(problems))
    r.update(draft=text.strip(), status="下書き")
    save(rows)


def answer(no, text=None):
    rows = load()
    r = find(rows, no)
    if r["status"] == "返事済み":
        raise T.ThreadsError(f"{r['no']} にはもう返事を出す予約をしています")
    text = (text or r["draft"]).strip()
    if not text:
        raise T.ThreadsError(f"{r['no']} の下書きがありません")
    if T.LINK_RE.search(text) or T.check_rules([text]):
        raise T.ThreadsError("返事が決まりに合いません（リンク・強い言葉）")
    items = T.load_queue()
    it = {"id": f"{r['no']}-{r['id'][-6:]}", "kind": "返信", "parts": [text], "reply_to": r["id"],
          "status": "承認済み", "time": T.now().isoformat(), "tries": 0}
    T.touch(it)
    items.append(it)
    T.save_queue(items)
    r.update(status="返事済み", draft=text)
    save(rows)
    T.log(f"{r['no']}（@{r['user']} さんへの返事）を、すぐ出す予約にしました")
    if T.load_cfg().get("threads_cloud"):
        import threads_cloud
        threads_cloud.sync()


def skip(no):
    rows = load()
    find(rows, no)["status"] = "見送り"
    save(rows)


def section_html(esc):
    """見本ページの最後に付ける「返信の下書き」。"""
    rows = [r for r in load() if r["status"] in ("新着", "下書き")]
    if not rows:
        return ""
    out = ["<h2>返信の下書き（OK の番号を送ってください。例：「R1 OK」）</h2>"]
    for r in rows:
        out.append(f"""<div class="cand"><div class="why"><b>{esc(r['no'])}</b>　@{esc(r['user'])} さんから
（あなたの投稿：{esc(r['post'][:40])}…）<br>「{esc(r['text'])}」<br><br>
<b>返事の下書き：</b>{esc(r['draft']) or '（まだありません）'}</div></div>""")
    return "".join(out)
