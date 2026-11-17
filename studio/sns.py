# -*- coding: utf-8 -*-
"""⑧SNS運用部の後半：投稿案を、今の依頼一覧（ops/tasks/queue.json）に「承認待ち」で入れる。

今の流れ（ops/chatgpt/WORKFLOW.md）をそのまま使う:
  承認待ち → のぼるさんが OK → 承認済み → tools/chatgpt_packets.py --render で ChatGPT への依頼書
  → ChatGPT が画像・動画を作り Metricool で予約。
ここでは承認も投稿もしない。tools/chatgpt_packets.py の検査に通ったものだけを入れる。
"""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _packets():
    path = ROOT / "tools" / "chatgpt_packets.py"
    spec = importlib.util.spec_from_file_location("chatgpt_packets", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def queue_path(cfg):
    p = Path(cfg.get("queue_path") or ROOT / "ops" / "tasks" / "queue.json")
    return p if p.is_absolute() else (Path(__file__).resolve().parent / p).resolve()


def existing_titles(cfg):
    p = queue_path(cfg)
    if not p.exists():
        return []
    return [t.get("title", "") for t in json.loads(p.read_text(encoding="utf-8")).get("tasks", [])]


def add_posts(cfg, prefix, business, posts, url, campaign, extra=None):
    """戻り値: (入れた件数, 外した投稿と理由の一覧)"""
    pk = _packets()
    path = queue_path(cfg)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": 1, "tasks": []}
    used = {t.get("id") for t in data["tasks"]}
    added, dropped, n = 0, [], 0
    for post in posts:
        n += 1
        tid = f"{prefix}-{n:02d}"
        while tid in used:
            n += 1
            tid = f"{prefix}-{n:02d}"
        channel = post.get("channel")
        payload = {"business": business, "channel": channel, "format": post.get("format", ""),
                   "angle": post.get("angle", ""), "facts": post.get("facts", []),
                   "draft": post.get("text", ""), "asset_brief": post.get("asset_brief", ""),
                   "week": post.get("week"), **(extra or {})}
        if url:
            payload["url"] = pk.utm(url, str(channel).lower(), campaign)
        if channel in pk.CHANNEL_LIMITS:
            payload["max_chars"] = pk.CHANNEL_LIMITS[channel]
        task = {"id": tid, "kind": "sns_post_draft", "title": post.get("title", "")[:60] or tid,
                "status": "承認待ち", "payload": payload}
        errors = pk.check_task(task)
        if errors:
            dropped.append(f"{task['title']}: {'、'.join(errors)}")
            continue
        data["tasks"].append(task)
        used.add(tid)
        added += 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return added, dropped
