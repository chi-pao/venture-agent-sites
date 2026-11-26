# -*- coding: utf-8 -*-
"""ノボログの予約を、クラウド（GitHub Actions）と手元のパソコンで合わせる。

しくみ:
  - 予約は非公開リポジトリ chi-pao/venture-studio-data の noborog/threads_queue.json に置く。
    クラウドが15分ごとにそれを見て、時間になった物を投稿する（パソコンが止まっていても出る）。
  - 手元で承認・取り消しをしたら、この sync で非公開リポジトリに送る。
    手元のタスク（10分ごと）も sync だけをして、クラウドの投稿結果を手元に取り込む。
  - 同じ予約が両方で変わっていたら、changed_at が新しい方を残す。
    ただし、投稿した記録（posted_ids）は、多い方を必ず残す（二重に出さないため）。
  - 合いことば（トークン）は、鍵（secrets/threads_token_key.txt と GitHub の秘密欄 THREADS_TOKEN_KEY）で
    かぎをかけて noborog/token.enc に置く。そのままの文字はどこにも置かない。画面にも出さない。
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import threads as T

REPO_URL = "https://github.com/chi-pao/venture-studio-data.git"
SUB = "noborog"
CLONE = T.HERE / "data" / "cloud-sync"
KEY_FILE = T.SECRETS / "threads_token_key.txt"
OUTCOME = ("status", "posted_ids", "posted_at", "error", "tries")
CONFIG_KEYS_SKIP = ("threads_cloud",)


class SyncError(RuntimeError):
    pass


# ---------- 予約を合わせる ----------
def merge(local, remote):
    """手元とクラウドの予約を合わせる。並びは手元の順、クラウドにしかない物は後ろに足す。"""
    rmap = {it["id"]: it for it in remote}
    out, seen = [], set()
    for l in local:
        r = rmap.get(l["id"])
        seen.add(l["id"])
        if not r:
            out.append(l)
            continue
        newer = r if (r.get("changed_at") or "") > (l.get("changed_at") or "") else l
        it = json.loads(json.dumps(newer, ensure_ascii=False))
        other = l if newer is r else r
        if len(other.get("posted_ids") or []) > len(it.get("posted_ids") or []):
            for k in OUTCOME:
                if k in other:
                    it[k] = other[k]
        out.append(it)
    out += [r for r in remote if r["id"] not in seen]
    return out


# ---------- 合いことばのかぎ ----------
def _openssl():
    for c in (shutil.which("openssl"), r"C:\Program Files\Git\usr\bin\openssl.exe",
              r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if c and Path(c).exists():
            return c
    raise SyncError("openssl が見つかりません（Git for Windows に入っています）")


def _crypt(src, dst, decrypt=False):
    if not KEY_FILE.exists():
        raise SyncError("合いことばの鍵（secrets/threads_token_key.txt）がありません")
    args = [_openssl(), "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
            "-pass", f"file:{KEY_FILE}", "-in", str(src), "-out", str(dst)]
    if decrypt:
        args.insert(2, "-d")
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SyncError("合いことばのかぎの開け閉めに失敗しました")


# ---------- git ----------
def _git(*args, check=True):
    r = subprocess.run(["git", "-C", str(CLONE), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SyncError(f"git {args[0]} に失敗しました: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def _fresh():
    if not (CLONE / ".git").exists():
        CLONE.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "-q", REPO_URL, str(CLONE)], capture_output=True, text=True)
        if r.returncode != 0:
            raise SyncError("非公開の置き場所を取り出せませんでした")
    _git("fetch", "-q", "origin", "main")
    _git("reset", "-q", "--hard", "origin/main")


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def sync(upload_token=False, tries=3):
    """クラウドの予約と手元の予約を合わせて、両方に書く。"""
    for i in range(tries):
        _fresh()
        d = CLONE / SUB
        d.mkdir(exist_ok=True)
        local = T.load_queue()
        # 置き場所全体の .gitignore は threads_* を入れないので、このフォルダーだけ入れる
        (d / ".gitignore").write_text("!threads_*\n", encoding="utf-8")
        remote = _read(d / "threads_queue.json", [])
        merged = merge(local, remote)
        T.save_queue(merged)
        (d / "threads_queue.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
        cfg = {k: v for k, v in T.load_cfg().items() if k not in CONFIG_KEYS_SKIP}
        (d / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        _token(d, upload_token)
        if (d / "threads_log.txt").exists():
            shutil.copy(d / "threads_log.txt", T.DATA / "threads_cloud_log.txt")
        _git("add", "-A", SUB)
        if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return merged
        _git("-c", "user.name=noborog-local", "-c", "user.email=noborog-local@users.noreply.github.com",
             "commit", "-q", "-m", f"ノボログの予約（手元から） {T.now():%Y-%m-%d %H:%M}")
        if _git("push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            return merged
    raise SyncError("非公開の置き場所に送れませんでした（次の回にもう一度）")


def _token(d, upload):
    """合いことば：最初（--token）は手元からクラウドへ。そのあとはクラウドが延長した物を手元へ。"""
    enc, state = d / "token.enc", d / "state.json"
    local_state = T.load_state()
    if upload or not enc.exists():
        if not T.TOKEN_FILE.exists():
            return
        _crypt(T.TOKEN_FILE, enc)
        keep = {k: local_state[k] for k in ("token_saved_at", "token_expires_at", "user_id") if k in local_state}
        state.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    cloud_state = _read(state, {})
    if (cloud_state.get("token_saved_at") or "") > (local_state.get("token_saved_at") or ""):
        tmp = T.TOKEN_FILE.with_suffix(".tmp")
        _crypt(enc, tmp, decrypt=True)
        tmp.replace(T.TOKEN_FILE)
        local_state.update(cloud_state)
        T.save_state(local_state)
        T.log("クラウドで延長した合いことばを、手元にも入れました")
