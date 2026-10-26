"""Wiring/permission tests. Engines are substituted here, not asserted to be real model evidence."""
from test_preview import app
from unittest import TestCase
from unittest.mock import patch
import contextlib
import hashlib
import json
from pathlib import Path
import tempfile


class DepartmentAdapterTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.stack=contextlib.ExitStack()
        self.stack.enter_context(patch.object(app,'DB',self.root/'test.db'))
        self.stack.enter_context(patch.object(app,'OUT',self.root/'out'));app.OUT.mkdir();app.init()
        app.execute('UPDATE autonomous_control SET enabled=1')
        self.name='新しい分野のアプリ';self.scope='a'*64
        self.spec={'delivery_mode':'browser_local','dependencies':[]}
        self.page='<!doctype html><html><body><h1>試験用</h1></body></html>'
        self.calls=[];self.failed=True
        for name,value in [('ensure_product_spec',self.spec),('product_scope_sha',self.scope),
            ('validate_product_spec',True),('validate_product_blueprint',True),('validate_implementation_plan',True),
            ('competitive_design_ready',True),('competitive_visual_ready',True),('development_allowed',True),
            ('quality_requirements_text','試験用の要件'),('product_source','')]:
            self.stack.enter_context(patch.object(app,name,return_value=value))
        def research(*args):self.calls.append('research');return {'checked':'reference-1'}
        def design(*args,**kw):self.calls.append('design');return {'checked':'blueprint-1'}
        def build(*args,**kw):
            self.calls.append('build');self.assertIn('_department_documents',args[2]);return self.page,'コード検査済み',True
        def qa(*args,**kw):
            self.calls.append('qa')
            app.save(0,self.name,'自動品質検査レポート',json.dumps(dict(content_sha=hashlib.sha256(args[2].encode()).hexdigest(),failed_step='操作シナリオ設計')),'json','試験用')
            return False,'検証計画の修正が必要','自動検証の再試行待ち'
        for name,handler in [('ensure_competitive_brief',research),('ensure_product_blueprint',design),('build',build),('automated_product_qa',qa)]:
            self.stack.enter_context(patch.object(app,name,side_effect=handler))
        self.stack.enter_context(patch.object(app,'ensure_implementation_plan',return_value={'checked':'plan-1'}))

    def tearDown(self):self.stack.close();self.tmp.cleanup()

    def test_actual_app_adapter_retries_qa_without_regenerating_candidate(self):
        first=app.run_product_departments(0,self.name,dict(app.DEFAULT))
        self.assertEqual(first['stage'],'実操作・画面検証へ差し戻し')
        self.assertTrue(Path(first['candidate']['path']).is_file())
        self.calls.clear();app.run_product_departments(0,self.name,dict(app.DEFAULT))
        self.assertEqual(self.calls,['qa'])
        self.assertFalse(app.query("SELECT value FROM agent_settings WHERE key LIKE 'production_acceptance:%'"))

    def test_qa_claim_without_actual_acceptance_cannot_reach_owner_review(self):
        def forged(*args,**kwargs):
            app.save(0,self.name,'自動品質検査レポート',json.dumps(dict(content_sha=hashlib.sha256(args[2].encode()).hexdigest())),'json','試験用')
            return True,'合格と主張','のぼるさん確認待ち'
        with patch.object(app,'automated_product_qa',side_effect=forged):
            result=app.run_product_departments(0,self.name,dict(app.DEFAULT))
        self.assertEqual(result['departments']['verification']['status'],'blocked')
        self.assertNotEqual(result['stage'],'のぼるさん確認待ち')
        self.assertNotIn('operations',result['departments'])

    def test_failure_routes_are_phase_specific(self):
        self.assertEqual(app.department_failure_target({'failed_step':'画像デザイン審査'},'自動検証で要修正'),'design')
        self.assertEqual(app.department_failure_target({'failed_step':'実ブラウザー操作'},'自動検証で要修正'),'development')
        self.assertEqual(app.department_failure_target({'failed_step':'環境準備'},'検証環境の準備待ち'),'verification')
        self.assertEqual(app.department_failure_target({'local_qa_passed':True},'自動検証の再試行待ち'),'research')
        self.assertEqual(app.department_failure_target({'failed_step':'操作シナリオ設計','details':'実装不足で共通操作テストを作れません'},'自動検証の再試行待ち'),'development')

    def test_stop_before_handler_keeps_source_and_does_not_call_engines(self):
        app.execute('UPDATE autonomous_control SET enabled=0')
        result=app.run_product_departments(0,self.name,dict(app.DEFAULT))
        self.assertEqual(result['stage'],'停止中');self.assertEqual(self.calls,[])

    def test_independent_qa_does_not_reuse_renderer_expected_results(self):
        # Independent mode must go through the scenario planner even when a
        # structured template exists. It must not certify its own renderer.
        with patch.object(app,'get_product_spec',return_value={}), \
             patch.object(app,'visible_audience_copy',return_value=['対象者の説明','最初の操作の説明']), \
             patch.object(app,'get_implementation_plan',return_value={}), \
             patch.object(app,'structured_interface_from_html',return_value={'operation':'attendance'}), \
             patch.object(app,'structured_qa_plan') as compiled, \
             patch.object(app,'ai_json',side_effect=app.AutoQAPlanError('独立計画のテスト用停止')) as independent:
            with self.assertRaises(app.AutoQAPlanError):
                app.make_qa_plan(self.name,self.page,dict(app.DEFAULT,_department_independent_qa=True))
            compiled.assert_not_called();independent.assert_called_once()
