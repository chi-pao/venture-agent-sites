"""Unit tests for resumption and bounded independent planning, not model-quality proof."""
import copy
import re
import tempfile
import io
from urllib.error import HTTPError
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from test_preview import app
from test_autoqa import work_plan


class CheckpointedQAPlannerTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.previous_out=app.OUT;app.OUT=self.root
        self.spec=dict(audience='在宅勤務者',requested_outcome='作業時間を計算して保存する',
            acceptance=['作業予定の集計','実績時間の集計','再読込して保持','出力と復元','誤入力を拒否'])
        self.cfg=dict(app.DEFAULT,model='fixture-model')
        self.page='<html><head><script>const SECRET="do-not-send";</script><style>body{color:red}</style></head><body><h1>在宅勤務の作業を整理する</h1><p>開始と終了を入力して作業時間を計算する。</p><form id="form"><label for="title">作業名</label><input id="title" required><button>保存する</button></form><strong id="planned">0分</strong></body></html>'
        self.full=work_plan();self.calls=[];self.timeout_once=False

    def tearDown(self):app.OUT=self.previous_out;self.tmp.cleanup()

    def model(self,prompt,cfg,tokens,**kw):
        if '独立QA監査。' in prompt:
            key='audit';value=dict(valid=True,reasons=[])
        elif '共通検査のうち' in prompt:
            kind=re.search(r'共通検査のうち([a-z]+)の1件',prompt).group(1);key=kind
            value=copy.deepcopy(next(x for x in self.full['scenarios'] if x['kind']==kind))
            if kind=='workflow':value['result_selector']=self.full['result_selector']
            if kind=='roundtrip':
                steps=value['steps'];csv=next(x for x in steps if x['op']=='download_csv');js=next(x for x in steps if x['op']=='download_json');restore=next(x for x in steps if x['op']=='restore_file')
                value=dict(csv_selector=csv['selector'],csv_contains=csv['contains'],json_selector=js['selector'],restore_selector=restore['selector'],mutation_steps=steps[2:next(i for i,x in enumerate(steps) if x['op']=='restore_file')],confirmation_mode='inline',cancel_selector=next(x['selector'] for x in steps if x['op']=='cancel_restore'),confirmation_steps=steps[max(i for i,x in enumerate(steps) if x['op']=='restore_file')+1:],checks=value['checks'],acceptance=value['acceptance'],rationale=value.get('rationale','復元前後の保存値を照合する'))

            if kind=='invalid':
                steps=value['steps'];value=dict(restore_selector=next(x['selector'] for x in steps if x['op']=='restore_invalid'),invalid_steps=[x for x in steps if x['op']!='restore_invalid'],checks=value['checks'],acceptance=value['acceptance'],rationale=value.get('rationale','不正な入力で保存が変わらないことを確認'))
        else:
            i,j=map(int,re.search(r'完成条件(\d+)のケース(\d+)',prompt).groups());key=f'feature-{i}-{j}'
            value=copy.deepcopy(next(x for x in self.full['feature_cases'] if x['acceptance_index']==i and x['case_index']==j))
            value['acceptance']=[i]
        self.calls.append(dict(key=key,prompt=prompt,tokens=tokens,timeout=kw['request_timeout'],schema=kw.get('schema')))
        if self.timeout_once and key=='variant':
            self.timeout_once=False;raise TimeoutError('unit-test timeout')
        return kw['validator'](value)

    def plan(self,page=None,cfg=None):
        with patch.object(app,'ai_json',side_effect=self.model):
            return app.checkpointed_independent_qa_plan('在宅ワーク',page or self.page,cfg or self.cfg,self.spec,['在宅勤務の作業を整理する','開始と終了を入力して作業時間を計算する。'])

    def test_timeout_resumes_after_last_completed_scenario(self):
        self.timeout_once=True
        with self.assertRaises(TimeoutError):self.plan()
        self.assertEqual([c['key'] for c in self.calls],['workflow','variant'])
        self.assertTrue(list(self.root.rglob('base-workflow.json')))
        plan=self.plan()
        self.assertEqual(len(plan['scenarios']),5);self.assertEqual(len(plan['feature_cases']),10)
        self.assertEqual(sum(c['key']=='workflow' for c in self.calls),1)
        self.assertEqual(sum(c['key']=='variant' for c in self.calls),2)

    def test_complete_plan_reuses_every_validated_unit_without_inference(self):
        first=self.plan();count=len(self.calls);second=self.plan()
        self.assertEqual(first,second);self.assertEqual(len(self.calls),count)
        self.assertEqual(count,20)  # 5 base + 10 feature cases + 5 independent audits.

    def test_each_request_is_small_and_scripts_never_enter_context(self):
        self.plan()
        self.assertLessEqual(max(c['tokens'] for c in self.calls),1200)
        self.assertTrue(all(c['timeout']==180 for c in self.calls))
        self.assertNotIn('do-not-send',''.join(c['prompt'] for c in self.calls))
        self.assertLess(max(len(c['prompt']) for c in self.calls),12000)
        self.assertTrue(all(isinstance(c['schema'],dict) for c in self.calls))

    def test_model_or_source_change_cannot_reuse_an_old_plan(self):
        self.plan();count=len(self.calls)
        self.plan(cfg=dict(self.cfg,model='different-model'));self.assertEqual(len(self.calls),2*count)
        self.plan(page=self.page+'<!--new source-->');self.assertEqual(len(self.calls),3*count)

    def test_inventory_preserves_target_labels_result_ids_and_button_copy(self):
        inventory=app.compact_qa_inventory(self.page)
        title=next(x for x in inventory['controls'] if x['selector']=='#title')
        self.assertEqual(title['label'],'作業名')
        button=next(x for x in inventory['controls'] if x['tag']=='button')
        self.assertEqual(button['selector'],'#form button');self.assertEqual(button['text'],'保存する')
        self.assertTrue(any(x['selector']=='#planned' for x in inventory['outputs']))

    def test_partial_case_does_not_become_a_valid_checkpoint(self):
        with patch.object(app,'ai_json',side_effect=lambda prompt,cfg,tokens,**kw:kw['validator'](dict(steps=[],checks=[],acceptance=[]))):
            with self.assertRaises(app.AutoQAPlanError):app.checkpointed_independent_qa_plan('在宅ワーク',self.page,self.cfg,self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.assertFalse(list(self.root.rglob('base-workflow.json')))
        self.assertTrue(list(self.root.rglob('base-workflow-error.json')))

    def test_rejected_semantic_audit_repairs_its_cases_without_repeating_base_scenarios(self):
        original=self.model;rejected=[False]
        def model(prompt,cfg,tokens,**kw):
            if '独立QA監査。' in prompt and not rejected[0]:
                rejected[0]=True
                return kw['validator'](dict(valid=False,reasons=['この条件を操作で確認していません']))
            return original(prompt,cfg,tokens,**kw)
        with patch.object(app,'ai_json',side_effect=model):
            with self.assertRaises(app.AutoQAPlanError):
                app.checkpointed_independent_qa_plan('在宅ワーク',self.page,self.cfg,self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.plan()
        self.assertEqual(sum(c['key']=='workflow' for c in self.calls),1)
        self.assertEqual(sum(c['key']=='feature-0-0' for c in self.calls),2)

    def test_bounded_schema_request_does_not_silently_add_a_larger_retry(self):
        with patch.object(app,'ai',return_value='{"wrong":true}') as model:
            with self.assertRaises(app.AutoQAPlanError):
                app.ai_json('unit fixture',dict(self.cfg,_bounded_json_retry=True,_schema_in_prompt=False),650,
                    schema={'type':'object'},max_attempts=1,
                    validator=lambda value:(_ for _ in ()).throw(ValueError('required key missing')))
            self.assertEqual(model.call_count,1)
            self.assertEqual(model.call_args.args[2],650)

    def test_schema_transport_fallback_preserves_small_output_budget(self):
        failure=HTTPError('http://fixture',400,'schema rejected',{},io.BytesIO(b'schema rejected'))
        with patch.object(app,'ai',side_effect=[failure,'{"ready":true}']) as model:
            result=app.ai_json('unit fixture',dict(self.cfg,_bounded_json_retry=True,_schema_in_prompt=False),650,
                schema={'type':'object'},max_attempts=1,validator=lambda value:value)
        self.assertEqual(result,{'ready':True})
        self.assertEqual([call.args[2] for call in model.call_args_list],[650,650])
        self.assertEqual(model.call_args_list[1].args[1]['_json_response'],'json')
        self.assertIn('出力契約:',model.call_args_list[1].args[0])
        self.assertIn('object',model.call_args_list[1].args[0])

    def test_real_model_object_indices_are_rejected_with_actionable_feedback(self):
        value=copy.deepcopy(self.full['scenarios'][0])
        value['result_selector']=self.full['result_selector']
        value['acceptance']=[dict(index=0,condition='注文登録が可能であること')]
        with self.assertRaisesRegex(app.AutoQAPlanError,'整数だけの配列'):
            app.validate_qa_unit(value,'workflow',len(self.spec['acceptance']))

    def test_model_context_does_not_encourage_copying_condition_objects(self):
        self.plan()
        prompt=self.calls[0]['prompt']
        self.assertIn('acceptance_by_index',prompt)
        self.assertNotIn('"index":0,"condition"',prompt)
        self.assertIn('整数ミリ秒',prompt)

    def test_primary_exact_result_is_explicit_and_not_inferred_from_partial_text(self):
        value=copy.deepcopy(self.full['scenarios'][0]);value['result_selector']=self.full['result_selector']
        value['checks']=[dict(op='text_contains',selector='#summary',value='1'),dict(op='text_contains',selector='#result',value='保存')]
        with self.assertRaises(app.AutoQAPlanError):app.validate_qa_unit(value,'workflow',5)
        value['exact_check']=dict(op='text_equals',selector='#planned',value='120分')
        checked=app.validate_qa_unit(value,'workflow',5)
        self.assertEqual(checked['checks'][0],value['exact_check'])
        self.assertNotIn('exact_check',checked)
        schema=app.qa_unit_schema(5,'workflow')
        self.assertIn('exact_check',schema['required'])

    def test_select_cannot_be_filled_as_a_text_input(self):
        page=self.page+'<select id="work_status"><option value="done">完了</option></select>'
        original=self.model
        def model(prompt,cfg,tokens,**kw):
            def reject_target(value):
                value['steps'].insert(0,dict(op='fill',selector='#work_status',value='done'))
                return kw['validator'](value)
            return original(prompt,cfg,tokens,**dict(kw,validator=reject_target))
        with patch.object(app,'ai_json',side_effect=model):
            with self.assertRaisesRegex(app.AutoQAPlanError,'要素に合わない操作'):
                app.checkpointed_independent_qa_plan('在宅ワーク',page,self.cfg,self.spec,['対象者向けの説明です','最初の使い方の説明です'])

    def test_roundtrip_compiler_emits_real_file_protocol_without_model_op_names(self):
        value=dict(csv_selector='#csv',csv_contains=['注文A','商品A'],json_selector='#json',restore_selector='#restore',mutation_steps=[dict(op='fill',selector='#title',value='別記録C'),dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#count',value='2'),dict(op='text_equals',selector='#summary',value='合計300円')],acceptance=[0],rationale='復元を照合する')
        plan=app.compile_qa_roundtrip(value,5)
        self.assertEqual([x['op'] for x in plan['steps']],['download_csv','download_json','fill','click','cancel_restore','restore_file','restore_file'])
        self.assertEqual(plan['checks'],value['checks'])
        with self.assertRaises(app.AutoQAPlanError):app.compile_qa_roundtrip(dict(value,mutation_steps=[dict(op='click',selector='#clear')]),5)

    def test_backup_binding_prompt_does_not_conflict_with_legacy_steps_envelope(self):
        self.plan()
        prompt=next(x['prompt'] for x in self.calls if x['key']=='roundtrip')
        self.assertIn('"csv_selector"',prompt)
        self.assertIn('steps/kindは出力しない',prompt)
        self.assertNotIn('stepsは{op,selector',prompt)
        self.assertNotIn('"steps":',prompt)
        self.assertIn('復元後の期待値:',prompt)

    def test_ollama_contract_uses_direct_required_keys_not_required_only_union(self):
        for schema in (app.qa_unit_schema(5,'workflow'),app.qa_roundtrip_schema(5)):
            self.assertNotIn('anyOf',schema)
            self.assertTrue(schema['required'])
            self.assertTrue(set(schema['required'])<=set(schema['properties']))

    def test_inline_confirmation_is_not_misclassified_as_native_dialog(self):
        value=dict(csv_selector='#csv',csv_contains=['注文A','商品A'],json_selector='#json',restore_selector='#restore',confirmation_mode='inline',cancel_selector='#cancelRestore',confirmation_steps=[dict(op='click',selector='#applyRestore')],mutation_steps=[dict(op='fill',selector='#title',value='C'),dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#count',value='2'),dict(op='text_equals',selector='#summary',value='300円')],acceptance=[0],rationale='復元前後を検証')
        plan=app.compile_qa_roundtrip(value,5)
        self.assertEqual([s['op'] for s in plan['steps'][-4:]],['restore_file','cancel_restore','restore_file','click'])
        self.assertTrue(plan['steps'][-3]['inline'])
        self.assertEqual(plan['steps'][-3]['selector'],'#cancelRestore')
        with self.assertRaises(app.AutoQAPlanError):app.compile_qa_roundtrip(dict(value,cancel_selector=''),5)

    def test_invalid_file_selection_cannot_be_omitted_by_model(self):
        value=dict(restore_selector='#restore',invalid_steps=[dict(op='fill',selector='#title',value=''),dict(op='click',selector='#save')],checks=[dict(op='invalid',selector='#title'),dict(op='text_equals',selector='#count',value='2')],acceptance=[0],rationale='不正入力後の保存値を照合')
        plan=app.compile_qa_invalid(value,5)
        self.assertEqual(plan['steps'][0],dict(op='restore_invalid',selector='#restore'))
        with self.assertRaises(app.AutoQAPlanError):app.compile_qa_invalid(dict(value,invalid_steps=[dict(op='click',selector='#save')]),5)

    def test_each_base_unit_reaches_browser_before_next_model_request(self):
        order=[];original=self.model
        def model(prompt,cfg,tokens,**kw):
            result=original(prompt,cfg,tokens,**kw);order.append('model:'+self.calls[-1]['key']);return result
        def browser(name,page,plan,directory,**kw):
            self.assertTrue(kw['prefix_only']);order.append('browser:'+plan['scenarios'][-1]['kind'])
            return dict(passed=False,partial_passed=True,scenarios=[],screenshots=[])
        with patch.object(app,'ai_json',side_effect=model),patch.object(app,'execute_browser_qa',side_effect=browser):
            app.checkpointed_independent_qa_plan('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.assertEqual(order[:4],['model:workflow','browser:workflow','model:variant','browser:variant'])

    def test_browser_rejection_keeps_source_and_stops_remaining_planning(self):
        with patch.object(app,'ai_json',side_effect=self.model),patch.object(app,'execute_browser_qa',side_effect=ValueError('expected 120分 actual 90分')):
            with self.assertRaisesRegex(app.AutoQAPlanError,'actual 90分'):
                app.checkpointed_independent_qa_plan('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.assertEqual([c['key'] for c in self.calls],['workflow'])
        self.assertFalse(list(self.root.rglob('base-workflow.json')))
        self.assertIn('actual 90分',next(self.root.rglob('base-workflow-error.json')).read_text())
