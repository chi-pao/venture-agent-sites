# -*- coding: utf-8 -*-
"""Threads 自動投稿のテスト（本物の Threads にはつながない）。"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import threads  # noqa: E402

CFG = dict(threads.DEFAULTS)


class FakeAPI:
    def __init__(self, fail_on=None):
        self.calls, self.n, self.fail_on = [], 0, fail_on

    def __call__(self, method, path, params, token, base=None):
        self.calls.append((method, path, dict(params)))
        if path.endswith("/threads"):
            self.n += 1
            if self.fail_on == self.n:
                raise threads.ThreadsError("わざと失敗")
            return {"id": f"c{self.n}"}
        if method == "GET" and "fields" in params:
            return {"status": "FINISHED"}
        if path.endswith("/threads_publish"):
            return {"id": "p" + params["creation_id"][1:]}
        raise AssertionError(path)


def client(api):
    c = threads.Client("tok", call=api, sleep=lambda s: None)
    c._uid = "U"
    return c


GOOD = ["大掃除でいちばんしんどいの、重い家具を動かすところじゃない？",
        "PR｜楽天市場の商品ページはこちら\nhttps://a.r10.to/abc"]


def item(id_, minutes_ago=5, parts=GOOD, status="承認済み"):
    return {"id": id_, "status": status, "parts": list(parts),
            "time": (threads.now() - timedelta(minutes=minutes_ago)).isoformat()}


class RulesTest(unittest.TestCase):
    def test_good(self):
        self.assertEqual(threads.check_rules(GOOD), [])

    def test_link_in_first_part(self):
        self.assertTrue(any("1本目" in p for p in threads.check_rules(["PR 楽天市場 https://a.r10.to/x"])))

    def test_link_needs_pr_and_rakuten(self):
        probs = threads.check_rules(["ふつうの文", "ここから https://a.r10.to/x"])
        self.assertTrue(any("PR" in p for p in probs))
        self.assertTrue(any("楽天市場" in p for p in probs))

    def test_banned_and_length(self):
        probs = threads.check_rules(["最安です" + "あ" * 600])
        self.assertTrue(any("最安" in p for p in probs))
        self.assertTrue(any("500" in p for p in probs))


class MediaTest(unittest.TestCase):
    def test_carousel_first_part(self):
        api = FakeAPI()
        it = item("m")
        it["images"] = ["https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg"]
        threads.post_item(client(api), it)
        posts = [c[2] for c in api.calls if c[1].endswith("/threads")]
        self.assertEqual([p.get("is_carousel_item") for p in posts[:3]], ["true"] * 3)
        self.assertEqual(posts[3]["media_type"], "CAROUSEL")
        self.assertEqual(posts[3]["children"], "c1,c2,c3")
        self.assertEqual(posts[4]["media_type"], "TEXT")  # 2本目は文だけ
        self.assertEqual(it["status"], "投稿済み")

    def test_single_image(self):
        api = FakeAPI()
        it = item("s")
        it["images"] = ["https://img/1.jpg"]
        threads.post_item(client(api), it)
        first = [c[2] for c in api.calls if c[1].endswith("/threads")][0]
        self.assertEqual(first["media_type"], "IMAGE")

    def test_video_card_first_then_photos(self):
        api = FakeAPI()
        it = item("v")
        it["images"] = ["https://img/1.jpg"]
        it["video"] = {"local": "media/v/v.mp4", "url": "https://m/v.mp4"}
        threads.post_item(client(api), it)
        posts = [c[2] for c in api.calls if c[1].endswith("/threads")]
        self.assertEqual(posts[0]["media_type"], "VIDEO")
        self.assertEqual(posts[0]["video_url"], "https://m/v.mp4")
        self.assertEqual(posts[1]["image_url"], "https://img/1.jpg")
        self.assertEqual(posts[2]["media_type"], "CAROUSEL")

    def test_card_only_single_image(self):
        api = FakeAPI()
        it = item("c")
        it["card"] = {"local": "media/c/c.jpg", "url": "https://m/c.jpg"}
        threads.post_item(client(api), it)
        first = [c[2] for c in api.calls if c[1].endswith("/threads")][0]
        self.assertEqual((first["media_type"], first["image_url"]), ("IMAGE", "https://m/c.jpg"))

    def test_media_not_uploaded_is_not_posted(self):
        api = FakeAPI()
        it = item("n")
        it["video"] = {"local": "media/n/n.mp4", "url": None}
        with self.assertRaises(threads.ThreadsError):
            threads.post_item(client(api), it)
        self.assertEqual(api.calls, [])

    def test_image_rules(self):
        self.assertTrue(threads.check_rules(GOOD, ["http://x"]))
        self.assertTrue(threads.check_rules(GOOD, ["https://x"] * 21))


class RunTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = threads.LOG, threads.DATA
        threads.DATA = Path(self.tmp.name)
        threads.LOG = threads.DATA / "log.txt"

    def tearDown(self):
        threads.LOG, threads.DATA = self.saved
        self.tmp.cleanup()

    def test_posts_thread_as_reply_chain(self):
        api = FakeAPI()
        items = [item("a")]
        done = threads.run(client(api), items, CFG)
        self.assertEqual(done, ["a"])
        self.assertEqual(items[0]["status"], "投稿済み")
        self.assertEqual(items[0]["posted_ids"], ["p1", "p2"])
        creates = [c for c in api.calls if c[1].endswith("/threads")]
        self.assertNotIn("reply_to_id", creates[0][2])
        self.assertEqual(creates[1][2]["reply_to_id"], "p1")

    def test_only_approved_and_due(self):
        api = FakeAPI()
        items = [item("cand", status="候補"), item("future", minutes_ago=-30)]
        self.assertEqual(threads.run(client(api), items, CFG), [])
        self.assertEqual(api.calls, [])

    def test_too_late_expires(self):
        items = [item("old", minutes_ago=60 * 5)]
        threads.run(client(FakeAPI()), items, CFG)
        self.assertEqual(items[0]["status"], "期限切れ")

    def test_daily_limit(self):
        items = [item(f"x{i}") for i in range(7)]
        done = threads.run(client(FakeAPI()), items, CFG)
        self.assertEqual(len(done), 5)

    def test_resume_after_partial_failure(self):
        items = [item("a")]
        threads.run(client(FakeAPI(fail_on=2)), items, CFG)
        self.assertEqual(items[0]["status"], "失敗")
        self.assertEqual(items[0]["posted_ids"], ["p1"])
        api = FakeAPI()
        api.n = 1
        threads.run(client(api), items, CFG)
        self.assertEqual(items[0]["status"], "投稿済み")
        creates = [c for c in api.calls if c[1].endswith("/threads")]
        self.assertEqual(len(creates), 1)  # 1本目はもう一度出さない
        self.assertEqual(creates[0][2]["reply_to_id"], "p1")

    def test_rule_violation_not_posted(self):
        api = FakeAPI()
        items = [item("bad", parts=["https://a.r10.to/x"])]
        threads.run(client(api), items, CFG)
        self.assertEqual(items[0]["status"], "失敗")
        self.assertEqual(api.calls, [])

    def test_dry_run_posts_nothing(self):
        api = FakeAPI()
        items = [item("a")]
        threads.run(client(api), items, CFG, dry=True)
        self.assertEqual(api.calls, [])
        self.assertEqual(items[0]["status"], "承認済み")


if __name__ == "__main__":
    unittest.main()
