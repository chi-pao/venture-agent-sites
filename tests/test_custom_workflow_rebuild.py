import importlib.util
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name == 'tests' else HERE
SOURCE = ROOT / 'agent' / 'venture_agent_integrated.py'
if not SOURCE.is_file():
    SOURCE = ROOT / 'delivery' / 'venture_agent_integrated.py'
spec = importlib.util.spec_from_file_location('custom_workflow_app', SOURCE)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


class CustomWorkflowRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        app.DB = self.root / 'test.db'
        app.OUT = self.root / 'out'
        app.OUT.mkdir()
        app.init()
        self.name = '新規用途テスト'
        app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)', (self.name, app.now(), app.now()))
        self.spec = {'audience': '検証ユーザー', 'requested_outcome': '操作可能な試作',
                     'differentiation': '利用者の作業を入力から結果まで一画面で行う',
                     'workflow': ['入力する', '処理結果を見る', '保存して読み直す'],
                     'must_have': ['入力', '業務処理', '保存と復元'],
                     'acceptance': ['入力処理の確認', '結果表示の確認', '保存と復元の確認'],
                     'delivery_mode': 'browser_local', 'dependencies': []}
        app.store_product_spec(self.name, self.spec)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unregistered_workflow_is_generated_from_feature_contract(self):
        source = '<!doctype html><html lang="ja"><body><main><h1>旅行テスト</h1><button id="go">試す</button></main></body></html>'
        with patch.object(app, 'get_product_spec', return_value={'audience': '家族旅行者', 'acceptance': ['経路候補を比較', '旅程を保存']}), \
             patch.object(app, 'get_product_blueprint', return_value={'first_action': '出発地と到着希望時刻を入力'}), \
             patch.object(app, 'get_implementation_plan', return_value={'features': [{'name': '経路候補比較', 'inputs': '出発地と到着時刻'}]}), \
             patch.object(app, 'competitive_context', return_value={'brief': {'design_patterns': []}}), \
             patch.object(app, 'ai', return_value=source) as model, \
             patch.object(app, 'ensure_product_spec', return_value={}), \
             patch.object(app, 'validate_html', return_value=[]), \
             patch.object(app, 'ensure_autoqa_environment'), \
             patch.object(app, 'browser_test', return_value=(True, '実ブラウザ操作検査合格')), \
             patch.object(app, 'review_generated_product', return_value=(True, '用途と画面品質を確認')), \
             patch.object(app, 'save', return_value=self.root / 'candidate.html'), \
             patch.object(app, 'event'):
            page, detail, passed = app.open_workflow_rebuild(
                1, self.name, dict(app.DEFAULT), '事業計画', '試作品HTML', False,
                '既存の登録パターンでは要件を表せない')

        self.assertIn('id="go"', page)
        self.assertTrue(passed)
        self.assertIn('完成条件の実操作QAは次工程で確認', detail)
        prompt = model.call_args.args[0]
        self.assertIn('固定テンプレート・登録済みパターンへの当てはめは禁止', prompt)
        self.assertIn('機能別実装・テスト契約', prompt)
        self.assertIn('既存の登録パターンでは要件を表せない', prompt)

    def test_failed_custom_rebuild_never_claims_completion(self):
        with patch.object(app, 'get_product_spec', return_value=self.spec), \
             patch.object(app, 'get_product_blueprint', return_value={}), \
             patch.object(app, 'get_implementation_plan', return_value={}), \
             patch.object(app, 'competitive_context', return_value={}), \
             patch.object(app, 'ai', return_value='not html'), \
             patch.object(app, 'extract_html', side_effect=ValueError('HTMLを抽出できません')), \
             patch.object(app, 'event'):
            page, detail, passed = app.open_workflow_rebuild(
                1, self.name, dict(app.DEFAULT), '事業計画', '試作品HTML', False,
                '登録パターンなし')

        self.assertEqual(page, '')
        self.assertFalse(passed)
        self.assertIn('専用生成・検査を継続', detail)
