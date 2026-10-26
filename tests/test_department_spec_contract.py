"""Scope contamination repair tests; model responses are explicit unit fixtures."""
import copy
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch
from test_preview import app


class DepartmentSpecContractTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.previous=app.OUT;app.OUT=self.root
        self.spec=dict(audience='在宅勤務者',requested_outcome='予定と実績の差を確認する',
            workflow=['入力する','計算する','保存する'],must_have=['稼働枠を計算する','予定と実績を比較する','保存して復元する'],
            acceptance=['入力画面が使いやすい','共同編集機能が実装','実装済みとは書かない'],delivery_mode='browser_local',dependencies=[])
        self.rationale=dict(mvp_scope='外部APIなしで作業時間を集計し、保存・再読込・CSV出力・復元を実行する')
        self.cfg=dict(app.DEFAULT);self.calls=0

    def tearDown(self):app.OUT=self.previous;self.tmp.cleanup()

    def test_instruction_leak_and_unrequested_collaboration_are_detected(self):
        self.assertTrue(app.department_spec_contract_issue(self.spec,self.rationale))
        self.assertTrue(app.department_spec_contract_issue(dict(self.spec,acceptance=['共同編集機能が実装']),self.rationale))
        self.assertEqual(app.department_spec_contract_issue(dict(self.spec,requested_outcome='共同編集で旅行を計画する',acceptance=['共同編集を実行する']),dict(mvp_scope='同行者と共同編集する')),'')

    def test_only_acceptance_is_repaired_and_original_features_are_preserved(self):
        def answer(prompt,cfg,tokens,**kw):
            if prompt.startswith('完成条件の独立監査。'):return kw['validator'](dict(valid=True,issues=[]))
            self.calls+=1
            return kw['validator'](dict(input='開始09時、終了17時、休憩60分を入力',action='稼働枠の計算ボタンを押して結果を表示',expected='稼働可能時間は420分として画面に表示される'))
        with patch.object(app,'ensure_product_spec',return_value=self.spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計・未確認')]),patch.object(app,'ai_json',side_effect=answer),patch.object(app,'store_product_spec',side_effect=lambda name,spec,**kw:spec):
            result=app.ensure_department_product_spec('在宅ワーク',self.cfg)
        self.assertEqual(self.calls,3)
        self.assertEqual(result['must_have'],self.spec['must_have']);self.assertEqual(result['workflow'],self.spec['workflow'])
        self.assertEqual(result['dependencies'],[]);self.assertEqual(result['delivery_mode'],'browser_local')
        self.assertNotIn('共同編集',str(result['acceptance']))

    def test_user_authored_contract_is_not_silently_overwritten(self):
        with patch.object(app,'ensure_product_spec',return_value=self.spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='ユーザー指定')]),patch.object(app,'ai_json') as model:
            with self.assertRaises(app.AutoQAPlanError):app.ensure_department_product_spec('在宅ワーク',self.cfg)
            model.assert_not_called()

    def test_completed_requirement_parts_survive_a_later_timeout(self):
        seen=[];fail=[True]
        def answer(prompt,cfg,tokens,**kw):
            if prompt.startswith('完成条件の独立監査。'):return kw['validator'](dict(valid=True,issues=[]))
            key=next(x for x in self.spec['must_have'] if '今回の必須機能:'+x in prompt);seen.append(key)
            if key==self.spec['must_have'][1] and fail[0]:fail[0]=False;raise TimeoutError('unit fixture')
            return kw['validator'](dict(input='具体的な予定120分と実績90分を入力する',action='登録した作業の比較結果を画面に表示する',expected='予定と実績の差がマイナス30分と表示される'))
        with patch.object(app,'ensure_product_spec',return_value=self.spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計・未確認')]),patch.object(app,'ai_json',side_effect=answer),patch.object(app,'store_product_spec',side_effect=lambda name,spec,**kw:spec):
            with self.assertRaises(TimeoutError):app.ensure_department_product_spec('在宅ワーク',self.cfg)
            app.ensure_department_product_spec('在宅ワーク',self.cfg)
        self.assertEqual(seen.count(self.spec['must_have'][0]),1)

    def test_incorrect_oracle_is_returned_to_proposal_not_stored_as_product_spec(self):
        def answer(prompt,cfg,tokens,**kw):
            if prompt.startswith('完成条件の独立監査。'):
                return kw['validator'](dict(valid=False,issues=['09:00〜17:00から休憩60分を引くと420分、480分ではない']))
            return kw['validator'](dict(input='開始09:00、終了17:00、休憩60分を入力する',action='稼働枠の計算を実行して計算結果を表示する',expected='稼働可能時間480分を結果欄に表示する'))
        with patch.object(app,'ensure_product_spec',return_value=self.spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計')]),patch.object(app,'ai_json',side_effect=answer),patch.object(app,'store_product_spec') as save:
            with self.assertRaisesRegex(app.AutoQAPlanError,'独立監査'):
                app.ensure_department_product_spec('在宅ワーク',self.cfg)
            save.assert_not_called()
        self.assertFalse(list(self.root.rglob('0.json')))
        self.assertIn('420分',next(self.root.rglob('0-error.json')).read_text())
