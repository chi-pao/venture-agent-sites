# -*- coding: utf-8 -*-
"""クラウド（GitHub Actions）用の config.json を作る。

- 元は config.example.json。データの場所だけ、取り出した非公開リポジトリの場所にする。
- 秘密の値（楽天のキー）は GitHub の秘密欄から環境変数で受け取り、config.json（コミットしない）にだけ書く。
  Discord の通知先は store.notify が環境変数 STUDIO_DISCORD_WEBHOOK を直接読むので、ここには書かない。
- 秘密でない設定を変えたいときは、リポジトリの変数 STUDIO_SETTINGS に JSON で書く（例: {"ideas_per_run": 4}）。
- 値はひとつも画面に出さない。
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def build(env):
    cfg = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
    cfg["data_dir"] = env["STUDIO_DATA_DIR"]
    cfg["claude_cmd"] = "claude"
    # SNS の投稿待ち一覧とまとめページは main の中のファイルなので、扱いが決まるまでクラウドでは作らない
    cfg["weekly_sns"] = False
    cfg["weekly_affiliate"] = False
    if env.get("STUDIO_SETTINGS"):
        cfg.update(json.loads(env["STUDIO_SETTINGS"]))
    for key, name in (("rakuten_app_id", "RAKUTEN_APP_ID"), ("rakuten_access_key", "RAKUTEN_ACCESS_KEY"),
                      ("rakuten_affiliate_id", "RAKUTEN_AFFILIATE_ID")):
        if env.get(name):
            cfg[key] = env[name]
    if env.get("STUDIO_MOCK") == "1":
        cfg["mock"] = True
    return cfg


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "config.json"
    out.write_text(json.dumps(build(os.environ), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"設定を作りました: {out}")
