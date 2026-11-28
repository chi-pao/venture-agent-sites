# -*- coding: utf-8 -*-
"""お買い得物件チェッカー（のぼるの挑戦記）の SNS 投稿を、クラウドで直接出す。

Metricool を通さないので、無料の枠に左右されない。
GitHub の自動実行（.github/workflows/sns-autopost.yml）が15分ごとにこれを動かす。

決まり:
  - 出すのは ops/sns/autopost/posts.json の中で「approved」（のぼるさんの OK の言葉）が書いてある物だけ。
  - 時間（at）を過ぎた物を出す。3日より前の物は出さない（古い物を急に出さないため）。
  - 出した記録は非公開リポジトリ venture-studio-data の autopost/log.json に残す（AUTOPOST_DATA）。
    記録がある SNS には二度と出さない。出た・失敗・つなぎ直しは INBOX.md と Discord に知らせる。
  - YouTube・TikTok の合いことばは、のぼるさんが手元で connect.py を1回動かして、
    かぎをかけて autopost/tokens.enc にしまう。TikTok は延長のたびにしまい直す。
  - YouTube は上げたあと状態を読み返し、公開になっていなければ知らせる。
  - TikTok は審査の前なので「下書き」としてスマホに届け、のぼるさんが「投稿」を押す。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
POSTS = ROOT / "ops/sns/autopost/posts.json"
# クラウドでは、記録と合いことばを非公開リポジトリ（venture-studio-data の autopost/）に置く。
# AUTOPOST_DATA が無い時（手元の確かめ）は、今まで通りこのリポジトリの中を使う。
DATA = Path(os.environ["AUTOPOST_DATA"]) if os.environ.get("AUTOPOST_DATA") else None
LOG = (DATA / "log.json") if DATA else ROOT / "ops/sns/autopost/log.json"
TOKENS = (DATA / "tokens.enc") if DATA else None
KEY_FILE = os.environ.get("AUTOPOST_KEY_FILE")
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


def now_jst():
    return datetime.now(JST)


# ---------- 合いことばの金庫（YouTube・TikTok） ----------
_VAULT = {"data": None, "dirty": False}


def vault_get(service):
    if _VAULT["data"] is None:
        _VAULT["data"] = vault.load(TOKENS, KEY_FILE) if (TOKENS and KEY_FILE) else {}
    return _VAULT["data"].get(service)


def vault_put(service, entry):
    vault_get(service)
    _VAULT["data"][service] = entry
    _VAULT["dirty"] = True


def vault_flush():
    if _VAULT["dirty"] and TOKENS and KEY_FILE:
        vault.save(TOKENS, KEY_FILE, _VAULT["data"])
        _VAULT["dirty"] = False


# ---------- お知らせ（INBOX.md と Discord） ----------
def notify(title, body):
    """非公開リポジトリの INBOX.md に残し、Discord の通知先があれば送る。合いことばは入れない。"""
    if DATA:
        inbox = DATA.parent / "INBOX.md"
        with inbox.open("a", encoding="utf-8") as f:
            f.write(f"\n## {now_jst():%Y-%m-%d %H:%M} {title}\n\n{body}\n")
    url = env("STUDIO_DISCORD_WEBHOOK")
    if not url:
        return
    payload = json.dumps({"content": f"**{title}**\n{body}"[:1900]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json",
                                                             "User-Agent": "sns-autopost"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception:  # noqa: BLE001  お知らせの失敗で投稿を止めない
        pass


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
def youtube_creds():
    """金庫（connect.py youtube で入れた物）を先に、無ければ GitHub の秘密欄を使う。"""
    e = vault_get("youtube")
    if e and e.get("refresh_token"):
        return e
    cid, sec, ref = env("YOUTUBE_CLIENT_ID"), env("YOUTUBE_CLIENT_SECRET"), env("YOUTUBE_REFRESH_TOKEN")
    if cid and sec and ref:
        return {"client_id": cid, "client_secret": sec, "refresh_token": ref}
    raise Skip("YouTube がまだつながっていません（手元で connect.py youtube）")


def youtube_access(c):
    _, _, t = http("POST", "https://oauth2.googleapis.com/token",
                   form={"client_id": c["client_id"], "client_secret": c["client_secret"],
                         "refresh_token": c["refresh_token"], "grant_type": "refresh_token"})
    return t["access_token"]


def youtube_channel(access):
    _, _, ch = http("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                    headers={"Authorization": f"Bearer {access}"})
    items = ch.get("items") or [{}]
    return items[0].get("snippet", {}).get("title", "?")


def youtube_upload(access, data, meta):
    auth = {"Authorization": f"Bearer {access}"}
    _, h, _ = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                   data=meta, headers={**auth, "X-Upload-Content-Type": "video/mp4",
                                       "X-Upload-Content-Length": str(len(data))})
    loc = h.get("Location") or h.get("location")
    _, _, r = http("PUT", loc, raw=data, headers={**auth, "Content-Type": "video/mp4"}, timeout=900)
    return r["id"]


def youtube_status(access, vid):
    """上げた動画の状態を読み返す（公開になっているか）。"""
    _, _, r = http("GET", f"https://www.googleapis.com/youtube/v3/videos?part=status&id={vid}",
                   headers={"Authorization": f"Bearer {access}"})
    items = r.get("items") or []
    return items[0].get("status", {}) if items else {}


def youtube_meta(title, description, privacy):
    return {"snippet": {"title": title[:100], "description": description, "categoryId": "22",
                        "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": True}}


def post_youtube(p, check=False):
    access = youtube_access(youtube_creds())
    if check:
        return youtube_channel(access)
    m = p.get("media")
    if not m or media_kind(m) != "video":
        raise Fail("YouTube は動画だけです")
    y = p["youtube"]
    vid = youtube_upload(access, (ROOT / m).read_bytes(), youtube_meta(y["title"], y["description"], "public"))
    st = youtube_status(access, vid)
    url = f"https://youtube.com/shorts/{vid}"
    if st.get("privacyStatus") != "public" or st.get("uploadStatus") in ("rejected", "failed"):
        notify("YouTube：公開になっていません",
               f"「{p.get('title', p['id'])}」を上げましたが、状態が「{st.get('privacyStatus')}」でした。\n"
               f"{url}\nYouTube Studio で確かめて、必要なら手で上げ直してください。")
        return {"id": vid, "note": f"公開になっていない（{st.get('privacyStatus')} / {st.get('uploadStatus')}）"}
    return {"id": vid, "url": url}


def youtube_test():
    """2秒の試しの動画を「限定公開」で上げ、状態を読み返して、すぐ消す。"""
    access = youtube_access(youtube_creds())
    out = Path(tempfile.mkdtemp()) / "test.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=2",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "2", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    vid = youtube_upload(access, out.read_bytes(),
                         youtube_meta("自動投稿の試し（すぐ消します）", "自動投稿の試しです。", "unlisted"))
    st = youtube_status(access, vid)
    http("DELETE", f"https://www.googleapis.com/youtube/v3/videos?id={vid}",
         headers={"Authorization": f"Bearer {access}"})
    ok = st.get("privacyStatus") == "unlisted"
    print("YouTube の試し: " + ("指定どおり「限定公開」で上がりました（試しの動画は消しました）" if ok
                                else f"指定と違う状態でした（{st.get('privacyStatus')}）。試しの動画は消しました"))
    return ok


# ---------- TikTok（審査の前は「下書き」としてスマホに届ける） ----------
TT_API = "https://open.tiktokapis.com/v2"
MB = 1024 * 1024


def tiktok_token_fields(t, now=None):
    now = now or now_jst()
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"],
            "access_expires_at": (now + timedelta(seconds=int(t.get("expires_in", 7200)))).isoformat(timespec="seconds"),
            "refresh_expires_at": (now + timedelta(seconds=int(t.get("refresh_expires_in", 15552000)))).isoformat(timespec="seconds")}


def tiktok_access(now=None):
    """2時間で切れる合いことばを、切れそうなら延長する（更新用の値も毎回変わるので金庫にしまい直す）。"""
    now = now or now_jst()
    e = vault_get("tiktok")
    if not e or not e.get("refresh_token"):
        raise Skip("TikTok がまだつながっていません（手元で connect.py tiktok）")
    if datetime.fromisoformat(e["access_expires_at"]) - now < timedelta(minutes=5):
        _, _, t = http("POST", f"{TT_API}/oauth/token/", form={
            "client_key": e["client_key"], "client_secret": e["client_secret"],
            "grant_type": "refresh_token", "refresh_token": e["refresh_token"]})
        if not t.get("access_token"):
            raise Fail(f"TikTok の合いことばの延長に失敗: {t.get('error_description') or t.get('error')}")
        e = {**e, **tiktok_token_fields(t, now)}
        vault_put("tiktok", e)
    left = datetime.fromisoformat(e["refresh_expires_at"]) - now
    if left < timedelta(days=14) and e.get("warned_on") != now.date().isoformat():
        notify("TikTok：つなぎ直しが近いです",
               f"あと{left.days}日で TikTok とのつながりが切れます。パソコンで\n"
               "py tools\\sns_autopost\\connect.py tiktok\nを1回動かしてください。")
        vault_put("tiktok", {**e, "warned_on": now.date().isoformat()})
    return e["access_token"]


def tiktok_chunks(size):
    """TikTok の分け方: 1つ 5〜64MB。64MB 以下なら1回で送る。最後の1つは余りを含める。"""
    if size <= 64 * MB:
        return size, 1
    chunk = 10 * MB
    return chunk, size // chunk


def tiktok_api(method, path, tok, data):
    _, _, r = http(method, f"{TT_API}{path}", data=data,
                   headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"})
    err = (r.get("error") or {}) if isinstance(r, dict) else {}
    if err.get("code") not in (None, "ok"):
        raise Fail(f"TikTok: {err.get('code')} {err.get('message', '')}"[:300])
    return r.get("data") or {}


def post_tiktok(p, check=False):
    tok = tiktok_access()
    if check:
        d = tiktok_api("GET", "/user/info/?fields=display_name", tok, None)
        return (d.get("user") or {}).get("display_name", "?")
    m = p.get("media")
    if not m or media_kind(m) != "video":
        raise Fail("TikTok は動画だけです")
    data = (ROOT / m).read_bytes()
    size = len(data)
    chunk, count = tiktok_chunks(size)
    d = tiktok_api("POST", "/post/publish/inbox/video/init/", tok, {"source_info": {
        "source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}})
    pub, up = d["publish_id"], d["upload_url"]
    for i in range(count):
        s = i * chunk
        e = size if i == count - 1 else s + chunk
        http("PUT", up, raw=data[s:e], timeout=900, headers={
            "Content-Type": "video/mp4", "Content-Length": str(e - s), "Content-Range": f"bytes {s}-{e - 1}/{size}"})
    for _ in range(30):  # 最大5分、届いたかを見る
        st = tiktok_api("POST", "/post/publish/status/fetch/", tok, {"publish_id": pub})
        if st.get("status") in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            break
        if st.get("status") == "FAILED":
            raise Fail(f"TikTok の受け取りに失敗: {st.get('fail_reason')}")
        time.sleep(10)
    else:
        raise Fail("TikTok が5分たっても受け取りを終えませんでした")
    caption = (p.get("tiktok") or {}).get("caption", "")
    notify("TikTok：下書きが届きました。スマホで投稿してください",
           f"「{p.get('title', p['id'])}」を TikTok に送りました。\n"
           "スマホの TikTok のお知らせ（受信箱）を開き、下の説明文を貼って「投稿」を押してください。\n\n"
           f"――説明文――\n{caption}")
    return {"id": pub, "note": "下書きとしてスマホに届けた（本人が投稿を押す）"}


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
                res = posters[name](p)
                res = res if isinstance(res, dict) else {"id": res}
                rec[name] = {"done": True, **res, "at": now.isoformat(timespec="minutes")}
                print(f"出しました: {p['id']} → {name}")
                if name != "tiktok":  # TikTok は下書きを届けた時に、別のお知らせを出している
                    notify(f"{name}：出しました", f"「{p.get('title', p['id'])}」" +
                           (f"\n{res['url']}" if res.get("url") else "") +
                           (f"\n※{res['note']}" if res.get("note") else ""))
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
                if tries >= MAX_TRIES:
                    notify(f"{name}：出せませんでした", f"「{p.get('title', p['id'])}」を{MAX_TRIES}回試しましたが、"
                           f"出せませんでした。\n理由: {str(e)[:200]}\nClaude Code に「自動投稿が止まった」と伝えてください。")
            changed = True
    if changed and not dry:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if not dry:
        vault_flush()  # TikTok の延長した合いことばなどを、かぎをかけてしまい直す
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
    vault_flush()
    return ok


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    if "--youtube-test" in sys.argv:
        sys.exit(0 if youtube_test() else 1)
    run(dry="--dry" in sys.argv)
