"""Requirements-driven recovery for implementation plans."""
import unittest
from unittest.mock import patch

import test_system_baseline as baseline

app = baseline.app


class RequirementsPlanFallbackTests(unittest.TestCase):
    def setUp(self):
        baseline.FrameworkTests.setUp(self)

    def tearDown(self):
        baseline.FrameworkTests.tearDown(self)

    def test_ai_failure_compiles_a_feature_for_each_product_acceptance(self):
        name = "小規模事業者向け売上CSV分析"
        self.add(name)
        spec = app.validate_product_spec(dict(
            audience="毎月の売上CSVを確認する小規模EC事業者",
            requested_outcome="売上傾向と確認点を把握して次の対応を決める",
            differentiation="CSV読み込みから条件別集計、対応判断までを一続きで行う",
            workflow=["CSVを読み込む", "期間と商品を選ぶ", "集計結果を保存して出力する"],
            must_have=["CSV列の対応付け", "期間別・商品別の集計", "結果と対応判断の保存"],
            acceptance=[
                "CSVの列を対応付けて読み込める",
                "期間と商品を変えて集計結果を比較できる",
                "集計結果と次の対応を保存・出力できる",
            ],
            delivery_mode="browser_local",
            dependencies=[],
        ))
        app.store_product_spec(name, spec)
        brief = app.development_design_reference_bundle(name, "比較資料は調査中")
        blueprint = app.blueprint_from_product_requirements(name, spec, brief, "画面設計の再構成")
        with patch.object(app, "ai_json",
                          side_effect=app.AutoQAPlanError("architectureを構造化できません")):
            plan = app.ensure_implementation_plan(name, dict(app.DEFAULT), blueprint)

        app.validate_implementation_plan(plan, spec, blueprint)
        self.assertEqual(plan["design_method"], "requirements_compiler_fallback")
        self.assertEqual(
            {feature["acceptance_index"] for feature in plan["features"]},
            set(range(len(spec["acceptance"]))),
        )
        self.assertEqual(len(plan["features"]), len(spec["acceptance"]))
        self.assertIn("期間と商品", plan["features"][1]["user_action"])
        self.assertEqual(len(plan["screen_links"]), len(blueprint["screen_sections"]))


if __name__ == "__main__":
    unittest.main()
