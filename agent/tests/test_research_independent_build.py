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

    def test_quality_gate_still_requires_competitive_sources(self):
        name = "比較証拠が必要な完成判定"
        self.add(name)
        bundle = app.development_design_reference_bundle(name, "調査待ち")
        self.assertFalse(app.competitive_design_ready(bundle))

    def test_related_design_references_need_not_be_exact_competitors(self):
        name = "独自の家族旅行計画アプリ"
        urls = app.competitive_reference_candidates(name)[:2]
        patterns = [
            dict(source_url=url, evidence_type="official_text",
                 pattern="参考サービスにある機能情報のまとまりを確認する。",
                 adapt="家族の希望を整理する用途へ情報のまとまりを取り入れる。",
                 improvement="家族の到着時刻や休憩条件に合わせた提案を加える。",
                 acceptance="条件を入力し希望に沿う候補と旅程が表示されるか試す。")
            for url in urls
        ]
        brief = dict(
            policy=app.COMPETITIVE_POLICY,
            sources=[dict(url=url, content_sha="a" * 64) for url in urls],
            comparisons=[
                dict(source_url=url, reference_type="design_reference",
                     relevance="旅行の一覧や共有画面の設計を考える参考事例。",
                     comparison="完全一致の競合ではなく、家族向け機能の設計参考として活用する。")
                for url in urls
            ],
            design_patterns=patterns,
        )
        self.assertTrue(app.competitive_design_ready(brief))

    def test_blueprint_compiler_recovers_after_ai_design_contract_failure(self):
        name = "小規模事業者向け照合アプリ"
        spec = app.validate_product_spec(dict(
            audience="毎月の売上CSVを照合する小規模EC事業者",
            requested_outcome="異なる形式の売上CSVを揃えて差異と未確認行を確認する",
            differentiation="表計算の関数を組まずに差異の理由候補と確認順を見つける",
            workflow=["2つのCSVを読み込む", "照合条件を選ぶ", "差異一覧を確認して出力する"],
            must_have=["異なる列名の対応付け", "金額と注文番号での照合", "未一致行と重複行の区別"],
            acceptance=["読み込んだ列を対応付けできる", "異なる金額の行を差異として示す", "照合結果をCSV出力できる"],
            delivery_mode="browser_local", dependencies=[]
        ))
        app.store_product_spec(name, spec)
        with patch.object(app, "ensure_competitive_brief", return_value={}), \
             patch.object(app, "get_product_blueprint", return_value=None), \
             patch.object(app, "ai_json", side_effect=app.AutoQAPlanError("画面設計のJSONが不完全です")):
            result = app.ensure_product_blueprint(name, dict(app.DEFAULT), allow_unverified=True)

        self.assertEqual(result["design_method"], "requirements_compiler_fallback")
        self.assertIn(spec["audience"], result["user_scene"])
        self.assertIn(spec["workflow"][0], result["first_action"])
        covered = {i for flow in result["core_flows"] for i in flow["acceptance"]}
        self.assertEqual(covered, set(range(len(spec["acceptance"]))))
        self.assertFalse(app.production_acceptance(name, "0" * 64))


if __name__ == "__main__":
    unittest.main()
