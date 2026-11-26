# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import threads as T  # noqa: E402
import threads_replies as R  # noqa: E402


class RepliesTest(unittest.TestCase):
    def test_only_unanswered_from_others(self):
        conv = [{"id": "1", "username": "a", "text": "x"},
                {"id": "2", "username": "me", "replied_to": {"id": "1"}},
                {"id": "3", "username": "b", "text": "y"},
                {"id": "4", "username": "c", "text": "z"}]
        got = [x["id"] for x in R.new_replies(conv, "me", known={"4"})]
        self.assertEqual(got, ["3"])

    def test_reply_not_counted_per_day(self):
        items = [{"status": "投稿済み", "posted_at": "2026-11-24T10:00", "kind": "返信"},
                 {"status": "投稿済み", "posted_at": "2026-11-24T10:00"}]
        self.assertEqual(T.posted_today(items, "2026-11-24"), 1)

    def test_reply_goes_under_their_comment(self):
        calls = []

        class C:
            def create(self, text, reply_to, images, topic):
                calls.append((reply_to, images, topic))
                return "c"

            def publish(self, cid):
                return "p1"

        it = {"id": "R1-x", "kind": "返信", "parts": ["ありがとうございます"], "reply_to": "their"}
        T.post_item(C(), it)
        self.assertEqual(calls, [("their", [], None)])
        self.assertEqual(it["status"], "投稿済み")


if __name__ == "__main__":
    unittest.main()
