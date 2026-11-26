# -*- coding: utf-8 -*-
"""成績集めと分析のテスト（Threads・楽天・ブラウザ・AI にはつながない）。"""
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import threads as T  # noqa: E402
import threads_learn as L  # noqa: E402


def fake_call(method, path, params, token, base=None):
    if path == "me":
        return {"id": "me", "username": "noborog.life"}
    if path.endswith("/replies"):  # 自分の2本目と、ほかの人の返信1件
        return {"data": [{"username": "noborog.life"}, {"username": "someone"}]}
    if path.endswith("/insights"):
        v = {"p1": 100, "p2": 5}[path.split("/")[0]]
        return {"data": [{"name": "views", "values": [{"value": v}]}, {"name": "likes", "values": [{"value": 2}]},
                         {"name": "replies", "values": [{"value": 1}]}]}
    if params.get("metric") == "clicks":
        return {"data": [{"name": "clicks", "link_total_values": [{"value": 3, "link_url": "https://a.r10.to/abc"},
                                                                  {"value": 9, "link_url": "https://a.r10.to/zzz"}]}]}
    if params.get("metric") == "views":
        return {"data": [{"name": "views", "values": [{"value": 7, "end_time": "2030-01-01T08:00:00+0000"}]}]}
    if params.get("metric") == "followers_count":
        return {"data": [{"name": "followers_count", "total_value": {"value": 12}}]}
    raise AssertionError(path)


class LearnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = T.DATA, T.LOG
        T.DATA = Path(self.tmp.name)
        T.LOG = T.DATA / "log.txt"

    def tearDown(self):
        T.DATA, T.LOG = self.saved
        self.tmp.cleanup()

    def test_collect_own(self):
        c = T.Client("tok", call=fake_call)
        c._uid = "me"
        items = [{"id": "a", "status": "投稿済み", "posted_ids": ["p1", "p2"], "posted_at": T.now().isoformat(),
                  "parts": ["つかみ", "PR｜\nhttps://a.r10.to/abc"]},
                 {"id": "b", "status": "候補", "parts": ["x"]}]
        self.assertEqual(L.collect_own(c, items), 1)
        m = items[0]["metrics"]
        self.assertEqual((m["views"], m["likes"], m["replies"], m["clicks"]), (100, 4, 1, 3))  # 返信は自分の2本目を除いた1件
        self.assertNotIn("metrics", items[1])
        acct = L.load(L.OWN_FILE, {})
        self.assertEqual(list(acct["followers"].values()), [12])
        self.assertEqual(acct["days"]["2030-01-01"], {"views": 7})

    def test_topic_tag_only_on_first_part(self):
        sent = []

        def call(method, path, params, token, base=None):
            sent.append(dict(params))
            return {"id": f"c{len(sent)}"}

        c = T.Client("tok", call=call, sleep=lambda s: None, wait=0)
        c._uid = "me"
        it = {"id": "a", "parts": ["つかみ", "PR｜\nhttps://a.r10.to/x"], "topic": "#暮らし.の&知恵"}
        T.post_item(c, it)
        posts = [p for p in sent if "text" in p]
        self.assertEqual(posts[0].get("topic_tag"), "暮らしの知恵")
        self.assertNotIn("topic_tag", posts[1])

    def test_num_and_merge(self):
        self.assertEqual([L.num(x) for x in ("1.2万", "3,456", "12", "", "K")], [12000, 3456, 12, 0, 0])
        old = (T.now() - timedelta(days=40)).isoformat()
        store = {"old": {"link": "old", "seen_at": old}}
        posts = [{"link": "/@x/post/1", "user": "x"}, {"link": "/@noborog.life/post/2", "user": "noborog.life"},
                 {"link": "", "user": "y"}]
        out = L.merge_others(store, posts)
        self.assertEqual(list(out), ["/@x/post/1"])  # 古い物・自分・リンクなしは残さない

    def test_analyze_feeds_plan(self):
        import threads_plan as P
        items = [{"id": "a", "status": "投稿済み", "posted_at": T.now().isoformat(), "parts": ["つかみ"],
                  "title": "紹介", "metrics": {"views": 10, "clicks": 1}}]
        L.save(L.OTHERS_FILE, {"/@x/post/1": {"link": "/@x/post/1", "time": T.now().isoformat(), "likes": 50,
                                               "replies": 3, "reposts": 0, "media": 1, "source": "検索", "text": "型"}})
        seen = {}

        def ask(prompt, cfg):
            seen["prompt"] = prompt
            return {"summary": "まだ少ない", "numbers": "表示10", "next_rules": ["12時は質問型"],
                    "steal": [{"from": "自己紹介", "pattern": "短い自己紹介", "how": "固定する"}]}

        L.analyze({}, items, ask=ask)
        self.assertIn('"views": 10', seen["prompt"])
        self.assertIn('"likes": 50', seen["prompt"])
        self.assertIn("12時は質問型", (T.DATA / L.LEARN_MD).read_text(encoding="utf-8"))
        prompt = P.build_prompt([], T.now(), {})
        self.assertIn("これまでの成績から決めたこと", prompt)
        self.assertIn("短い自己紹介 → 固定する", prompt)


if __name__ == "__main__":
    unittest.main()


class AmazonTest(unittest.TestCase):
    def test_add_amazon_link(self):
        import threads as T
        it = {"id": "x", "parts": ["寒い夜に。", "PR｜向く人\n\n▽楽天市場の商品ページ\nhttps://a.r10.to/abc\n※11月20日時点 1,980円"]}
        T.add_amazon(it, "https://www.amazon.co.jp/某/dp/B0ABCDEFGH/ref=xyz", "noborog-22")
        self.assertIn("https://www.amazon.co.jp/dp/B0ABCDEFGH?tag=noborog-22", it["parts"][1])
        self.assertIn("▽楽天市場", it["parts"][1])
        self.assertEqual(T.check_rules(it["parts"]), [])
        T.add_amazon(it, "B0ZZZZZZZZ", "noborog-22")  # 付け直すと前のは消える
        self.assertEqual(it["parts"][1].count("▽Amazon"), 1)
        self.assertIn("B0ZZZZZZZZ", it["parts"][1])
        self.assertTrue(T.check_rules(["x", "PR｜x\nhttps://amzn.to/abc"]))  # Amazon と書いていない
        with self.assertRaises(T.ThreadsError):
            T.add_amazon(it, "ちがう", "noborog-22")


class SpreadTest(unittest.TestCase):
    def test_same_product_is_spread(self):
        import threads as T
        base = T.parse_time("2030-01-02T12:00")
        a = {"id": "a", "status": "承認済み", "time": base.isoformat(), "product": {"code": "box"}}
        b = {"id": "b", "status": "候補", "product": {"code": "box"}}
        c = {"id": "c", "status": "候補", "product": {"code": "other"}}
        items = [a, b, c]
        self.assertEqual(T.spread_time(items, b, base, 4), base + T.timedelta(hours=9))  # 12時は枠でない・14時は4時間未満 → 21時
        self.assertEqual(T.spread_time(items, c, base, 4, min_gap_minutes=0, slots=["12:00"]), base)


class PaceTest(unittest.TestCase):
    def test_overflow_goes_to_next_free_slot(self):
        import threads as T
        day = "2030-01-02"
        items = [{"id": f"a{i}", "status": "承認済み", "time": T.parse_time(f"{day}T{hm}").isoformat(), "product": {}}
                 for i, hm in enumerate(T.PACE_SLOTS)]
        new = {"id": "n", "status": "候補", "product": {"code": "x"}}
        got = T.spread_time(items, new, T.parse_time(f"{day}T14:00"), 4, 3)
        self.assertEqual(got, T.parse_time("2030-01-03T10:00"))  # 3回で満員 → 次の日の朝10時
        got2 = T.spread_time(items[:1], new, T.parse_time(f"{day}T07:00"), 4, 3)
        self.assertEqual(got2, T.parse_time(f"{day}T14:00"))  # 枠でない7時 → 10時は埋まっている → 14時
