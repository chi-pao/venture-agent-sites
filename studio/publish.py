# -*- coding: utf-8 -*-
"""⑦公開部：作ったアプリを、スマホでも見られる「確認用ページ」として公開する。

- GitHub の `preview/<番号>` ブランチにだけ送る（main には触らない）。
- Cloudflare Pages はブランチごとに確認用の URL を作る:
  https://preview-<番号>.venture-agent-sites.pages.dev/
- 検索に出ないよう、すべての HTML に noindex を入れる。
- 以前の review-previews/ のように main に溜まり続けない（案ごとに1つのブランチを上書き）。
- 実際に開けたかを確かめ、開けなければ「未確認」と正直に書く。
"""
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

NOINDEX = '<meta name="robots" content="noindex,nofollow">'


def find_static(build_dir, hint=""):
    """サーバーなしで開ける画面のフォルダーを探す。"""
    build_dir = Path(build_dir)
    for name in [hint, "dist", "build", "out", "public", "."]:
        if not name:
            continue
        d = (build_dir / name).resolve()
        if d.is_dir() and (d / "index.html").exists() and build_dir.resolve() in [d, *d.parents]:
            return d
    return None


def add_noindex(folder):
    for html in Path(folder).rglob("*.html"):
        text = html.read_text(encoding="utf-8", errors="replace")
        if "noindex" not in text:
            text = re.sub(r"(<head[^>]*>)", r"\1" + NOINDEX, text, count=1, flags=re.I)
            html.write_text(text, encoding="utf-8")


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")


def preview_url(cfg, idea_id):
    return f"https://preview-{idea_id.lower()}.{cfg['pages_host']}/"


def publish(cfg, work_dir, idea_id, static_dir):
    """戻り値: (URL, 状態の説明)"""
    if cfg.get("mock"):
        return "", "練習モードのため公開していません"
    if not cfg.get("publish_previews"):
        return "", "確認用ページの公開は設定でオフ（config.json の publish_previews）"
    if not static_dir:
        return "", "開ける画面（index.html）が見つからないため公開していません"
    stage = Path(work_dir) / f"publish-{idea_id}"
    if stage.exists():
        shutil.rmtree(stage)
    ignore = shutil.ignore_patterns("node_modules", ".git", ".env", ".env.*", "*.map")
    shutil.copytree(static_dir, stage, ignore=ignore)
    add_noindex(stage)
    branch = f"preview/{idea_id.lower()}"
    remote = f"https://github.com/{cfg['github_repo']}.git"
    steps = [["init", "-q"], ["checkout", "-q", "-b", branch], ["add", "-A"],
             ["-c", "user.name=venture-studio", "-c", "user.email=venture-studio@users.noreply.github.com",
              "commit", "-q", "-m", f"確認用ページ {idea_id}"],
             ["push", "-q", "--force", remote, f"HEAD:refs/heads/{branch}"]]
    for step in steps:
        r = _git(step, stage)
        if r.returncode != 0:
            return "", f"GitHub への送信に失敗（{' '.join(step[:2])}）: {r.stderr.strip()[:300]}"
    url = preview_url(cfg, idea_id)
    for _ in range(int(cfg.get("preview_wait_checks", 10))):
        time.sleep(30)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "venture-studio"}),
                                        timeout=20) as res:
                if res.status == 200:
                    return url, "公開して開けることを確認済み"
        except Exception:
            continue
    return url, "送信済み・開けるかは未確認（Cloudflare でブランチの確認用ページが無効の可能性）"
