# -*- coding: utf-8 -*-
"""自動投稿のテスト。  python -m unittest tools/sns_autopost/test_post.py"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["AUTOPOST_DATA"] = str(TMP / "autopost")
os.environ["AUTOPOST_KEY_FILE"] = str(TMP / "key")
os.environ.pop("STUDIO_DISCORD_WEBHOOK", None)
(TMP / "key").write_text("test-key-not-secret", encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import post as P  # noqa: E402
import vault as V  # noqa: E402

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=P.JST)


class VaultTest(unittest.TestCase):
    def test_round_trip_and_file_is_not_plain(self):
        enc = TMP / "v" / "tokens.enc"
        V.save(enc, TMP / "key", {"youtube": {"refresh_token": "abc-secret"}})
        self.assertNotIn(b"abc-secret", enc.read_bytes())
        self.assertEqual(V.load(enc, TMP / "key")["youtube"]["refresh_token"], "abc-secret")

    def test_missing_file_is_empty(self):
        self.assertEqual(V.load(TMP / "none.enc", TMP / "key"), {})


class TikTokTest(unittest.TestCase):
    def setUp(self):
        P._VAULT.update(data={}, dirty=False)
        self.calls = []
        self._http = P.http

    def tearDown(self):
        P.http = self._http
        P._VAULT.update(data=None, dirty=False)

    def test_chunks(self):
        self.assertEqual(P.tiktok_chunks(33 * P.MB), (33 * P.MB, 1))
        self.assertEqual(P.tiktok_chunks(64 * P.MB), (64 * P.MB, 1))
        chunk, n = P.tiktok_chunks(105 * P.MB)
        self.assertEqual((chunk, n), (10 * P.MB, 10))  # 最後の1つが余りの5MBを含む

    def test_not_connected_is_skip(self):
        with self.assertRaises(P.Skip):
            P.tiktok_access(NOW)

    def test_refresh_rotates_and_saves(self):
        P._VAULT["data"]["tiktok"] = {
            "client_key": "k", "client_secret": "s", "access_token": "old", "refresh_token": "r1",
            "access_expires_at": (NOW - timedelta(minutes=1)).isoformat(),
            "refresh_expires_at": (NOW + timedelta(days=100)).isoformat()}

        def fake(method, url, **kw):
            self.calls.append((url, kw.get("form")))
            return 200, {}, {"access_token": "new", "refresh_token": "r2", "expires_in": 7200,
                             "refresh_expires_in": 15552000}
        P.http = fake
        self.assertEqual(P.tiktok_access(NOW), "new")
        self.assertEqual(self.calls[0][1]["refresh_token"], "r1")
        self.assertEqual(P._VAULT["data"]["tiktok"]["refresh_token"], "r2")
        self.assertTrue(P._VAULT["dirty"])

    def test_fresh_token_is_reused(self):
        P._VAULT["data"]["tiktok"] = {
            "access_token": "a", "refresh_token": "r",
            "access_expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "refresh_expires_at": (NOW + timedelta(days=100)).isoformat()}
        P.http = lambda *a, **k: self.fail("延長しなくてよい")
        self.assertEqual(P.tiktok_access(NOW), "a")


class YouTubeTest(unittest.TestCase):
    def setUp(self):
        P._VAULT.update(data={"youtube": {"client_id": "c", "client_secret": "s", "refresh_token": "r"}}, dirty=False)
        self.saved = (P.youtube_access, P.youtube_upload, P.youtube_status)
        P.youtube_access = lambda c: "tok"
        P.youtube_upload = lambda a, d, m: "VID1"
        (P.ROOT / "tmp_test_video.mp4").write_bytes(b"x")
        self.p = {"id": "T1", "title": "試し", "media": "tmp_test_video.mp4",
                  "youtube": {"title": "t", "description": "d"}}

    def tearDown(self):
        P.youtube_access, P.youtube_upload, P.youtube_status = self.saved
        (P.ROOT / "tmp_test_video.mp4").unlink()
        P._VAULT.update(data=None, dirty=False)

    def test_public_is_ok(self):
        P.youtube_status = lambda a, v: {"privacyStatus": "public", "uploadStatus": "uploaded"}
        r = P.post_youtube(self.p)
        self.assertEqual(r["id"], "VID1")
        self.assertNotIn("note", r)

    def test_private_is_reported(self):
        P.youtube_status = lambda a, v: {"privacyStatus": "private", "uploadStatus": "uploaded"}
        r = P.post_youtube(self.p)
        self.assertIn("公開になっていない", r["note"])
        self.assertIn("YouTube：公開になっていません", (TMP / "INBOX.md").read_text(encoding="utf-8"))


class RunTest(unittest.TestCase):
    def test_log_goes_to_private_place_and_notifies(self):
        posts = [{"id": "C9", "title": "動画", "at": "2026-11-28T11:00:00+09:00", "approved": "OK",
                  "platforms": ["youtube", "tiktok"]}]
        P.POSTS = TMP / "posts.json"
        P.POSTS.write_text(json.dumps(posts), encoding="utf-8")

        def tt(p):
            raise P.Skip("まだ")
        P.run(now=NOW, posters={"youtube": lambda p: {"id": "V", "url": "https://youtube.com/shorts/V"},
                                "tiktok": tt})
        log = json.loads((TMP / "autopost" / "log.json").read_text(encoding="utf-8"))
        self.assertTrue(log["C9"]["youtube"]["done"])
        self.assertEqual(log["C9"]["tiktok"]["note"], "まだ")
        self.assertIn("youtube：出しました", (TMP / "INBOX.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
