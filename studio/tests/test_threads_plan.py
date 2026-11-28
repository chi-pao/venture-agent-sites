# -*- coding: utf-8 -*-
"""投稿候補づくりのテスト（楽天にも AI にもつながない）。"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import affiliate as A  # noqa: E402
import threads as T  # noqa: E402
import threads_plan as P  # noqa: E402


def product(code, genre_rank=1, reviews=100, aff=True):
    return {"name": f"商品{code}", "price": 1980, "shop": "店", "url": f"https://hb.afl.rakuten.co.jp/x/{code}",
            "item_url": f"https://item.rakuten.co.jp/shop/{code}/", "is_affiliate": aff, "code": code,
            "rank": genre_rank, "caption": "説明", "catch": "", "postage": 0, "point_rate": 1,
            "reviews": reviews, "rating": 4.5, "image": ""}


def fetch(cfg, gid):
    if gid == 999:
        raise A.RakutenError("だめ")
    base = str(gid or 0)
    return [product(base + "-a"), product(base + "-b", reviews=3), product(base + "-c", aff=False),
            product("same")]


CFG = {"threads_genres": {"インテリア・寝具・収納": None, "家電": 1, "壊れ": 999}}
DAY = datetime(2030, 1, 2)


def answer(products):
    return {"candidates": [
        {"slot": "07:00", "kind": "毎日のおなじみ", "title": "ランキング", "product": None, "parts": ["今日のメモ"]},
        {"slot": "12:00", "kind": "紹介", "title": "紹介A", "product": 0,
         "hook": "つかみ", "pr_comment": "サイズを確かめてね",
         "target": {"誰に": "40代・共働き", "悩み": "朝が寒い", "どう助かるか": "タイマーつき"}, "style": "呼びかけ型"},
        {"slot": "19:00", "kind": "紹介", "title": "商品なし", "product": None, "parts": ["つかみ"]},
        {"slot": "15:00", "kind": "紹介", "title": "深掘り", "product": 1, "hook": "つかみ",
         "thread": ["選び方👇", "よくある失敗👇"], "pr_comment": "サイズを見てね"},
        {"slot": "19:00", "kind": "紹介", "title": "紹介B", "product": 1,
         "parts": ["つかみ https://example.com", "中身"]},
    ]}


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = T.LOG, T.DATA, T.QUEUE
        T.DATA = Path(self.tmp.name)
        T.LOG, T.QUEUE = T.DATA / "log.txt", T.DATA / "q.json"

    def tearDown(self):
        T.LOG, T.DATA, T.QUEUE = self.saved
        self.tmp.cleanup()

    def test_gather_filters_and_dedupes(self):
        products, errors = P.gather(CFG, [], fetch)
        codes = [p["code"] for p in products]
        self.assertEqual(sorted(codes), ["0-a", "1-a", "same"])  # レビュー少・リンクなし・重複は外す
        self.assertEqual(len(errors), 1)

    def test_recently_posted_skipped(self):
        items = [{"status": "投稿済み", "posted_at": T.now().isoformat(), "product": {"code": "0-a"}}]
        products, _ = P.gather(CFG, items, fetch)
        self.assertNotIn("0-a", [p["code"] for p in products])

    def test_make_adds_link_part_and_checks(self):
        captured = {}

        def ask(prompt, cfg):
            captured["prompt"] = prompt
            return answer(None)

        products, _ = P.gather(CFG, [], fetch)
        products = products * 2  # 4件以上にする
        new = P.to_items(ask("", CFG), products, DAY, datetime(2030, 1, 1))
        ids = [it["id"] for it in new]
        self.assertEqual(ids, ["0102-01", "0102-02", "0102-04", "0102-05"])  # 商品のない紹介は外す
        deep = new[2]
        self.assertEqual(len(deep["parts"]), 4)  # つかみ＋途中2本＋リンク
        self.assertTrue(deep["parts"][3].startswith("PR｜"))
        self.assertEqual(T.check_rules(deep["parts"]), [])
        new = [new[0], new[1], new[3]]
        promo = new[1]
        self.assertEqual(len(promo["parts"]), 2)
        self.assertTrue(promo["parts"][1].startswith("PR｜サイズを確かめてね"))
        self.assertEqual(T.media_index(promo), 0)  # 写真は1本目（つかみ）に付ける
        self.assertIn("▽楽天市場の商品ページ\n" + products[0]["url"], promo["parts"][1])
        self.assertIn("1月1日時点 1,980円・送料無料", promo["parts"][1])
        self.assertEqual(T.check_rules(promo["parts"]), [])
        self.assertTrue(T.check_rules(new[2]["parts"]))  # 1本目にリンク
        P.add_images(new, {}, get=lambda url, n: [f"https://img/{i}.jpg" for i in range(n)])
        self.assertEqual(len(promo["images"]), 6)
        self.assertNotIn("images", new[0])
        for it in new:
            it["problems"] = T.check_rules(it["parts"], it.get("images")) + it["problems"]
        md = P.review_md(new, DAY, [])
        self.assertIn("## 12:00", md)
        self.assertIn("⚠", md)
        self.assertIn("ねらい：誰に：40代・共働き", md)
        self.assertIn("まねた型：呼びかけ型", md)

    def test_prompt_has_rules_and_products(self):
        products, _ = P.gather(CFG, [], fetch)
        text = P.build_prompt(products, DAY, CFG)
        self.assertIn("使った体験は書かない", text)
        self.assertIn("商品0-a", text)
        self.assertNotIn("hb.afl", text)  # AI にはリンクを渡さない

    def test_past_products_reused(self):
        old = (T.now() - timedelta(days=5)).isoformat()
        items = [{"id": "a", "status": "投稿済み", "posted_at": old, "made_at": old, "parts": ["年末の片づけ、\n本文"],
                  "product": {"code": "c1", "name": "箱", "genre": "インテリア・寝具・収納", "price": 2680, "url": "https://a.r10.to/x"},
                  "metrics": {"views": 105, "clicks": 1}},
                 {"id": "b", "status": "投稿済み", "posted_at": old, "parts": ["x"],
                  "product": {"code": "c2", "name": "弱い", "genre": "インテリア・寝具・収納", "price": 1, "url": "https://a.r10.to/y"}, "metrics": {"views": 3}},
                 {"id": "c", "status": "投稿済み", "posted_at": T.now().isoformat(), "parts": ["x"],
                  "product": {"code": "c3", "name": "昨日", "genre": "インテリア・寝具・収納", "price": 1, "url": "https://a.r10.to/z"}, "metrics": {"views": 500}}]
        past = P.past_products(items, {})
        self.assertEqual([p["code"] for p in past], ["c1"])  # 反応が弱い物・出したばかりの物は外す
        self.assertEqual(past[0]["past"]["前の1本目の書き出し"], "年末の片づけ、")
        part = P.link_part(dict(past[0], postage=None), T.now())
        self.assertIn("https://a.r10.to/x", part)
        self.assertIn(f"{T.parse_time(old).month}月{T.parse_time(old).day}日時点", part)  # 価格は前に取った日
        text = P.build_prompt(past, DAY, CFG)
        self.assertIn("前に出したとき", text)
        self.assertIn("トピックタグ", text)
        self.assertIn("どう助かるか", text)

    def test_sold_product_repeats_often(self):
        old = (T.now() - timedelta(days=2, hours=1)).isoformat()
        items = [{"id": "s", "status": "投稿済み", "posted_at": old, "parts": ["片づけ\n本文"],
                  "product": {"code": "box", "name": "箱", "genre": "インテリア・寝具・収納", "price": 2680, "url": "https://a.r10.to/b",
                              "item_url": "https://item.rakuten.co.jp/shop/box/"}, "metrics": {"views": 0}}]
        report = {"order": {"rows": [{"item_url": "https://item.rakuten.co.jp/shop/box/"}]}}
        past = P.past_products(items, {}, sold=P.sold_counts(report))
        self.assertEqual([p["code"] for p in past], ["box"])  # 表示0でも、売れた物は2日あけば出す
        self.assertIn("1件", past[0]["past"]["楽天で売れた"])
        self.assertEqual(P.past_products(items, {}, sold={}), [])  # 売れていなければ出さない
        self.assertIn("楽天で売れた", P.build_prompt(past, DAY, CFG))
        items[0]["product"]["genre"] = "レディースファッション"
        self.assertEqual(P.past_products(items, {}, sold=P.sold_counts(report)), [])  # 決めたジャンル以外は、売れた物でも出さない

    def test_genre_share_and_filter(self):
        ps = [{"code": f"i{i}", "genre": "インテリア・寝具・収納"} for i in range(6)] +              [{"code": "d", "genre": "日用品雑貨・文房具・手芸"}, {"code": "k", "genre": "家電"},
              {"code": "x", "genre": "レディースファッション"}, {"code": "y", "genre": "キッチン用品・食器・調理器具"}]
        got = [g["code"] for g in P.mix_by_share(ps)]
        self.assertEqual(got, ["i0", "i1", "d", "i2", "i3", "k", "i4", "i5"])  # メイン2つ・サブ1つ、ほかのジャンルは入れない
        self.assertEqual(P.genre_group("寝具"), "インテリア")
        self.assertEqual(P.genre_group("総合（キッチン家電）"), "家電")
        self.assertIsNone(P.genre_group("メンズファッション"))

    def test_pick_uses_slot_time(self):
        day = (T.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        items = [{"id": "x", "status": "候補", "for_date": day, "slot": "12:00",
                  "parts": ["つかみ", "PR｜楽天市場の商品ページはこちら\nhttps://hb.afl.rakuten.co.jp/x"]},
                 {"id": "bad", "status": "候補", "for_date": day, "slot": "07:00", "parts": ["https://a.r10.to/x"]}]
        T.save_queue(items)
        T.cmd_pick(SimpleNamespace(ids=["x"]))
        got = T.find(T.load_queue(), "x")
        self.assertEqual(got["status"], "承認済み")
        self.assertTrue(got["time"].startswith(day + "T14:00"))  # 12時は投稿の枠でないので、次の枠（14時）へ
        with self.assertRaises(T.ThreadsError):
            T.cmd_pick(SimpleNamespace(ids=["bad"]))


class PreviewTest(unittest.TestCase):
    def test_page_shows_thread_and_card(self):
        import threads_preview as V
        it = {"id": "0102-03", "title": "紹介A", "kind": "紹介", "slot": "12:00",
              "parts": ["つかみ", "PR｜楽天市場の商品ページはこちら\nhttps://a.r10.to/abc\n※価格"]}
        cache = {"https://a.r10.to/abc": {"title": "【楽天市場】家具スライダー", "domain": "item.rakuten.co.jp"}}
        html = V.page([it], "見本", cache)
        self.assertIn("決まりチェック OK", html)
        self.assertIn("家具スライダー", html)
        self.assertNotIn("【楽天市場】", html)
        self.assertEqual(html.count('class="post'), 2)




class MediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = T.DATA
        T.DATA = Path(self.tmp.name)

    def tearDown(self):
        T.DATA = self.saved
        self.tmp.cleanup()

    def test_upload_only_approved(self):
        import threads_media as M
        (T.DATA / "media" / "a").mkdir(parents=True)
        (T.DATA / "media" / "a" / "a.jpg").write_bytes(b"x")
        (T.DATA / "media" / "b").mkdir(parents=True)
        (T.DATA / "media" / "b" / "b.jpg").write_bytes(b"y")
        items = [{"id": "a", "status": "承認済み", "card": {"local": "media/a/a.jpg", "url": None}},
                 {"id": "b", "status": "候補", "card": {"local": "media/b/b.jpg", "url": None}}]
        pushed = {}

        def push(stage, cfg):
            pushed["files"] = sorted(p.name for p in stage.iterdir())

        M.upload(items, {}, push=push, check=lambda url, n: True)
        self.assertIn("a.jpg", pushed["files"])
        self.assertNotIn("b.jpg", pushed["files"])
        self.assertIn("robots.txt", pushed["files"])
        self.assertEqual(items[0]["card"]["url"], M.HOST + "/a.jpg")
        self.assertIsNone(items[1]["card"]["url"])

    def test_card_spec_fallback(self):
        import threads_media as M
        it = {"id": "x", "kind": "毎日のおなじみ", "parts": ["おはようございます。昨日のメモ\n総合3位　トイレ\n総合27位　水"]}
        spec = M.card_spec(it)
        self.assertEqual(spec["style"], "ranking")
        self.assertEqual(spec["points"][0], "3位|トイレ")


class AIMediaTest(unittest.TestCase):
    """AI（ComfyUI）を使わずに、カードと動画の組み立てだけを確かめる。"""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = T.DATA
        T.DATA = Path(self.tmp.name)
        import threads_media as M
        self.M = M
        self.saved_dir = M.MEDIA_DIR
        M.MEDIA_DIR = T.DATA / "media"

    def tearDown(self):
        T.DATA = self.saved
        self.M.MEDIA_DIR = self.saved_dir
        self.tmp.cleanup()

    def test_card_and_video_with_fake_ai(self):
        from PIL import Image
        M = self.M

        class FakeAI:
            def start(self):
                pass

            def image(self, prompt, out, art="photo", seed=None):
                Image.new("RGB", (896, 1120), (120, 90, 60)).save(out)
                return out

            def video(self, start_image, prompt, out_dir, art="photo"):
                out_dir = Path(out_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                paths = []
                for i in range(12):
                    pth = out_dir / f"f{i:04d}.png"
                    Image.new("RGB", (704, 896), (100 + i * 5, 80, 60)).save(pth)
                    paths.append(pth)
                return paths

        photo = Image.new("RGB", (600, 600), (250, 250, 250))
        saved_fetch = M.fetch_image
        M.fetch_image = lambda url: photo
        try:
            items = [{"id": "x-01", "kind": "毎日のおなじみ", "parts": ["おはよう\n総合3位　トイレ"], "scene": "room"},
                     {"id": "x-02", "kind": "紹介", "parts": ["寒い夜、つらい人へ。", "PR｜…"], "scene": "bed",
                      "product": {"rank": 14, "genre": "家電"}, "images": ["https://img/1.jpg", "https://img/2.jpg"]},
                     {"id": "x-03", "kind": "紹介", "parts": ["ほこり、終わらない問題。", "PR｜…"], "scene": "dusty shelf",
                      "after": "clean shelf", "after_text": "なでた所だけ、つやっ",
                      "product": {"rank": 3}, "images": ["https://img/1.jpg"]}]
            made = M.make_for(items, ai=FakeAI())
        finally:
            M.fetch_image = saved_fetch
        self.assertEqual(made, ["x-01.jpg", "x-02-hook.jpg", "x-02.mp4", "x-03-ba.jpg", "x-03-ba.mp4"])
        self.assertTrue((T.DATA / "media" / "x-03" / "after.png").exists())  # 使った後の絵
        self.assertTrue((T.DATA / "media" / "x-03" / "clip_after").exists())
        self.assertTrue((T.DATA / items[1]["card"]["local"]).exists())  # 動画の日も、つかみの画像を作る
        self.assertTrue((T.DATA / items[1]["video"]["local"]).exists())
        self.assertTrue((T.DATA / "media" / "x-02" / "preview.mp4").exists())


if __name__ == "__main__":
    unittest.main()
