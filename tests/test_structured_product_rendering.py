"""Regression checks for the shared structured product renderer."""
import tempfile
import unittest
from pathlib import Path

from test_quality_continuation import app


class StructuredProductRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        app.DB = root / "test.db"
        app.OUT = root / "out"
        app.OUT.mkdir()
        app.init()

    def tearDown(self):
        self.tmp.cleanup()

    def test_attendance_and_workday_structured_pages_have_valid_javascript(self):
        cases = (
            ("オンライン授業参加管理アプリ", {"requested_outcome": "名簿から出欠を集計する", "must_have": ["名簿", "出欠", "集計"]}),
            ("在宅ワーク支援アプリ", {"requested_outcome": "予定と実績時間を管理する", "must_have": ["予定時間", "実績時間", "超過計算"]}),
        )
        for name, details in cases:
            with self.subTest(name=name):
                spec = dict(
                    audience="小規模な利用者",
                    differentiation="中心作業の入力から結果までを整理する",
                    workflow=["入力する", "結果を見る", "保存して読み直す"],
                    acceptance=["入力と結果を確認する", "保存と復元を確認する"],
                    delivery_mode="browser_local",
                    dependencies=[],
                    **details,
                )
                item = app.deterministic_product_interface(name, spec)
                page = app.render_product_interface(name, item, spec)
                errors = app.validate_html(page, name)
                self.assertEqual(errors, [], "\\n".join(errors))
                self.assertIn("String.fromCharCode(13,10)", page)


if __name__ == "__main__":
    unittest.main()
