"""Control-plane tests; these deliberately do not claim real model/product quality."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'agent'/'department_manager.py'
spec=importlib.util.spec_from_file_location('departments',MODULE)
dm=importlib.util.module_from_spec(spec);spec.loader.exec_module(dm)


class DepartmentManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.query=lambda sql,args=():[dict(x) for x in self.db.execute(sql,args).fetchall()]
        self.execute=lambda sql,args=():self.db.execute(sql,args)
        self.manager=dm.DepartmentManager(self.query,self.execute,self.root,lambda:'2026-10-26T12:00:00+09:00')
        self.calls=[];self.fail=None;self.research_fail=False
        self.handlers={d:lambda ctx,d=d:self.handle(d,ctx) for d in ('research','design','development','verification')}
        self.validators={d:lambda out:None for d in ('proposal','research','design','development','verification')}

    def tearDown(self):self.db.close();self.tmp.cleanup()

    def handle(self,department,context):
        self.calls.append(department)
        if department=='research':
            if self.research_fail:raise RuntimeError('公式画面取得失敗')
            return dict(verified=True,brief={'sources':['a','b']})
        if department=='design':return dict(spec=context['spec'],feedback=context['feedback'].get('design'),research=context.get('research'))
        if department=='development':return dict(content_sha=dm.department_digest(context['design']),path='example.html',details='候補')
        return dict(passed=self.fail is None,return_to=self.fail or 'verification',details='具体的な検査結果')

    def run_factory(self,scope='scope',configuration=None,enabled=lambda:True):
        return self.manager.run('旅行アプリ',scope,{'audience':'家族'},self.handlers,self.validators,configuration or {},enabled)

    def test_handoffs_reach_owner_review_without_publishing(self):
        result=self.run_factory()
        self.assertEqual(self.calls,['research','design','development','verification'])
        self.assertEqual(result['stage'],'のぼるさん確認待ち')
        self.assertEqual(result['departments']['operations']['status'],'approval_wait')
        self.assertNotIn('approved',json.dumps(result))

    def test_restart_reuses_unchanged_validated_receipts(self):
        self.run_factory();self.calls.clear()
        self.manager=dm.DepartmentManager(self.query,self.execute,self.root,lambda:'later')
        self.run_factory()
        self.assertEqual(self.calls,[])

    def test_verifier_failure_does_not_repeat_research_design_or_build(self):
        self.fail='verification';first=self.run_factory();self.calls.clear()
        self.fail=None;second=self.run_factory()
        self.assertEqual(self.calls,['verification'])
        self.assertEqual(first['candidate'],second['candidate'])
        self.assertEqual(second['stage'],'のぼるさん確認待ち')

    def test_design_failure_returns_to_design_then_rebuilds_and_rechecks(self):
        self.fail='design';self.run_factory();self.calls.clear()
        self.fail=None;self.run_factory()
        self.assertEqual(self.calls,['design','development','verification'])

    def test_workflow_failure_repairs_only_development_and_verification(self):
        self.fail='development';self.run_factory();self.calls.clear()
        self.fail=None;self.run_factory()
        self.assertEqual(self.calls,['development','verification'])

    def test_research_failure_allows_work_but_cannot_grant_review(self):
        self.research_fail=True;result=self.run_factory()
        self.assertEqual(self.calls,['research','design','development','verification'])
        self.assertEqual(result['stage'],'比較調査待ち・制作検査済み')
        self.assertNotIn('operations',result['departments'])
        self.calls.clear();self.research_fail=False
        self.assertEqual(self.run_factory()['stage'],'のぼるさん確認待ち')
        self.assertIn('research',self.calls)

    def test_changed_requirements_invalidate_all_prior_contracts(self):
        self.run_factory();self.calls.clear();self.run_factory(scope='new-scope')
        self.assertEqual(self.calls,['research','design','development','verification'])

    def test_changed_research_error_does_not_discard_offline_design_or_candidate(self):
        self.research_fail=True;self.run_factory();self.calls.clear()
        self.handlers['research']=lambda ctx:(_ for _ in ()).throw(RuntimeError('別の通信エラー'))
        self.run_factory()
        self.assertNotIn('design',self.calls);self.assertNotIn('development',self.calls)

    def test_new_verifier_configuration_preserves_source(self):
        self.run_factory();self.calls.clear()
        self.run_factory(configuration={'verification':{'model':'new-reviewer'}})
        self.assertEqual(self.calls,['verification'])

    def test_tampered_receipt_is_regenerated(self):
        result=self.run_factory();self.calls.clear()
        Path(result['departments']['research']['path']).write_text('{"verified":false}')
        self.run_factory()
        self.assertEqual(self.calls,['research'])

    def test_same_error_counts_instead_of_resetting_memory(self):
        self.fail='design';self.run_factory();result=self.run_factory()
        self.assertEqual(result['feedback']['design']['repeats'],2)
        self.assertNotEqual(result['stage'],'のぼるさん確認待ち')

    def test_handler_exception_keeps_completed_upstream_work(self):
        original=self.handlers['development']
        self.handlers['development']=lambda ctx:(_ for _ in ()).throw(ValueError('コード生成失敗'))
        result=self.run_factory()
        self.assertEqual(result['departments']['research']['status'],'completed')
        self.assertEqual(result['departments']['design']['status'],'completed')
        self.assertEqual(result['departments']['development']['status'],'blocked')
        self.handlers['development']=original;self.calls.clear();self.run_factory()
        self.assertEqual(self.calls,['development','verification'])

    def test_invalid_contract_cannot_move_to_next_department(self):
        self.validators['design']=lambda out:(_ for _ in ()).throw(ValueError('操作仕様不足'))
        result=self.run_factory()
        self.assertEqual(self.calls,['research','design'])
        self.assertEqual(result['departments']['design']['status'],'blocked')

    def test_stop_request_does_not_start_next_department(self):
        result=self.run_factory(enabled=lambda:len(self.calls)<2)
        self.assertEqual(self.calls,['research','design'])
        self.assertEqual(result['stage'],'停止中')

    def test_corrupt_or_external_receipt_never_trusted(self):
        with self.assertRaises(ValueError):
            self.manager.read_receipt({'path':'/etc/passwd','sha256':'x'})

    def test_stop_during_verification_does_not_allow_owner_review(self):
        result=self.run_factory(enabled=lambda:len(self.calls)<4)
        self.assertEqual(result['stage'],'停止中')
        self.assertNotIn('operations',result['departments'])

    def test_requirements_cannot_escape_department_folder(self):
        with self.assertRaises(ValueError):self.run_factory(scope='../outside')

    def test_bundled_engine_matches_modular_sources(self):
        path=MODULE.parent/'bundle_departments.py'
        spec=importlib.util.spec_from_file_location('bundle',path)
        bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)
        self.assertEqual(bundle.bundle(MODULE.parent),(MODULE.parent/'venture_agent_integrated.py').read_text())


if __name__=='__main__':unittest.main()
