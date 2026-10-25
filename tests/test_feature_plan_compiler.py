import tempfile
import unittest
import json
import urllib.error
from unittest.mock import patch
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


    def test_ai_timeout_compiles_plan_and_generic_online_class_stays_local(self):
        with tempfile.TemporaryDirectory() as directory:
            old_db, old_out = app.DB, app.OUT
            try:
                app.DB = Path(directory) / 'test.db'
                app.OUT = Path(directory) / 'out'
                app.OUT.mkdir()
                app.init()
                name = 'オンライン授業参加管理アプリ'
                app.execute(
                    'INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',
                    (name, app.now(), app.now()),
                )
                spec = dict(
                    audience='個人講師と少人数スクールの管理者',
                    requested_outcome='授業単位の出欠と集計を短い操作で記録する',
                    differentiation='出欠入力から出席率・CSV出力まで一画面で完了する',
                    workflow=['受講者を登録する', '授業の出欠を記録する', '集計とCSVを確認する'],
                    must_have=['名簿登録', '授業ごとの出欠', '出席率集計と保存'],
                    acceptance=['受講者を登録・修正できる', '出欠入力で出席率が再計算される', '再読込後も記録を確認してCSV出力できる'],
                    delivery_mode='browser_local', dependencies=[],
                )
                app.store_product_spec(name, spec)
                old_spec = dict(app.get_product_spec(name),
                    dependencies=['授業配信サービスとの出欠連携（手動登録は単独利用可能）'],
                    delivery_mode='connected')
                app.execute('UPDATE venture_product_specs SET spec=? WHERE idea=?',
                    (json.dumps(old_spec, ensure_ascii=False), name))
                recovered = app.ensure_product_spec(name, dict(app.DEFAULT))
                self.assertEqual(recovered['dependencies'], [])
                self.assertEqual(recovered['delivery_mode'], 'browser_local')
                blueprint = blueprint_fixture(name)
                with patch.object(app, 'ai_json', side_effect=TimeoutError('model request timed out')):
                    plan = app.ensure_implementation_plan(name, dict(app.DEFAULT), blueprint)
                self.assertEqual(plan['design_method'], 'requirements_compiler_fallback')
                self.assertEqual(len(plan['features']), len(spec['acceptance']))
                self.assertTrue(app.get_implementation_plan(name))
            finally:
                app.DB, app.OUT = old_db, old_out


    def test_http_400_compiles_and_persists_product_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            old_db, old_out = app.DB, app.OUT
            try:
                app.DB = Path(directory) / 'test.db'
                app.OUT = Path(directory) / 'out'
                app.OUT.mkdir()
                app.init()
                name = '在宅ワーク支援アプリ'
                rationale = {
                    'category': '個人の業務効率化',
                    'target_customer': '在宅勤務者やフリーランス',
                    'customer_pain': '予定時間と実績時間が別々で超過に気づきにくい',
                    'hypothesis': '予定・実績・休憩を一画面で管理し、残り時間を計算する',
                    'differentiation': '休憩を引いた稼働可能時間と予定・実績の差を同じ日付で確認する',
                    'mvp_scope': '日付・開始終了・休憩の入力、稼働可能時間と差分計算、検索・保存・CSV出力',
                }
                app.execute(
                    'INSERT INTO autonomous_ideas(name,rationale,attempts,created,updated) VALUES(?,?,1,?,?)',
                    (name, json.dumps(rationale, ensure_ascii=False), app.now(), app.now()),
                )
                failure = urllib.error.HTTPError('http://localhost:11434/api/generate',400,'Bad Request',{},None)
                with patch.object(app, 'ai_json', side_effect=failure):
                    spec = app.ensure_product_spec(name, dict(app.DEFAULT))
                self.assertEqual(spec['requirements_method'], 'requirements_compiler_fallback')
                self.assertIn('在宅勤務者', spec['audience'])
                self.assertIn('休憩', ' '.join(spec['must_have']))
                self.assertGreaterEqual(len(spec['workflow']), 3)
                self.assertGreaterEqual(len(spec['acceptance']), 3)
                self.assertEqual(app.get_product_spec(name)['requirements_method'], 'requirements_compiler_fallback')
            finally:
                app.DB, app.OUT = old_db, old_out


    def test_http_400_ux_design_uses_requirements_blueprint(self):
        with tempfile.TemporaryDirectory() as directory:
            old_db, old_out = app.DB, app.OUT
            try:
                app.DB = Path(directory) / 'test.db'
                app.OUT = Path(directory) / 'out'
                app.OUT.mkdir()
                app.init()
                name = 'オンライン授業参加管理アプリ'
                rationale = {
                    'target_customer': '個人講師と少人数スクール',
                    'customer_pain': '授業ごとの出欠を手作業で集計する',
                    'hypothesis': '出欠記録と集計を短い操作で完了する',
                    'differentiation': '名簿・授業・出欠・集計を一画面でつなぐ',
                    'mvp_scope': '受講者名簿、授業ごとの出欠、出席率集計と保存',
                }
                app.execute(
                    'INSERT INTO autonomous_ideas(name,rationale,attempts,created,updated) VALUES(?,?,1,?,?)',
                    (name, json.dumps(rationale, ensure_ascii=False), app.now(), app.now()),
                )
                spec = app.store_product_spec(name, {
                    'audience': rationale['target_customer'],
                    'requested_outcome': rationale['customer_pain'],
                    'differentiation': rationale['differentiation'],
                    'workflow': ['受講者を登録する','授業の出欠を記録する','集計を確認する'],
                    'must_have': ['名簿','授業ごとの出欠','出席率集計'],
                    'acceptance': ['登録できる','出欠で集計が変わる','保存・再読込できる'],
                    'delivery_mode': 'browser_local', 'dependencies': [],
                })
                brief=blueprint_fixture(name)
                failure = urllib.error.HTTPError('http://localhost:11434/api/generate',400,'Bad Request',{},None)
                with patch.object(app, 'ai_json', side_effect=failure):
                    blueprint = app.ensure_product_blueprint(name, dict(app.DEFAULT),
                        allow_unverified=True, competitive_brief=brief)
                self.assertEqual(blueprint['design_method'], 'requirements_compiler_fallback')
                self.assertTrue(blueprint['screen_sections'])
                self.assertTrue(blueprint['core_flows'])
            finally:
                app.DB, app.OUT = old_db, old_out


if __name__ == '__main__':
    unittest.main()
