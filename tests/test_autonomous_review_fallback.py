import tempfile
import unittest
from pathlib import Path

from test_preview import app


class AutonomousReviewFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        app.DB = root / "review.db"
        app.OUT = root / "out"
        app.OUT.mkdir()
        app.init()
        self.name = "在宅ワーク時間・作業管理"
        self.spec = {
            "audience": "在宅勤務者やフリーランス",
            "requested_outcome": "稼働枠と作業の予定・実績を照合する",
            "differentiation": "休憩を引いた稼働枠と実績差を一画面で確認する",
            "workflow": ["日付と稼働時間を入力する", "作業予定と実績を比較する", "結果を保存して見直す"],
            "must_have": ["入力", "比較", "保存"],
            "acceptance": ["予定と実績の差が正しく出る", "稼働枠の超過を表示する", "保存後に記録を復元する"],
            "delivery_mode": "browser_local",
            "dependencies": [],
        }
        app.store_product_spec(self.name, self.spec)

    def tearDown(self):
        self.tmp.cleanup()

    def test_competitive_brief_uses_exact_official_text_and_marks_limits(self):
        refs = [
            {
                "url": "https://clockify.me/features/",
                "status": "本文取得",
                "checked_at": app.now(),
                "content_sha": "a" * 64,
                "text": "Clockify features. Track time, organize projects, monitor tasks and export detailed reports for teams and individuals.",
            },
            {
                "url": "https://toggl.com/features",
                "status": "本文取得",
                "checked_at": app.now(),
                "content_sha": "b" * 64,
                "text": "Toggl features include time tracking, capacity planning, project reporting and workload visibility for teams.",
            },
        ]
        brief = app.deterministic_competitive_brief(self.name, refs)
        self.assertTrue(app.competitive_design_ready(brief))
        self.assertEqual(len(brief["comparisons"]), 2)
        for comparison, ref in zip(brief["comparisons"], refs):
            self.assertIn(comparison["source_quote"], ref["text"])
            self.assertIn("実画面", comparison["comparison"])
        self.assertFalse(brief["measured_advantage"])
        self.assertIn("実操作", brief["research_gaps"][0])

    def make_layout(self, width):
        return {
            "width": width,
            "overflow": False,
            "smallControls": [],
            "tinyText": 0,
            "heading": "在宅ワーク時間・作業管理",
            "controls": 12,
            "body": "在宅勤務者やフリーランスが使う画面。日付と稼働時間を入力する",
        }

    def make_scenarios(self):
        return [
            {"kind": "feature", "acceptance_index": i, "case_index": j, "width": width, "passed": True}
            for i in range(len(self.spec["acceptance"]))
            for j in (0, 1)
            for width in (1280, 390)
        ]

    def make_page(self):
        return """<!doctype html><html><head><style>
        body{display:grid;gap:20px;color:#222;background:#f5f5f5}
        section{border-radius:16px;box-shadow:0 2px #ddd;background:linear-gradient(#fff,#eee)}
        .hero{color:#234}.card{color:#345}.result{color:#567}
        </style></head><body><main>
        <h1>在宅ワーク時間・作業管理</h1><h2>稼働枠を入力</h2><h3>結果を保存</h3>
        <section>対象者と使い方</section><section>入力と比較</section><section>保存と結果</section>
        </main></body></html>"""

    def test_browser_metrics_fallback_requires_pc_mobile_and_all_acceptance_cases(self):
        browser = {
            "passed": True,
            "layouts": [self.make_layout(w) for w in (1280, 1280, 390, 390)],
            "scenarios": self.make_scenarios(),
        }
        plan = {"audience_quotes": ["在宅勤務者やフリーランス", "日付と稼働時間を入力する"]}
        visual = app.review_qa_images_programmatic(self.name, browser, self.make_page(), plan)
        self.assertEqual(visual["review_mode"], "programmatic_browser_metrics")
        for key in ("audience", "design", "readability", "mobile", "usefulness"):
            self.assertEqual(visual[key]["score"], 4)
        self.assertIn("主観評価を保証しない", visual["limitations"])

        browser["layouts"][2]["overflow"] = True
        browser["scenarios"].pop()
        failed = app.review_qa_images_programmatic(self.name, browser, self.make_page(), plan)
        self.assertLess(failed["mobile"]["score"], 4)
        self.assertLess(failed["usefulness"]["score"], 4)


if __name__ == "__main__":
    unittest.main()
