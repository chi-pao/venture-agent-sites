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

    def test_every_registered_structured_pattern_has_valid_javascript(self):
        spec = dict(
            audience="小規模な利用者",
            requested_outcome="入力値を整理して、次の対応を判断する",
            differentiation="中心作業の入力から結果までを一画面で確認する",
            workflow=["対象の情報を入力する", "結果を確認して記録する", "保存した内容を後で見直す"],
            must_have=["必要な項目を入力する", "状況に応じた結果を表示する", "結果を保存して出力する"],
            acceptance=["必要情報を入力し、誤入力を修正できる", "異なる入力に応じて結果が変わる", "結果を保存・再読込・出力できる"],
            delivery_mode="browser_local",
            dependencies=[],
        )
        for operation, name in app.PRODUCT_PATTERN_PROBES.items():
            with self.subTest(operation=operation, name=name):
                item = app.deterministic_product_interface(name, spec)
                page = app.render_product_interface(name, item, spec)
                errors = app.validate_html(page, name)
                self.assertEqual(errors, [], "\\n".join(errors))
                self.assertIn("String.fromCharCode(13,10)", page)


if __name__ == "__main__":
    unittest.main()
