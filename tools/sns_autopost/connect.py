# -*- coding: utf-8 -*-
"""のぼるさんのパソコンで1回だけ動かして、YouTube・TikTok とクラウドの自動投稿をつなぐ。

  py tools\\sns_autopost\\connect.py youtube   ブラウザで「許可」を押すだけ
  py tools\\sns_autopost\\connect.py tiktok    同じく「許可」を押すだけ（TikTok のアプリの準備のあと）
  py tools\\sns_autopost\\connect.py status    つながっているかを見る（合いことばは出さない）

- 合いことばは画面に出さない。かぎをかけて、非公開リポジトリ venture-studio-data の autopost/tokens.enc に送る。
- かぎは手元の studio/secrets/threads_token_key.txt（GitHub の秘密欄 THREADS_TOKEN_KEY と同じ物）。
"""
import base64
import getpass
import glob
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import post  # noqa: E402
import vault  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KEY_FILE = Path(os.environ.get("AUTOPOST_KEY_FILE") or ROOT / "studio/secrets/threads_token_key.txt")
DATA_REPO = "https://github.com/chi-pao/venture-studio-data.git"
ENC_IN_REPO = "autopost/tokens.enc"
JST = timezone(timedelta(hours=9))
YT_SCOPE = "https://www.googleapis.com/auth/youtube"  # 上げる・状態を見る・試しの動画を消す
TT_SCOPE = "user.info.basic,video.upload"
TT_PORT = 8723
TT_REDIRECT = f"http://localhost:{TT_PORT}/callback/"


def say(msg):
    print(msg, flush=True)


# ---------- ブラウザで許可を受け取る ----------
def wait_for_code(port, open_url, timeout=600):
    """手元の受け口でブラウザからの返事（code）を待つ。"""
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:
                got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>つながりました。この画面は閉じてかまいません。</h2>".encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    srv.timeout = 2
    real_port = srv.server_address[1]
    url = open_url(real_port)
    say("ブラウザが開きます。アカウントを選んで「許可」（または「続行」）を押してください。")
    webbrowser.open(url)
    end = datetime.now() + timedelta(seconds=timeout)
    while not got and datetime.now() < end:
        srv.handle_request()
    srv.server_close()
    if "error" in got:
        raise SystemExit(f"許可されませんでした（{got.get('error')}）。もう一度やり直してください。")
    if not got.get("code"):
        raise SystemExit("10分たっても許可が届きませんでした。もう一度やり直してください。")
    return got["code"]


def pkce_pair(hex_challenge=False):
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = digest.hex() if hex_challenge else base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ---------- 非公開リポジトリに送る ----------
def git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"非公開の置き場所とのやりとりに失敗しました（git {args[0]}）")
    return r


def store(service, entry):
    """非公開リポジトリの tokens.enc の、その SNS の分だけを書きかえて送る。"""
    if not KEY_FILE.exists():
        raise SystemExit(f"かぎのファイルがありません: {KEY_FILE}")
    entry["saved_at"] = datetime.now(JST).isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "data"
        r = subprocess.run(["git", "clone", "-q", "--depth", "1", DATA_REPO, str(repo)], capture_output=True)
        if r.returncode != 0:
            raise SystemExit("非公開の置き場所を取り出せませんでした（GitHub にログインしているか確かめてください）")
        for _ in range(3):
            enc = repo / ENC_IN_REPO
            data = vault.load(enc, KEY_FILE)
            data[service] = entry
            vault.save(enc, KEY_FILE, data)
            git(repo, "add", ENC_IN_REPO)
            git(repo, "-c", "user.name=autopost-connect", "-c", "user.email=autopost@users.noreply.github.com",
                "commit", "-q", "-m", f"自動投稿: {service} をつないだ")
            if subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:main"],
                              capture_output=True).returncode == 0:
                return
            git(repo, "fetch", "-q", "--depth", "1", "origin", "main")
            git(repo, "reset", "-q", "--hard", "origin/main")
    raise SystemExit("非公開の置き場所に送れませんでした。少したってからもう一度動かしてください。")


# ---------- YouTube ----------
def find_client_json():
    """Google の画面でダウンロードした client_secret_….json を、ダウンロードフォルダーから探す。"""
    home = Path.home()
    found = []
    for d in (home / "Downloads", home / "ダウンロード", home / "Desktop", Path.cwd()):
        found += glob.glob(str(d / "client_secret*.json"))
    found.sort(key=os.path.getmtime, reverse=True)
    for f in found:
        try:
            j = json.loads(Path(f).read_text(encoding="utf-8"))
            c = j.get("installed") or j.get("web")
            if c and c.get("client_id") and c.get("client_secret"):
                return Path(f), c
        except Exception:  # noqa: BLE001
            continue
    return None, None


def connect_youtube():
    path, c = find_client_json()
    if not c:
        raise SystemExit("ダウンロードフォルダーに client_secret で始まるファイルが見つかりません。\n"
                         "手順書の「YouTube」の、ファイルをダウンロードする所をもう一度やってください。")
    say(f"Google の準備のファイルを見つけました: {path.name}")
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)

    def url(port):
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": c["client_id"], "redirect_uri": f"http://127.0.0.1:{port}", "response_type": "code",
            "scope": YT_SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256"})

    ports = {}

    def url_and_remember(port):
        ports["p"] = port
        return url(port)

    code = wait_for_code(0, url_and_remember)
    _, _, t = post.http("POST", "https://oauth2.googleapis.com/token", form={
        "client_id": c["client_id"], "client_secret": c["client_secret"], "code": code,
        "grant_type": "authorization_code", "redirect_uri": f"http://127.0.0.1:{ports['p']}",
        "code_verifier": verifier})
    if not t.get("refresh_token"):
        raise SystemExit("長く使える合いことばがもらえませんでした。もう一度やり直してください。")
    entry = {"client_id": c["client_id"], "client_secret": c["client_secret"], "refresh_token": t["refresh_token"]}
    name = post.youtube_channel(post.youtube_access(entry))
    store("youtube", entry)
    say(f"YouTube とつながりました（チャンネル: {name}）。クラウドの置き場所にしまいました。")
    say(f"ダウンロードした {path.name} は、もう消してかまいません。")


# ---------- TikTok ----------
def connect_tiktok():
    say("TikTok の開発者の画面にある「Client key」と「Client secret」を入れます。")
    say("（貼り付けても文字は表示されません。貼ったら Enter を押してください）")
    key = getpass.getpass("Client key: ").strip()
    sec = getpass.getpass("Client secret: ").strip()
    if not key or not sec:
        raise SystemExit("空でした。もう一度やり直してください。")
    verifier, challenge = pkce_pair(hex_challenge=True)  # TikTok のパソコン用は16進の形
    state = secrets.token_urlsafe(16)

    def url(_port):
        return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
            "client_key": key, "scope": TT_SCOPE, "response_type": "code", "redirect_uri": TT_REDIRECT,
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})

    code = wait_for_code(TT_PORT, url)
    _, _, t = post.http("POST", "https://open.tiktokapis.com/v2/oauth/token/", form={
        "client_key": key, "client_secret": sec, "code": code, "grant_type": "authorization_code",
        "redirect_uri": TT_REDIRECT, "code_verifier": verifier})
    if not t.get("refresh_token"):
        raise SystemExit("TikTok から合いことばがもらえませんでした。もう一度やり直してください。")
    entry = {"client_key": key, "client_secret": sec}
    entry.update(post.tiktok_token_fields(t))
    store("tiktok", entry)
    say("TikTok とつながりました。クラウドの置き場所にしまいました。")


def status():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "data"
        subprocess.run(["git", "clone", "-q", "--depth", "1", DATA_REPO, str(repo)], capture_output=True)
        data = vault.load(repo / ENC_IN_REPO, KEY_FILE)
    for s in ("youtube", "tiktok"):
        e = data.get(s)
        say(f"{s}: " + (f"つながっています（{e.get('saved_at', '?')} に保存）" if e else "まだです"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"youtube": connect_youtube, "tiktok": connect_tiktok, "status": status}.get(
        cmd, lambda: say(__doc__))()
