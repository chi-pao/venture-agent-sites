import tempfile
import unittest
from pathlib import Path

from test_preview import app
from test_quality_continuation import blueprint_fixture


class FeaturePlanCompilerTests(unittest.TestCase):
    def test_rebuilds_product_specific_feature_plan_for_each_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            old_db, old_out = app.DB, app.OUT
            try:
                app.DB = Path(directory) / 'test.db'
                app.OUT = Path(directory) / 'out'
                app.OUT.mkdir()
                app.init()
                name = 'AI駆動型のデータ分析サービス'
                app.execute(
                    'INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',
                    (name, app.now(), app.now()),
                )
                spec = dict(
                    audience='毎月の売上データを整理する小規模事業者',
                    requested_outcome='売上CSVの傾向と確認点を見つけ、次の対応を決める',
                    differentiation='CSVを読み込んで条件別集計から次の行動まで一続きで確認できる',
                    workflow=['CSVを読み込む', '集計条件を選ぶ', '結果を保存して共有する'],
                    must_have=['CSV列の対応付け', '期間別・商品別の集計', '結果の保存とCSV出力'],
                    acceptance=['CSV読込', '期間と商品を変えて集計結果を比較できる', '結果と次の対応を保存・出力できる'],
                    delivery_mode='browser_local', dependencies=[],
                )
                app.store_product_spec(name, spec)
                blueprint = blueprint_fixture(name)
                plan = app.implementation_plan_from_requirements(name, app.get_product_spec(name), blueprint, '構造化出力失敗')
                app.validate_implementation_plan(plan, app.get_product_spec(name), blueprint)
                self.assertEqual(plan['design_method'], 'requirements_compiler_fallback')
                self.assertEqual({feature['acceptance_index'] for feature in plan['features']}, {0, 1, 2})
                self.assertIn('集計結果', plan['features'][1]['name'])
                self.assertEqual(len(plan['features']), len(spec['acceptance']))
                self.assertGreaterEqual(len(plan['features'][0]['name']), 20)
                self.assertNotIn('記録一覧だけ', plan['features'][0]['processing'])
                short_blueprint = blueprint_fixture(name)
                short_blueprint['screen_sections'] = [
                    dict(purpose='初回', action='入力', result='結果'),
                    dict(purpose='作業中', action='処理', result='状況'),
                    dict(purpose='完了後', action='保存', result='記録'),
                ]
                short_plan = app.implementation_plan_from_requirements(
                    name, app.get_product_spec(name), short_blueprint, '短い画面名の境界テスト'
                )
                app.validate_implementation_plan(short_plan, app.get_product_spec(name), short_blueprint)
                self.assertTrue(all(len(link['purpose']) >= 12 for link in short_plan['screen_links']))
                self.assertTrue(all(len(link['next_action']) >= 12 for link in short_plan['screen_links']))
            finally:
                app.DB, app.OUT = old_db, old_out


if __name__ == '__main__':
    unittest.main()
