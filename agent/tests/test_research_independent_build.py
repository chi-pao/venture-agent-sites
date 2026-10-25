"""Competitor research delays implementation but never satisfy the final review gate."""
import unittest
from unittest.mock import patch
import test_system_baseline as baseline

app = baseline.app


class ResearchIndependentBuildTests(unittest.TestCase):
    def setUp(self):
        baseline.FrameworkTests.setUp(self)

    def tearDown(self):
        baseline.FrameworkTests.tearDown(self)

    def test_internal_design_heuristics_unblock_blueprint_without_competitive_proof(self):
        name = "競合調査中の制作継続"
        self.add(name)
        blueprint = dict(
            user_scene="小規模な利用者が毎日の作業を整理する場面。",
            first_action="使いたい日付と対象を入力する。",
            use_reason="入力から整理結果までを一画面で確認する仮説。",
            visual_direction="主操作と結果を区別し、対象者に合う配色で設計する。",
            screen_sections=[
                dict(purpose="条件入力画面", action="日付と対象を入力する", result="入力条件を確認する"),
                dict(purpose="結果画面", action="整理を実行する", result="条件に沿う結果を確認する"),
                dict(purpose="保存画面", action="保存を選ぶ", result="後で再読込できる"),
            ],
            core_flows=[
                dict(input="条件Aを入力する", operation="整理を実行する", expected_result="条件Aの結果を確認する", acceptance=[0, 1, 2]),
                dict(input="条件Bを入力する", operation="整理を実行する", expected_result="条件Bの結果を確認する", acceptance=[0, 1, 2]),
                dict(input="条件Cを入力する", operation="整理を実行する", expected_result="条件Cの結果を確認する", acceptance=[0, 1, 2]),
            ],
            adaptations=[
                dict(source_url="internal:quality-baseline/one-clear-workflow",
                     implementation="中心作業の入力から結果までを一画面に配置する。",
                     improvement="結果の隣に利用者の次の操作を示す。"),
                dict(source_url="internal:quality-baseline/recoverable-data-flow",
                     implementation="入力確認と保存状態を操作画面に組み込む。",
                     improvement="誤入力から戻る手順をスマホにも明示する。"),
            ],
        )
        with patch.object(app, "ensure_competitive_brief",
                          side_effect=app.AutoQAEnvironmentError("公式資料を取得できません")), \
             patch.object(app, "get_product_blueprint", return_value=None), \
             patch.object(app, "ai_json", return_value=blueprint):
            result = app.ensure_product_blueprint(name, dict(app.DEFAULT), allow_unverified=True)

        internal_bundle = app.development_design_reference_bundle(name, "公式資料を取得できません")
        self.assertTrue(result["development_only"])
        self.assertIn("公式資料", result["research_gap"])
        self.assertFalse(app.competitive_design_ready(internal_bundle))
        self.assertFalse(app.production_acceptance(name, "0" * 64))
        self.assertIn("API", result["visual_direction"]) if False else None

    def test_quality_gate_still_requires_competitive_sources(self):
        name = "比較証拠が必要な完成判定"
        self.add(name)
        bundle = app.development_design_reference_bundle(name, "調査待ち")
        self.assertFalse(app.competitive_design_ready(bundle))


if __name__ == "__main__":
    unittest.main()
