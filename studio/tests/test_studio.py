# -*- coding: utf-8 -*-
"""練習モードで、企画から【最終確認】・SNS・楽天アフィリエイトまでを通すテスト。AIも楽天も呼ばない。

実行: py -m unittest discover -s studio/tests
"""
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[1]
ROOT = STUDIO.parent
sys.path.insert(0, str(STUDIO))

import affiliate  # noqa: E402
import publish  # noqa: E402
import studio  # noqa: E402
from engine import EngineError, extract_json  # noqa: E402


def packets():
    spec = importlib.util.spec_from_file_location("chatgpt_packets", ROOT / "tools" / "chatgpt_packets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.queue = self.tmp / "queue.json"
        shutil.copy(ROOT / "ops" / "tasks" / "queue.json", self.queue)  # 本物の依頼一覧の写しに足す
        cfg = json.loads((STUDIO / "config.example.json").read_text(encoding="utf-8"))
        cfg.update(mock=True, queue_path=str(self.queue))
        self.cfg_path = self.tmp / "config.json"
        self.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            studio.main(["--config", str(self.cfg_path), *args])
        return buf.getvalue()

    def recs(self):
        out = {}
        for p in (self.tmp / "data" / "ideas").glob("*/record.json"):
            r = json.loads(p.read_text(encoding="utf-8"))
            out[r["idea"]["title"]] = r
        return out

    def queue_tasks(self, prefix):
        return [t for t in json.loads(self.queue.read_text(encoding="utf-8"))["tasks"] if t["id"].startswith(prefix)]

    def test_idea_to_owner_check_then_continue(self):
        self.cli("run")
        r = self.recs()
        self.assertEqual(r["練習用の案A"]["stage"], "owner_check")      # 確認なしで最後まで作った
        self.assertEqual(r["練習用の案B"]["stage"], "market_no_go")     # 競合に負ける
        self.assertEqual(r["練習用の案C"]["stage"], "market_no_go")     # 点数不足
        a = r["練習用の案A"]
        self.assertEqual(len([h for h in a["history"] if h["stage"] == "開発中"]), 1)
        self.assertEqual(a["qa"]["verdict"], "レビュー可")               # 品質部の要修正 → 自動で直した
        doc = (self.tmp / "data" / "ideas" / a["id"] / "最終確認.md").read_text(encoding="utf-8")
        for words in ("なぜ収益化できそうか", "心配な点", "decide", "continue"):
            self.assertIn(words, doc)
        self.assertIn("【最終確認】", (self.tmp / "data" / "INBOX.md").read_text(encoding="utf-8"))
        self.assertEqual(self.queue_tasks("ST-"), [])                   # 続けると決めるまで SNS には入れない

        with self.assertRaises(SystemExit):
            self.cli("decide", a["id"], "brushup")                       # 直す点がないブラッシュアップは不可
        self.cli("decide", a["id"], "brushup", "--note", "色を明るく", "--later")
        self.assertEqual(self.recs()["練習用の案A"]["stage"], "brushup")
        self.cli("auto")                                                 # 定期実行が直しを進める
        a = self.recs()["練習用の案A"]
        self.assertEqual(a["stage"], "owner_check")
        self.assertIn("色を明るく", (self.tmp / "data" / "ideas" / a["id"] / "build" / "SPEC.md").read_text(encoding="utf-8"))

        self.cli("decide", a["id"], "continue")
        self.assertEqual(self.recs()["練習用の案A"]["stage"], "continuing")
        tasks = self.queue_tasks("ST-")
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t["status"] == "承認待ち" for t in tasks))   # AIは承認しない
        self.assertEqual(packets().check_queue(json.loads(self.queue.read_text(encoding="utf-8"))), {})

        with self.assertRaises(SystemExit):
            self.cli("decide", a["id"], "kill")                          # もう判断済み

    def test_kill_feeds_learning_and_auto_waits(self):
        self.cli("run")
        a = self.recs()["練習用の案A"]
        self.cli("decide", a["id"], "kill", "--note", "興味がない分野")
        self.assertIn("興味がない分野", (self.tmp / "data" / "learning.md").read_text(encoding="utf-8"))
        self.cli("metrics", a["id"], "--visits", "10", "--signups", "1", "--revenue", "0")
        self.assertIn("訪問 10", (self.tmp / "data" / "learning.md").read_text(encoding="utf-8"))
        out = self.cli("auto")                                           # 7日たっていないので企画はしない
        self.assertNotIn("①企画部", out)

    def test_weekly_sns_and_affiliate(self):
        self.cli("sns")
        self.assertEqual(len(self.queue_tasks("CH-")), 2)
        self.cli("affiliate")
        af = self.queue_tasks("AF-")
        self.assertEqual(len(af), 2)
        for t in af:
            self.assertTrue(t["payload"]["affiliate"] and t["payload"]["pr_label"])
            self.assertIn("utm_campaign=af_", t["payload"]["url"])
            self.assertTrue(any("1,980円" in f for f in t["payload"]["facts"]))  # 事実は楽天の値だけ
            self.assertNotIn("練習用の事実", t["payload"]["facts"])
        page = next((self.tmp / "data" / "picks").glob("*/index.html")).read_text(encoding="utf-8")
        self.assertIn("【PR】", page)
        self.assertIn('rel="sponsored nofollow', page)
        self.assertEqual(packets().check_queue(json.loads(self.queue.read_text(encoding="utf-8"))), {})


class PartsTest(unittest.TestCase):
    def test_extract_fenced(self):
        self.assertEqual(extract_json('説明\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_extract_last_object(self):
        self.assertEqual(extract_json('前置き {"a": 1} 本題 {"b": {"c": 2}} 終わり'), {"b": {"c": 2}})

    def test_no_json(self):
        with self.assertRaises(EngineError):
            extract_json("JSONなし")

    def test_find_static_and_noindex(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "dist").mkdir()
            (tmp / "dist" / "index.html").write_text("<html><head><title>t</title></head></html>", encoding="utf-8")
            found = publish.find_static(tmp, "dist")
            self.assertEqual(found, (tmp / "dist").resolve())
            outside = tmp.parent / "index.html"
            existed = outside.exists()
            if not existed:
                outside.write_text("x", encoding="utf-8")
            try:  # 外を指されても外は選ばず、中の dist を使う
                self.assertEqual(publish.find_static(tmp, ".."), (tmp / "dist").resolve())
            finally:
                if not existed:
                    outside.unlink()
            publish.add_noindex(found)
            self.assertIn("noindex", (found / "index.html").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rakuten_pick_needs_reviews(self):
        items = [{"name": "a", "price": 100, "reviews": 5}, {"name": "b", "price": 200, "reviews": 50}]
        self.assertEqual([i["name"] for i in affiliate.pick(items, 30)], ["b"])


if __name__ == "__main__":
    unittest.main()
