# -*- coding: utf-8 -*-
"""案ごとの記録（JSON）、一覧表（BOARD.md）、学びのまとめ（learning.md）、通知。"""
import hashlib
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

# 段階の名前（画面に出すので日本語）
STAGES = {
    "idea": "企画済み",
    "market_no_go": "見送り（市場・競合部）",
    "review_fail": "見送り（審査部）",
    "building": "開発中",
    "needs_fix": "品質の基準に届かず（あなたの判断待ち）",
    "owner_check": "【最終確認】あなたの判断待ち",
    "brushup": "ブラッシュアップ中",
    "continuing": "続ける（事業として独立）",
    "killed": "やめる",
    "error": "途中で失敗（記録を確認）",
}
WAITING_ON_OWNER = ("owner_check", "needs_fix")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Store:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.ideas_dir = self.root / "ideas"
        self.ideas_dir.mkdir(parents=True, exist_ok=True)

    # ---- 案の読み書き ----
    def new_id(self, title):
        h = hashlib.sha256(f"{title}{datetime.now().isoformat()}".encode()).hexdigest()[:6]
        return datetime.now().strftime("%m%d") + "-" + h

    def folder(self, idea_id):
        p = self.ideas_dir / idea_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def load(self, idea_id):
        path = self.ideas_dir / idea_id / "record.json"
        if not path.exists():
            raise SystemExit(f"案 {idea_id} が見つかりません。`py studio.py list` で番号を確かめてください。")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, rec):
        path = self.folder(rec["id"]) / "record.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def all(self):
        out = []
        for p in sorted(self.ideas_dir.glob("*/record.json")):
            out.append(json.loads(p.read_text(encoding="utf-8")))
        return out

    def set_stage(self, rec, stage, note=""):
        rec["stage"] = stage
        rec.setdefault("history", []).append({"at": now(), "stage": STAGES.get(stage, stage), "note": note})
        self.save(rec)

    # ---- 一覧表 ----
    def write_board(self):
        recs = self.all()
        lines = ["# 事業スタジオの一覧", "", f"更新: {now()}", "",
                 "## あなたの番（確認・作業が必要なもの）", ""]
        waiting = [r for r in recs if r["stage"] in WAITING_ON_OWNER]
        if not waiting:
            lines.append("- なし")
        for r in waiting:
            lines.append(f"- **{r['id']}** {r['idea']['title']} … {STAGES[r['stage']]} → 次の操作: `{next_action(r)}`")
        lines += ["", "## すべての案", "", "| 番号 | 名前 | 段階 | 合計点 | 勝てる見込み | 更新 |", "|---|---|---|---|---|---|"]
        for r in sorted(recs, key=lambda x: x["history"][-1]["at"], reverse=True):
            win = (r.get("market") or {}).get("win_probability", "")
            lines.append(f"| {r['id']} | {r['idea']['title']} | {STAGES.get(r['stage'], r['stage'])} | "
                         f"{r.get('score', '')} | {win} | {r['history'][-1]['at']} |")
        (self.root / "BOARD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 学び（⑧数字・学習部が企画部に渡すもの） ----
    def learning_text(self, limit=25):
        items = []
        for r in self.all():
            last = r["history"][-1]
            if r["stage"] in ("market_no_go", "review_fail", "killed", "continuing"):
                items.append(f"- {r['idea']['title']}: {STAGES[r['stage']]}。理由: {last.get('note', '')[:200]}")
            for m in r.get("metrics", [])[-1:]:
                items.append(f"- {r['idea']['title']} の実際の数字（{m['at']}）: 訪問 {m.get('visits')}、"
                             f"登録 {m.get('signups')}、売上 {m.get('revenue_yen')} 円")
        text = "\n".join(items[-limit:])
        (self.root / "learning.md").write_text("# 過去の学び（企画部に渡す）\n\n" + (text or "なし") + "\n", encoding="utf-8")
        return text

    def past_titles(self):
        return [r["idea"]["title"] for r in self.all()]


def next_action(rec):
    i = rec["id"]
    if rec["stage"] in WAITING_ON_OWNER:
        return f"py studio.py show {i} → decide {i} continue / brushup / kill"
    return f"py studio.py show {i}"


def notify(cfg, data_dir, title, body):
    """INBOX.md に必ず残し、Discord の通知先が設定されていれば送る。"""
    inbox = Path(data_dir) / "INBOX.md"
    with inbox.open("a", encoding="utf-8") as f:
        f.write(f"\n## {now()} {title}\n\n{body}\n")
    print(f"\n[お知らせ] {title}\n{body}\n")
    url = os.environ.get("STUDIO_DISCORD_WEBHOOK") or cfg.get("discord_webhook_url")
    if not url or cfg.get("mock"):
        return
    payload = json.dumps({"content": f"**{title}**\n{body}"[:1900]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json",
                                                             "User-Agent": "venture-studio"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # 通知の失敗で本体を止めない
        print(f"（Discord への通知に失敗: {e}。INBOX.md には残っています）")
