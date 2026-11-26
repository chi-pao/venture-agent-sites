# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import threads_cloud as C  # noqa: E402


def item(i, status="承認済み", changed=None, posted=None, **kw):
    it = {"id": i, "status": status, "parts": ["a"], **kw}
    if changed:
        it["changed_at"] = changed
    if posted is not None:
        it["posted_ids"] = posted
    return it


class MergeTest(unittest.TestCase):
    def test_cloud_post_result_comes_back(self):
        local = [item("a", changed="2026-11-23T07:40")]
        remote = [item("a", "投稿済み", "2026-11-28T10:01", ["p1", "p2"])]
        m = C.merge(local, remote)
        self.assertEqual(m[0]["status"], "投稿済み")
        self.assertEqual(m[0]["posted_ids"], ["p1", "p2"])

    def test_local_new_approval_wins(self):
        local = [item("a", "取り消し", "2026-11-24T09:00")]
        remote = [item("a", "承認済み", "2026-11-23T07:40")]
        self.assertEqual(C.merge(local, remote)[0]["status"], "取り消し")

    def test_posted_ids_never_lost(self):
        # 手元で後から触っても、クラウドが出した記録は残す（二重に出さない）
        local = [item("a", "承認済み", "2026-11-28T10:05")]
        remote = [item("a", "投稿済み", "2026-11-28T10:01", ["p1"], posted_at="x")]
        m = C.merge(local, remote)[0]
        self.assertEqual(m["status"], "投稿済み")
        self.assertEqual(m["posted_ids"], ["p1"])

    def test_new_items_on_both_sides_kept(self):
        m = C.merge([item("a"), item("b")], [item("c"), item("a")])
        self.assertEqual([x["id"] for x in m], ["a", "b", "c"])

    def test_no_changed_at_prefers_local(self):
        m = C.merge([item("a", "候補", text="local")], [item("a", "候補", text="cloud")])
        self.assertEqual(m[0]["text"], "local")


if __name__ == "__main__":
    unittest.main()
