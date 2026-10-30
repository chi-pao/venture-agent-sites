"""Scope contamination repair tests; model responses are explicit unit fixtures."""
import copy
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch
from test_preview import app


class DepartmentSpecContractTests(TestCase):
    def test_requested_class_timestamp_missing_in_date_only_native_page_is_development_gap(self):
        page='<form id="recordForm"><input id="class_date" type="date"><label for="class_date">授業日</label><button id="saveRecord" type="submit">保存</button></form><strong id="recordCount">0</strong><tbody id="recordRows"></tbody>'
        inventory=app.compact_qa_inventory(page)
        spec=dict(self.spec,acceptance=['授業日時を2023-10-05 14:00に設定し保存と再読込で保持する'])
        cfg=dict(self.cfg,qa_component_contract='native-record-create-v1')
        gap=app.qa_native_requirement_gap(spec,inventory,cfg)
        self.assertIn('実装不足',gap)
        self.assertEqual(app.department_failure_target(dict(failed_step='操作シナリオ設計',details=gap),'実操作・画面検証へ差し戻し'),'development')
        with patch.object(app,'qa_initial_display_context',side_effect=AssertionError('Do not regenerate tests for an absent input')),patch.object(app,'ai_json',side_effect=AssertionError('The missing capability is already established')):
            with self.assertRaisesRegex(app.AutoQAPlanError,'実装不足'):app.checkpointed_independent_qa_plan('授業管理',page,cfg,spec,[])
        with_time=app.compact_qa_inventory(page+'<label for="class_time">授業時刻</label><input id="class_time" type="time">')
        self.assertEqual(app.qa_native_requirement_gap(spec,with_time,cfg),'')
        custom=app.compact_qa_inventory(page+'<button id=\"timePicker\" type=\"button\">授業時刻を選ぶ</button>')
        self.assertEqual(app.qa_native_requirement_gap(spec,custom,cfg),'')
        self.assertEqual(app.qa_native_requirement_gap(spec,inventory,dict(cfg,qa_component_contract='unknown')),'')

    def test_colon_duration_equation_is_checked_before_product_qa(self):
        wrong='入力: 日付=2023年10月10日, 開始時間=10:00, 終了時間=18:00, 休憩時間=1:30 / 操作: 稼働枠と作業を保存 / 期待結果: 稼働可能時間: 8:00 (終了時間 - 開始時間 - 休憩時間 = 18:00 - 10:00 - 1:30 = 6:30)、予定合計: 7:00、実績: 6:30、差分: -0:30 (予定合計 - 実績 = 7:00 - 6:30 = 0:30)。'
        fix=app.department_duration_correction(wrong)
        self.assertEqual(fix['computed_minutes'],'390');self.assertIn('稼働可能時間: 6:30',fix['after'])
        self.assertIn('休憩時間=1:30',fix['after']);self.assertIn('差分: -0:30',fix['after'])
        self.assertIsNone(app.department_duration_correction(fix['after']))
        self.assertIn('矛盾',app.department_difference_issue(fix['after']))
        self.assertEqual(app.department_difference_issue(fix['after'].replace('差分: -0:30','差分: 0:30')),'')
        self.assertIn('矛盾',app.department_difference_issue('差分: 0:30 (7:00 - 6:30 = -0:30)'))
        self.assertIsNone(app.department_duration_correction(wrong.replace('終了時間=18:00','終了時間=08:00')))
        self.assertIsNone(app.department_duration_correction(wrong+' 別の入力: 休憩時間=2:00'))
        spec=dict(self.spec,acceptance=[wrong])
        self.assertTrue(app.department_spec_contract_issue(spec,self.rationale).startswith('時間算術:'))
        with patch.object(app,'ensure_product_spec',return_value=spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計')]),patch.object(app,'store_product_spec',side_effect=lambda name,value,**kw:value) as save:
            with self.assertRaisesRegex(app.AutoQAPlanError,'残る仕様の不一致'):app.ensure_department_product_spec('在宅ワーク',self.cfg)
        self.assertIn('稼働可能時間: 6:30',save.call_args.args[1]['acceptance'][0])

    def test_ai_duration_typo_is_corrected_from_same_inputs_only(self):
        wrong='入力: 日付=2023-10-05, 開始時間=09:00, 終了時間=17:00, 休憩時間=1.5時間 / 操作: 稼働枠を保存 / 期待結果: 稼働可能時間: 7.5時間 (17:00 - 09:00 - 1.5時間)'
        spec=dict(self.spec,acceptance=[wrong,'保存後に同じ入力値が再表示される','CSVに保存値が含まれる'])
        fix=app.department_duration_correction(wrong)
        self.assertEqual(fix['computed_minutes'],'390');self.assertIn('6時間30分',fix['after'])
        with patch.object(app,'ensure_product_spec',return_value=spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計')]),patch.object(app,'store_product_spec',side_effect=lambda name,value,**kw:value),patch.object(app,'ai_json',side_effect=AssertionError('Unambiguous arithmetic does not require another model vote')):
            fixed=app.ensure_department_product_spec('在宅ワーク',self.cfg)
        self.assertEqual(fixed['acceptance'][1:],spec['acceptance'][1:]);self.assertEqual(fixed['must_have'],spec['must_have'])
        self.assertIsNone(app.department_duration_correction(fix['after']))
        self.assertIsNone(app.department_duration_correction(wrong.replace('終了時間=17:00','終了時間=08:00')))
        self.assertIsNone(app.department_duration_correction(wrong+' 別の入力: 開始時間=10:00'))
        self.assertIn('矛盾',app.department_difference_issue('差分: -0.5時間 (6時間 - 5.5時間)'))
        self.assertEqual(app.department_difference_issue('差分: 0.5時間 (6時間 - 5.5時間)'), '')
        self.assertEqual(app.department_difference_issue('差分: -30分 (330分 - 6時間)'), '')

    def test_declared_backup_lifecycle_compiles_data_without_named_screens(self):
        spec=dict(delivery_mode='browser_local',must_have=['受講者名簿のローカル保存','バックアップと復元機能'])
        cfg=dict(department_backup_protocol='browser-json-file-v1')
        self.assertTrue(app.department_file_backup_protocol('バックアップと復元機能',spec,{},cfg))
        data=dict(saved_input='受講者名=山田、授業日=2026-10-30、状態=出席',changed_input='受講者名=山田、授業日=2026-10-30、状態=欠席')
        compiled=app.department_compile_backup_acceptance(data)
        self.assertIn(data['saved_input'],compiled['expected']);self.assertIn(data['changed_input'],compiled['expected'])
        self.assertIn('キャンセル',compiled['action']);self.assertIn('JSON',compiled['action']);self.assertIn('再読込',compiled['action'])
        self.assertNotIn('完成条件に追加',compiled['expected'])
        self.assertFalse(app.department_unrequested_file_contract(str(compiled),str(spec)))
        self.assertFalse(app.department_file_backup_protocol('バックアップと復元機能',dict(spec,must_have=spec['must_have']+['バックアップ名と履歴一覧']),{},cfg))
        self.assertFalse(app.department_file_backup_protocol('未登録の旅程の乗継計算',spec,{},cfg))
        with self.assertRaises(app.AutoQAPlanError):app.department_compile_backup_acceptance(dict(data,changed_input=data['saved_input']))
        with self.assertRaises(app.AutoQAPlanError):app.department_compile_backup_acceptance(dict(data,saved_input='バックアップ名=指定されていない名前'))

    def test_backup_data_compilation_still_receives_independent_source_audit(self):
        spec=dict(self.spec,delivery_mode='browser_local',must_have=['日付と状態の入力と保存','CSV出力機能','バックアップと復元機能'])
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            calls.append(prompt)
            if prompt.startswith('完成条件の独立監査。'):return kw['validator'](dict(valid=True,issues=[]))
            if 'saved_input' in kw['schema']['properties']:
                self.assertNotIn('expected',kw['schema']['properties'])
                return kw['validator'](dict(saved_input='作業名=資料整理、日付=2026-10-30、実績=60分',changed_input='作業名=資料整理、日付=2026-10-30、実績=90分'))
            return kw['validator'](dict(input='作業名=資料整理、実績=60分を入力する',action='対象の保存またはCSV出力を実行する',expected='資料整理の実績60分が保存値または出力ファイルに含まれる'))
        with patch.object(app,'ensure_product_spec',return_value=spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計')]),patch.object(app,'ai_json',side_effect=model),patch.object(app,'store_product_spec',side_effect=lambda name,value,**kw:value):
            repaired=app.ensure_department_product_spec('在宅ワーク',dict(self.cfg,department_backup_protocol='browser-json-file-v1'))
        self.assertEqual(len(repaired['acceptance']),3)
        self.assertEqual(sum(p.startswith('完成条件の独立監査。') for p in calls),3)
        self.assertTrue(list(self.root.rglob('*-backup-data-last-response.json')))
        self.assertTrue(list(self.root.rglob('*-backup-protocol.json')))
        self.assertIn('実績=60分',repaired['acceptance'][-1]);self.assertIn('実績=90分',repaired['acceptance'][-1])

    def test_unrequested_file_names_and_backup_screens_are_detected_without_removing_scope(self):
        source=dict(must_have=['受講者名簿のローカル保存','授業日時と出欠状態の連動','CSV出力機能','バックアップと復元機能'],requested_outcome='名簿登録から保存とCSV出力までを行う',acceptance=['3名を保存する。ファイル名は「名簿_YYYY-MM-DD_HH-MM.csv」である','バックアップ名=午前10時の記録をバックアップ一覧画面から復元する'])
        self.assertIn('命名規則',app.department_spec_contract_issue(source,{}))
        self.assertEqual(app.department_spec_source_requirements(source),source['must_have'])
        explicit=dict(source,must_have=source['must_have']+['ファイル名を名簿_YYYY-MM-DD_HH-MM.csvにする。バックアップ名を一覧で管理する'])
        self.assertEqual(app.department_spec_contract_issue(explicit,{}),'')

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

    def test_repair_receives_both_rejected_candidate_and_audit_feedback(self):
        reject=[True];prompts=[]
        def answer(prompt,cfg,tokens,**kw):
            if prompt.startswith('完成条件の独立監査。'):
                if reject[0]:
                    reject[0]=False
                    return kw['validator'](dict(valid=False,issues=['480分ではなく休憩後420分']))
                return kw['validator'](dict(valid=True,issues=[]))
            prompts.append(prompt)
            return kw['validator'](dict(input='開始09:00、終了17:00、休憩60分を入力する',action='稼働枠の計算を実行して計算結果を表示する',expected='稼働可能時間480分を結果欄に表示する'))
        with patch.object(app,'ensure_product_spec',return_value=self.spec),patch.object(app,'idea_details',return_value=self.rationale),patch.object(app,'query',return_value=[dict(source='AI設計')]),patch.object(app,'ai_json',side_effect=answer),patch.object(app,'store_product_spec',side_effect=lambda name,spec,**kw:spec):
            with self.assertRaises(app.AutoQAPlanError):app.ensure_department_product_spec('在宅ワーク',self.cfg)
            app.ensure_department_product_spec('在宅ワーク',self.cfg)
        self.assertIn('修正すべき前回の候補:',prompts[1])
        self.assertIn('480分を結果欄',prompts[1]);self.assertIn('420分',prompts[1])
