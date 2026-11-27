# -*- coding: utf-8 -*-
"""自動投稿の合いことば（YouTube・TikTok）を、かぎをかけて1つのファイルにしまう。

- しまう場所: 非公開リポジトリ chi-pao/venture-studio-data の autopost/tokens.enc
- かぎ: ノボログと同じ鍵（手元 studio/secrets/threads_token_key.txt ＝ GitHub の秘密欄 THREADS_TOKEN_KEY）
  → のぼるさんが GitHub の秘密欄に新しく入れる物は無い。
- かけ方はノボログ（studio/threads_cloud.py）と同じ openssl の形。中身は画面にも記録にも出さない。
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class VaultError(RuntimeError):
    pass


def openssl():
    for c in (shutil.which("openssl"), r"C:\Program Files\Git\usr\bin\openssl.exe",
              r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if c and Path(c).exists():
            return c
    raise VaultError("openssl が見つかりません（Git for Windows に入っています）")


def _run(key_file, src, dst, decrypt):
    if not Path(key_file).exists():
        raise VaultError("合いことばの鍵がありません")
    args = [openssl(), "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt",
            "-pass", f"file:{key_file}", "-in", str(src), "-out", str(dst)]
    if decrypt:
        args.insert(2, "-d")
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise VaultError("合いことばのかぎの開け閉めに失敗しました")


def load(enc_path, key_file):
    """かぎを開けて中身（dict）を返す。ファイルが無ければ空。"""
    enc_path = Path(enc_path)
    if not enc_path.exists():
        return {}
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        _run(key_file, enc_path, tmp, decrypt=True)
        return json.loads(Path(tmp).read_text(encoding="utf-8"))
    finally:
        os.remove(tmp)


def save(enc_path, key_file, data):
    enc_path = Path(enc_path)
    enc_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        Path(tmp).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _run(key_file, tmp, enc_path, decrypt=False)
    finally:
        os.remove(tmp)
