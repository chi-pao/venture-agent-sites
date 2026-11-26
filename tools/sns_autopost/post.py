# -*- coding: utf-8 -*-
"""お買い得物件チェッカー（のぼるの挑戦記）の SNS 投稿を、クラウドで直接出す。

Metricool を通さないので、無料の枠に左右されない。
GitHub の自動実行（.github/workflows/sns-autopost.yml）が15分ごとにこれを動かす。

決まり:
  - 出すのは ops/sns/autopost/posts.json の中で「approved」（のぼるさんの OK の言葉）が書いてある物だけ。
  - 時間（at）を過ぎた物を出す。3日より前の物は出さない（古い物を急に出さないため）。
  - 出した記録は ops/sns/autopost/log.json に残す。記録がある SNS には二度と出さない。
  - 失敗は3回までやり直す。それでもだめなら止めて、記録に理由を書く。
  - 合いことば（トークン）は GitHub の秘密欄から受け取る。画面にも記録にも出さない。
  - 合いことばがまだ無い SNS は飛ばす（記録には「準備中」と書く）。

使い方:
  python tools/sns_autopost/post.py            投稿する
  python tools/sns_autopost/post.py --check    つながりの確認だけ（投稿しない）
  python tools/sns_autopost/post.py --dry      何を出すかを表示するだけ
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POSTS = ROOT / "ops/sns/autopost/posts.json"
LOG = ROOT / "ops/sns/autopost/log.json"
JST = timezone(timedelta(hours=9))
RAW = "https://raw.githubusercontent.com/chi-pao/venture-agent-sites/main/"
MAX_TRIES = 3
CATCH_UP = timedelta(days=3)
PLATFORMS = ("threads", "instagram", "bluesky", "youtube", "tiktok")


class Skip(Exception):
    """合いことばが無いなど、今回は出さない（失敗には数えない）。"""


class Fail(Exception):
    pass


def env(name):
    v = os.environ.get(name, "").strip()
    return v or None


# ---------- 通信 ----------
def http(method, url, data=None, headers=None, form=None, raw=None, timeout=120):
    h = dict(headers or {})
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    elif raw is not None:
        body = raw
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
            return r.status, dict(r.headers), (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        # 合いことばが混ざらないよう、相手の返事の要点だけを残す
        msg = txt[:300]
        try:
            j = json.loads(txt)
            msg = json.dumps(j.get("error", j), ensure_ascii=False)[:300]
        except Exception:
            pass
        raise Fail(f"{e.code}: {msg}")


def public_url(path):
    return RAW + urllib.parse.quote(path)


def media_kind(path):
    return "video" if path.lower().endswith((".mp4", ".mov")) else "image"


# ---------- Threads ----------
def post_threads(p, check=False):
    tok = env("THREADS_TOKEN")
    if not tok:
        raise Skip("合いことば THREADS_TOKEN がまだありません")
    base = "https://graph.threads.net/v1.0"
    if check:
        _, _, me = http("GET", f"{base}/me?fields=username&access_token={tok}")
        return f"@{me.get('username')}"
    t = p["threads"]
    form = {"text": t["text"], "access_token": tok}
    m = p.get("media")
    if m:
        kind = media_kind(m)
        form["media_type"] = "VIDEO" if kind == "video" else "IMAGE"
        form["video_url" if kind == "video" else "image_url"] = public_url(m)
    else:
        form["media_type"] = "TEXT"
    _, _, c = http("POST", f"{base}/me/threads", form=form)
    cid = c["id"]
    for _ in range(60):  # 動画の準備を最大10分待つ
        _, _, s = http("GET", f"{base}/{cid}?fields=status,error_message&access_token={tok}")
        if s.get("status") == "FINISHED":
            break
        if s.get("status") in ("ERROR", "EXPIRED"):
            raise Fail(f"Threads の準備に失敗: {s.get('error_message')}")
        time.sleep(10)
    else:
        raise Fail("Threads の準備が10分で終わりませんでした")
    _, _, r = http("POST", f"{base}/me/threads_publish", form={"creation_id": cid, "access_token": tok})
    return r["id"]


# ---------- Instagram（Instagram ログインの API。プロのアカウントが必要） ----------
def post_instagram(p, check=False):
    tok = env("INSTAGRAM_TOKEN")
    if not tok:
        raise Skip("合いことば INSTAGRAM_TOKEN がまだありません")
    base = "https://graph.instagram.com/v21.0"
    if check:
        _, _, me = http("GET", f"{base}/me?fields=username&access_token={tok}")
        return f"@{me.get('username')}"
    m = p.get("media")
    if not m:
        raise Fail("Instagram は画像か動画が必要です")
    form = {"caption": p["instagram"]["caption"], "access_token": tok}
    if media_kind(m) == "video":
        form.update(media_type="REELS", video_url=public_url(m), share_to_feed="true")
    else:
        form["image_url"] = public_url(m)
    _, _, c = http("POST", f"{base}/me/media", form=form)
    cid = c["id"]
    for _ in range(60):
        _, _, s = http("GET", f"{base}/{cid}?fields=status_code,status&access_token={tok}")
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise Fail(f"Instagram の準備に失敗: {s.get('status')}")
        time.sleep(10)
    else:
        raise Fail("Instagram の準備が10分で終わりませんでした")
    _, _, r = http("POST", f"{base}/me/media_publish", form={"creation_id": cid, "access_token": tok})
    return r["id"]


# ---------- Bluesky ----------
URL_RE = re.compile(r"https?://[^\s　）)」]+")
TAG_RE = re.compile(r"(?:(?<=\s)|^)#([^\s#　、。！？]+)")


def facets(text):
    """リンクとハッシュタグを押せるようにする（位置はバイトで数える）。"""
    out = []
    for m in URL_RE.finditer(text):
        s, e = len(text[: m.start()].encode()), len(text[: m.end()].encode())
        out.append({"index": {"byteStart": s, "byteEnd": e},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}]})
    for m in TAG_RE.finditer(text):
        s, e = len(text[: m.start()].encode()), len(text[: m.end()].encode())
        out.append({"index": {"byteStart": s, "byteEnd": e},
                    "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": m.group(1)}]})
    return out


def small_image(path):
    """Bluesky は画像1枚 約1MB まで。大きい時は JPEG に縮める。"""
    data = path.read_bytes()
    if len(data) <= 950_000:
        return data, mimetypes.guess_type(path.name)[0] or "image/png"
    for q in (3, 6, 10):
        out = Path(tempfile.mkdtemp()) / "s.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-q:v", str(q), str(out)], check=True)
        if out.stat().st_size <= 950_000:
            return out.read_bytes(), "image/jpeg"
    raise Fail("画像を1MB以下にできませんでした")


def post_bluesky(p, check=False):
    handle, pw = env("BLUESKY_HANDLE"), env("BLUESKY_APP_PASSWORD")
    if not (handle and pw):
        raise Skip("合いことば BLUESKY_HANDLE / BLUESKY_APP_PASSWORD がまだありません")
    pds = "https://bsky.social/xrpc"
    _, _, s = http("POST", f"{pds}/com.atproto.server.createSession", data={"identifier": handle, "password": pw})
    auth = {"Authorization": f"Bearer {s['accessJwt']}"}
    if check:
        return f"@{s.get('handle')}"
    text = p["bluesky"]["text"]
    rec = {"$type": "app.bsky.feed.post", "text": text, "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "langs": ["ja"]}
    f = facets(text)
    if f:
        rec["facets"] = f
    m = p.get("media")
    if m:
        path = ROOT / m
        if media_kind(m) == "video":
            _, _, b = http("POST", f"{pds}/com.atproto.repo.uploadBlob", raw=path.read_bytes(),
                           headers={**auth, "Content-Type": "video/mp4"}, timeout=600)
            rec["embed"] = {"$type": "app.bsky.embed.video", "video": b["blob"],
                            "aspectRatio": {"width": 1080, "height": 1920}}
        else:
            data, mime = small_image(path)
            _, _, b = http("POST", f"{pds}/com.atproto.repo.uploadBlob", raw=data, headers={**auth, "Content-Type": mime})
            rec["embed"] = {"$type": "app.bsky.embed.images",
                            "images": [{"image": b["blob"], "alt": p["bluesky"].get("alt", "")}]}
    _, _, r = http("POST", f"{pds}/com.atproto.repo.createRecord", headers=auth,
                   data={"repo": s["did"], "collection": "app.bsky.feed.post", "record": rec})
    return r["uri"]


# ---------- YouTube ----------
def post_youtube(p, check=False):
    cid, sec, ref = env("YOUTUBE_CLIENT_ID"), env("YOUTUBE_CLIENT_SECRET"), env("YOUTUBE_REFRESH_TOKEN")
    if not (cid and sec and ref):
        raise Skip("合いことば YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN がまだありません")
    _, _, t = http("POST", "https://oauth2.googleapis.com/token",
                   form={"client_id": cid, "client_secret": sec, "refresh_token": ref, "grant_type": "refresh_token"})
    auth = {"Authorization": f"Bearer {t['access_token']}"}
    if check:
        _, _, ch = http("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", headers=auth)
        items = ch.get("items") or [{}]
        return items[0].get("snippet", {}).get("title", "?")
    m = p.get("media")
    if not m or media_kind(m) != "video":
        raise Fail("YouTube は動画だけです")
    y = p["youtube"]
    meta = {"snippet": {"title": y["title"][:100], "description": y["description"], "categoryId": "22",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": True}}
    data = (ROOT / m).read_bytes()
    _, h, _ = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                   data=meta, headers={**auth, "X-Upload-Content-Type": "video/mp4",
                                       "X-Upload-Content-Length": str(len(data))})
    loc = h.get("Location") or h.get("location")
    _, _, r = http("PUT", loc, raw=data, headers={**auth, "Content-Type": "video/mp4"}, timeout=900)
    return r["id"]


# ---------- TikTok ----------
def post_tiktok(p, check=False):
    # TikTok は、審査に通るまで「自分だけが見られる」投稿しかできない。審査が済んだら作る。
    raise Skip("TikTok は審査が済むまで準備中")


POSTERS = {"threads": post_threads, "instagram": post_instagram, "bluesky": post_bluesky,
           "youtube": post_youtube, "tiktok": post_tiktok}


# ---------- 予約を見て出す ----------
def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def due(p, now):
    at = datetime.fromisoformat(p["at"])
    if at.tzinfo is None:
        at = at.replace(tzinfo=JST)
    return at <= now < at + CATCH_UP


def run(dry=False, now=None, posters=None):
    posters = posters or POSTERS
    now = now or datetime.now(JST)
    posts, log = load(POSTS, []), load(LOG, {})
    changed = False
    for p in posts:
        if not (p.get("approved") or "").strip():
            continue  # のぼるさんの OK が無い物は出さない
        if p.get("stop") or not due(p, now):
            continue
        rec = log.setdefault(p["id"], {})
        for name in p.get("platforms", []):
            r = rec.get(name, {})
            if r.get("done") or r.get("tries", 0) >= MAX_TRIES:
                continue
            if dry:
                print(f"出す予定: {p['id']} → {name}")
                continue
            try:
                pid = posters[name](p)
                rec[name] = {"done": True, "id": pid, "at": now.isoformat(timespec="minutes")}
                print(f"出しました: {p['id']} → {name}")
            except Skip as e:
                if r.get("note") != str(e):
                    rec[name] = {**r, "note": str(e)}
                    changed = True
                print(f"飛ばしました: {p['id']} → {name}（{e}）")
                continue
            except Exception as e:  # noqa: BLE001
                tries = r.get("tries", 0) + 1
                rec[name] = {"tries": tries, "error": str(e)[:300], "at": now.isoformat(timespec="minutes")}
                print(f"失敗しました（{tries}回目）: {p['id']} → {name}")
            changed = True
    if changed and not dry:
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return changed


def check():
    ok = True
    for name, f in POSTERS.items():
        try:
            print(f"{name}: つながりました（{f({}, check=True)}）")
        except Skip as e:
            print(f"{name}: {e}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"{name}: つながりませんでした（{str(e)[:200]}）")
    return ok


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    run(dry="--dry" in sys.argv)
