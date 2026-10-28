"""Unit tests for resumption and bounded independent planning, not model-quality proof."""
import copy
import json
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
    def test_failed_unit_switches_only_to_configured_alternative_and_back(self):
        cfg=dict(model='planner',qa_oracle_model='oracle',code_model='coder')
        self.assertEqual(app.qa_retry_models(cfg,{}),('planner','oracle'))
        self.assertEqual(app.qa_retry_models(cfg,dict(error='TimeoutError: timed out')),('coder','coder'))
        self.assertEqual(app.qa_retry_models(cfg,dict(error='invalid output',model='coder',oracle_model='coder')),('planner','oracle'))
        self.assertEqual(app.qa_retry_models(cfg,dict(error='HTTP Error 403')),('planner','oracle'))
        self.assertEqual(app.qa_retry_models(dict(model='planner'),dict(error='timed out')),('planner','planner'))

    def test_retry_timeout_grows_only_after_timeout_and_stays_bounded(self):
        self.assertEqual(app.qa_retry_timeout({},{}),180)
        self.assertEqual(app.qa_retry_timeout({},dict(error='TimeoutError: timed out')),270)
        self.assertEqual(app.qa_retry_timeout({},dict(error='TimeoutError: timed out',timeout_streak=2)),360)
        self.assertEqual(app.qa_retry_timeout({},dict(error='invalid JSON',timeout_streak=2)),180)

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
        if '再読込の完成条件番号' in prompt:
            key='reload-binding';value=dict(acceptance=next(x['acceptance'] for x in self.full['scenarios'] if x['kind']=='reload'))
        elif '独立QA監査。' in prompt:
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
        self.calls.append(dict(key=key,prompt=prompt,tokens=tokens,timeout=kw['request_timeout'],schema=kw.get('schema'),model=cfg['model']))
        if self.timeout_once and key=='variant':
            self.timeout_once=False;raise TimeoutError('unit-test timeout')
        return kw['validator'](value)

    def plan(self,page=None,cfg=None):
        with patch.object(app,'ai_json',side_effect=self.model):
            return app.checkpointed_independent_qa_plan('在宅ワーク',page or self.page,cfg or self.cfg,self.spec,['在宅勤務の作業を整理する','開始と終了を入力して作業時間を計算する。'])

    def test_workflow_with_wrong_save_button_replans_operations(self):
        page='<form id="recordForm"><input id="title" required><button id="saveRecord" type="submit">作業を保存</button></form><button id="saveWorkday" type="button">稼働枠を保存</button>'
        inventory=app.compact_qa_inventory(page)
        value={'steps':[{'op':'fill','selector':'#title','value':'作業'},{'op':'click','selector':'#saveWorkday'}]}
        with self.assertRaisesRegex(app.AutoQAPlanError,'未送信'):
            app.validate_qa_inventory_actions(value,inventory,'workflow')
        value['steps'].append({'op':'click','selector':'#saveRecord'})
        app.validate_qa_inventory_actions(value,inventory,'workflow')

    def test_independent_feature_planner_receives_matching_design_examples(self):
        plan={'features':[{'acceptance_index':0,'test_cases':[{'input':'条件A','action':'操作A','expected':'設計時の期待A'},{'input':'条件B','action':'操作B','expected':'設計時の期待B'}]}]}
        self.plan(cfg=dict(self.cfg,_department_documents={'implementation_plan':plan}))
        first=next(c['prompt'] for c in self.calls if c['key']=='feature-0-0')
        second=next(c['prompt'] for c in self.calls if c['key']=='feature-0-1')
        other=next(c['prompt'] for c in self.calls if c['key']=='feature-1-0')
        self.assertIn('条件A',first);self.assertIn('独立検証',first)
        self.assertIn('条件B',second);self.assertNotIn('条件A',other)
        self.assertTrue(any(c['key']=='audit' for c in self.calls))

    def test_timeout_resumes_after_last_completed_scenario(self):
        self.timeout_once=True
        with self.assertRaises(TimeoutError):self.plan()
        self.assertEqual([c['key'] for c in self.calls],['workflow','variant'])
        self.assertTrue(list(self.root.rglob('base-workflow.json')))
        plan=self.plan()
        self.assertEqual(len(plan['scenarios']),5);self.assertEqual(len(plan['feature_cases']),10)
        self.assertEqual(sum(c['key']=='workflow' for c in self.calls),1)
        self.assertEqual(sum(c['key']=='variant' for c in self.calls),2)

    def test_timeout_does_not_resend_stale_prior_response(self):
        self.timeout_once=True
        with self.assertRaises(TimeoutError):self.plan()
        error=next(self.root.rglob('base-variant-error.json'))
        (error.parent/'base-variant-last-response.json').write_text(json.dumps({'stale':'OLD_RESPONSE_MARKER'}),encoding='utf-8')
        plan=self.plan()
        prompt=[c['prompt'] for c in self.calls if c['key']=='variant'][-1]
        self.assertNotIn('OLD_RESPONSE_MARKER',prompt)
        self.assertIn('TimeoutError',prompt)
        self.assertEqual(sum(c['key']=='workflow' for c in self.calls),1)

    def test_timeout_switches_failed_unit_and_reuses_completed_units(self):
        self.timeout_once=True
        cfg=dict(self.cfg,code_model='alternate-model')
        with self.assertRaises(TimeoutError):self.plan(cfg=cfg)
        self.plan(cfg=cfg)
        self.assertEqual([c['model'] for c in self.calls if c['key']=='variant'],['fixture-model','alternate-model'])
        self.assertEqual([c['timeout'] for c in self.calls if c['key']=='variant'],[180,270])
        self.assertEqual(sum(c['key']=='workflow' for c in self.calls),1)

    def test_complete_plan_reuses_every_validated_unit_without_inference(self):
        first=self.plan();count=len(self.calls);second=self.plan()
        self.assertEqual(first,second);self.assertEqual(len(self.calls),count)
        self.assertEqual(count,20)  # 4 base + reload mapping + 10 feature cases + 5 audits.

    def test_reload_rechecks_the_prior_independent_expected_values(self):
        plan=self.plan()
        variant=next(s for s in plan['scenarios'] if s['kind']=='variant')
        reload=next(s for s in plan['scenarios'] if s['kind']=='reload')
        self.assertEqual(reload['steps'],[dict(op='reload')])
        self.assertEqual(reload['checks'],variant['checks'])
        self.assertEqual(reload['acceptance'],next(s['acceptance'] for s in self.full['scenarios'] if s['kind']=='reload'))
        self.assertEqual(sum(c['key']=='reload-binding' for c in self.calls),1)

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

    def test_required_fields_survive_bounded_control_list(self):
        optional=''.join('<input id="optional%d" placeholder="%s">'%(i,'説明'*25) for i in range(20))
        page='<h1>在宅勤務</h1><form id="form">'+optional+'<input id="work_date" type="date" required><select id="task_status" required><option value="open">未着手</option></select><button id="saveRecord">保存</button></form><strong id="planned">0分</strong>'
        class Stop(Exception):pass
        def model(prompt,cfg,tokens,**kw):
            self.assertIn('#work_date',prompt)
            self.assertIn('#task_status',prompt)
            self.assertIn('#saveRecord',prompt)
            raise Stop()
        with patch.object(app,'ai_json',side_effect=model):
            with self.assertRaises(Stop):app.checkpointed_independent_qa_plan('在宅ワーク',page,self.cfg,self.spec,['対象者の説明','最初の操作の説明'])

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
        plan=self.plan()
        prompt=next(x['prompt'] for x in self.calls if x['key']=='roundtrip')
        self.assertIn('"csv_selector"',prompt)
        self.assertIn('steps/kindは出力しない',prompt)
        self.assertNotIn('stepsは{op,selector',prompt)
        self.assertNotIn('"steps":',prompt)
        self.assertIn('checksは出力しない',prompt)
        reload=next(s for s in plan['scenarios'] if s['kind']=='reload')
        restored=next(s for s in plan['scenarios'] if s['kind']=='roundtrip')
        self.assertEqual(restored['checks'],reload['checks'])

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
            self.assertTrue(kw['prefix_only']);order.append('browser:'+(plan['scenarios'][-1]['kind'] if plan['scenarios'] else 'feature'))
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

    def test_conflicting_expectations_repair_before_any_browser_observation(self):
        raw=dict(steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#form button')],
            checks=[dict(op='text_equals',selector='#planned',value='1分'),dict(op='visible',selector='#title')],
            exact_check=dict(op='text_equals',selector='#planned',value='2分'),acceptance=[0],result_selector='#planned',rationale='入力から計算した期待値')
        fixed=copy.deepcopy(raw);fixed['checks'][0]['value']='2分'
        def model(prompt,cfg,tokens,**kw):return kw['validator'](copy.deepcopy(raw))
        args=('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        with patch.object(app,'ai_json',side_effect=model),patch.object(app,'execute_browser_qa',side_effect=ValueError('browser reached')) as browser:
            with self.assertRaisesRegex(app.AutoQAPlanError,'期待値が矛盾'):
                app.checkpointed_independent_qa_plan(*args)
            self.assertEqual(browser.call_count,0)
            with patch.object(app,'repair_qa_conflicting_checks',return_value=fixed) as repair:
                with self.assertRaisesRegex(app.AutoQAPlanError,'browser reached'):
                    app.checkpointed_independent_qa_plan(*args)
                self.assertEqual(repair.call_count,1)
                self.assertEqual(browser.call_count,1)

    def test_display_nodes_cannot_be_operated_as_checkboxes_and_files_cannot_be_clicked(self):
        inventory=app.compact_qa_inventory(self.page+'<input type="file" id="restoreFile">')
        for step in (dict(op='check',selector='#planned'),dict(op='click',selector='#restoreFile')):
            with self.subTest(step=step),self.assertRaises(app.AutoQAPlanError):
                app.validate_qa_inventory_actions(dict(steps=[step]),inventory,'workflow')
        valid=dict(steps=[dict(op='fill',selector='#title',value='入力')])
        self.assertEqual(app.validate_qa_inventory_actions(valid,inventory,'workflow'),valid)

    def test_repair_prompt_includes_previous_test_and_observed_error(self):
        original=self.model;fail=[True];prompts=[]
        def model(prompt,cfg,tokens,**kw):
            prompts.append(prompt)
            return original(prompt,cfg,tokens,**kw)
        def browser(*args,**kwargs):
            if fail[0]:fail[0]=False;raise ValueError('expected 1 actual 100%')
            return dict(passed=False,partial_passed=True,scenarios=[],screenshots=[])
        with patch.object(app,'ai_json',side_effect=model),patch.object(app,'execute_browser_qa',side_effect=browser):
            with self.assertRaises(app.AutoQAPlanError):
                app.checkpointed_independent_qa_plan('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
            app.checkpointed_independent_qa_plan('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.assertIn('前回の不合格検査:',prompts[1]);self.assertIn('actual 100%',prompts[1])
        self.assertIn('仕様から正解を再計算',prompts[1])

    def test_verification_text_override_preserves_independent_vision_model(self):
        cfg=dict(self.cfg,qa_vision_model='vision-fixture',department_models={'verification':'reasoning-fixture'})
        role=app.department_configuration(cfg,'verification')
        self.assertEqual(role['model'],'reasoning-fixture')
        self.assertEqual(role['qa_vision_model'],'vision-fixture')

    def test_display_contract_discards_observed_numbers_and_keeps_literal_format(self):
        formats=app.qa_display_contracts_from_nodes([dict(selector='#rate',text='100%（出席扱い1/1、欠席0）',label='出席率')])
        self.assertEqual(formats['#rate']['template'],'{n0}%（出席扱い{n1}/{n2}、欠席{n3}）')
        self.assertNotIn('100',str(formats))
        test=dict(exact_check=dict(selector='#rate',expected_values=['50','1','2','1'],expected_literals=['','%（出席扱い','/','、欠席','）']))
        compiled=app.compile_qa_formatted_expectation(test,formats)
        self.assertEqual(compiled['exact_check']['value'],'50%（出席扱い1/2、欠席1）')
        self.assertNotIn('expected_values',compiled['exact_check'])
        with self.assertRaises(app.AutoQAPlanError):app.compile_qa_formatted_expectation(dict(exact_check=dict(selector='#rate',expected_values=['100'])),formats)

    def test_display_format_can_never_supply_its_own_numeric_oracle(self):
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='7件 / 超過3件')])
        with self.assertRaises(app.AutoQAPlanError):
            app.compile_qa_formatted_expectation(dict(exact_check=dict(selector='#summary',expected_values=[])),formats)
        result=app.compile_qa_formatted_expectation(dict(exact_check=dict(selector='#summary',expected_values=['2','0'],expected_literals=['','件 / 超過','件'])),formats)
        self.assertEqual(result['exact_check']['value'],'2件 / 超過0件')

    def test_observed_business_state_is_not_automatically_an_expected_state(self):
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='1件 / 稼働枠内')])
        with self.assertRaises(app.AutoQAPlanError):
            app.compile_qa_formatted_expectation(dict(exact_check=dict(selector='#summary',expected_values=['2'])),formats)
        compiled=app.compile_qa_formatted_expectation(dict(exact_check=dict(selector='#summary',expected_values=['2'],expected_literals=['','件 / 稼働超過'])),formats)
        self.assertEqual(compiled['exact_check']['value'],'2件 / 稼働超過')

    def test_feature_case_executes_before_the_next_case_or_semantic_audit(self):
        order=[];original=self.model
        def model(prompt,cfg,tokens,**kw):
            value=original(prompt,cfg,tokens,**kw);order.append(self.calls[-1]['key']);return value
        def browser(name,page,plan,directory,**kw):
            if plan['feature_cases']:
                order.append('feature-browser');raise ValueError('feature actual 0 expected 120')
            return dict(passed=False,partial_passed=True,scenarios=[],screenshots=[])
        with patch.object(app,'ai_json',side_effect=model),patch.object(app,'execute_browser_qa',side_effect=browser):
            with self.assertRaisesRegex(app.AutoQAPlanError,'feature actual'):
                app.checkpointed_independent_qa_plan('在宅ワーク',self.page,dict(self.cfg,qa_probe_units=True),self.spec,['対象者向けの説明です','最初の使い方の説明です'])
        self.assertEqual(order[-2:],['feature-0-0','feature-browser'])
        self.assertNotIn('feature-0-1',order);self.assertNotIn('audit',order)

    def test_targeted_oracle_repair_preserves_operations_and_other_checks(self):
        raw=dict(steps=[dict(op='fill',selector='#amount',value='1000'),dict(op='click',selector='#save')],checks=[dict(op='text_contains',selector='#result',value='保存しました')],acceptance=[0],exact_check=dict(selector='#summary',expected_values=['1件 / 超過1件'],expected_literals=['未処理','件']))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='5件 / 超過4件')])
        answer=dict(expected_text='1件 / 超過0件',basis='未対応1件を保存し期限は将来なので超過は0件')
        def model(prompt,cfg,tokens,**kw):
            self.assertLessEqual(tokens,450);self.assertIn('expected_text',prompt)
            self.assertNotIn('5件 / 超過4件',prompt)
            return kw['validator'](answer)
        with patch.object(app,'ai_json',side_effect=model):
            fixed=app.repair_qa_exact_oracle('返品管理',raw,formats,self.spec,self.cfg,self.root,'feature-0-0','期待結果と不一致')
        self.assertEqual(fixed['steps'],raw['steps']);self.assertEqual(fixed['checks'],raw['checks'])
        self.assertEqual(fixed['exact_check']['value'],'1件 / 超過0件')
        self.assertNotEqual(fixed['exact_check']['value'],'5件 / 超過4件')

    def test_date_facts_are_independent_and_do_not_infer_business_state(self):
        steps=[dict(op='fill',selector='#deadline',value='2023-12-31'),dict(op='fill',selector='#future',value='2027-01-01'),dict(op='fill',selector='#bad',value='2026-02-30')]
        facts=app.qa_independent_date_facts(steps,{'date':'2026-10-27'})
        self.assertEqual([x['relation'] for x in facts],['before','after'])
        self.assertEqual(facts[0]['days_from_reference'],-1031)
        self.assertNotIn('overdue',str(facts))
        self.assertEqual(app.qa_independent_date_facts(steps,{}),[])

    def test_resume_refreshes_browser_local_day_without_copying_stale_date(self):
        from datetime import datetime, timezone
        current=datetime(2026,10,27,16,0,tzinfo=timezone.utc)
        observed={'date':'2026-10-27','timezone':'Asia/Tokyo','source':'browser local clock'}
        clock=app.qa_current_reference_clock(observed,current)
        self.assertEqual(clock['date'],'2026-10-28')
        self.assertEqual(clock['timezone'],'Asia/Tokyo')
        fact=app.qa_independent_date_facts([dict(op='fill',selector='#deadline',value='2026-10-27')],clock)
        self.assertEqual(fact[0]['relation'],'before')
        self.assertEqual(fact[0]['days_from_reference'],-1)

    def test_oracle_receives_browser_date_without_observed_result(self):
        raw=dict(steps=[dict(op='fill',selector='#deadline',value='2023-12-31')],acceptance=[0],exact_check=dict(selector='#summary',value='0件'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='1件 / 超過1件')])
        def model(prompt,cfg,tokens,**kw):
            if '独立監査。日付' in prompt:
                self.assertNotIn('実画面から推測した値',prompt)
                return kw['validator'](dict(valid=True,reason='期限と検証日時を要求に照らして確認しました'))
            self.assertEqual(cfg['model'],'experiment-oracle')
            self.assertEqual(kw['request_timeout'],300)
            self.assertIn('2026-10-27',prompt)
            self.assertIn('2023-12-31',prompt)
            self.assertNotIn('1件 / 超過1件',prompt)
            return kw['validator'](dict(expected_text='1件 / 超過1件',basis='期限2023年は検証日の2026年より前なので1件超過'))
        with patch.object(app,'ai_json',side_effect=model):
            fixed=app.repair_qa_exact_oracle('返品管理',raw,formats,self.spec,dict(self.cfg,qa_oracle_model='experiment-oracle',qa_oracle_timeout=300,_qa_reference_clock={'date':'2026-10-27','timezone':'Asia/Tokyo','source':'browser local clock'}),self.root,'base-workflow','期待結果と不一致')
        self.assertEqual(fixed['exact_check']['value'],'1件 / 超過1件')

    def test_date_oracle_audit_rejects_contradictory_basis(self):
        raw=dict(steps=[dict(op='fill',selector='#deadline',value='2026-10-27')])
        candidate=dict(exact_check=dict(op='text_equals',selector='#summary',value='1件 / 超過0件'),oracle_basis='期限が基準日より前だが超過は発生しない')
        cfg=dict(self.cfg,_qa_reference_clock={'date':'2026-10-28'})
        def audit(prompt,cfg,tokens,**kw):
            self.assertIn('"relation":"before"',prompt)
            return kw['validator'](dict(valid=False,reason='未処理の期限が基準日より前で根拠と結果が矛盾する'))
        with patch.object(app,'ai_json',side_effect=audit):
            with self.assertRaisesRegex(app.AutoQAPlanError,'独立監査が未合格'):
                app.qa_audit_date_oracle(raw,self.spec,cfg,[],candidate)

    def test_variant_oracle_receives_prior_operations_but_feature_starts_clean(self):
        prior=[dict(kind='workflow',steps=[dict(op='fill',selector='#order',value='FIRST-123'),dict(op='click',selector='#save')])]
        raw=dict(steps=[dict(op='fill',selector='#order',value='SECOND-456'),dict(op='click',selector='#save')],acceptance=[0],exact_check=dict(op='text_equals',selector='#count',value='1件'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#count',text='2件')])
        prompts=[]
        def model(prompt,cfg,tokens,**kw):
            prompts.append(prompt)
            return kw['validator'](dict(expected_text='2件',basis='2回の登録操作から件数を計算する'))
        with patch.object(app,'ai_json',side_effect=model):
            cfg=dict(self.cfg,_qa_prior_scenarios=prior)
            app.repair_qa_exact_oracle('返品管理',raw,formats,self.spec,cfg,self.root,'base-variant','期待結果と不一致')
            app.repair_qa_exact_oracle('返品管理',raw,formats,self.spec,cfg,self.root,'feature-0-0','期待結果と不一致')
        self.assertIn('FIRST-123',prompts[0]);self.assertIn('SECOND-456',prompts[0])
        self.assertNotIn('FIRST-123',prompts[1]);self.assertIn('SECOND-456',prompts[1])

    def test_action_timeline_counts_attempts_without_assuming_saves(self):
        prior=[dict(steps=[dict(op='click',selector='#submit'),dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#cancel')])]
        current=[dict(op='click',selector='#submit'),dict(op='click',selector='#submit')]
        self.assertEqual(app.qa_action_timeline(prior,current),[
            dict(selector='#cancel',prior=1,current=0),dict(selector='#submit',prior=1,current=2)])

    def test_variant_must_not_repeat_identical_inputs_and_actions(self):
        steps=[dict(op='fill',selector='#order',value='123456'),dict(op='click',selector='#save')]
        prior=[dict(kind='workflow',steps=steps)]
        self.assertTrue(app.qa_variant_repeats_workflow(dict(steps=copy.deepcopy(steps)),prior))
        changed=copy.deepcopy(steps);changed[0]['value']='654321'
        self.assertFalse(app.qa_variant_repeats_workflow(dict(steps=changed),prior))
        self.assertFalse(app.qa_variant_repeats_workflow(dict(steps=steps),[]))

    def test_missing_date_selector_only_repaired_when_unique(self):
        value={'steps':[{'op':'fill','value':'2026-10-27'}]}
        one={'controls':[{'tag':'input','type':'date','selector':'#class_date'}]}
        self.assertEqual(app.qa_resolve_unique_date_selector(value,one)['steps'][0]['selector'],'#class_date')
        self.assertNotIn('selector',value['steps'][0])
        ambiguous={'controls':one['controls']+[{'tag':'input','type':'date','selector':'#other'}]}
        self.assertNotIn('selector',app.qa_resolve_unique_date_selector(value,ambiguous)['steps'][0])

    def test_contradictory_expectations_are_not_accepted(self):
        value={'steps':[{'op':'fill','selector':'#item','value':'A'},{'op':'click','selector':'#save'}],
               'checks':[{'op':'text_contains','selector':'#summary','value':'2件'}, {'op':'visible','selector':'#item'}],
               'exact_check':{'op':'text_equals','selector':'#summary','value':'1件'},'acceptance':[0], 'result_selector':'#summary'}
        with self.assertRaisesRegex(app.AutoQAPlanError,'矛盾'):app.validate_qa_unit(value,'workflow',1)
        value['exact_check']['value']='2件'
        app.validate_qa_unit(value,'workflow',1)

    def test_conflicting_oracle_repair_preserves_actions_and_independent_checks(self):
        raw=dict(steps=[dict(op='fill',selector='#item',value='A'),dict(op='click',selector='#save')],
                 checks=[dict(op='text_contains',selector='#summary',value='1件'),dict(op='visible',selector='#item')],
                 exact_check=dict(op='text_equals',selector='#summary',value='2件'),acceptance=[0])
        def model(prompt,cfg,tokens,**kw):
            self.assertNotIn('実測値:2件',prompt)
            return kw['validator'](dict(expected_text='2件',replacement_values=['2件'],basis='先行入力と今回入力を照合し2件と計算'))
        with patch.object(app,'ai_json',side_effect=model):
            result=app.repair_qa_conflicting_checks(raw,self.spec,self.cfg,self.root,'base-variant',[])
        self.assertEqual(result['steps'],raw['steps'])
        self.assertEqual(result['checks'][1],raw['checks'][1])
        self.assertEqual(result['checks'][0]['value'],'2件')
        app.validate_qa_unit(result,'variant',len(self.spec['acceptance']))
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](dict(expected_text='2件',replacement_values=['1件'],basis='入力から独立に計算した結果です'))):
            with self.assertRaises(app.AutoQAPlanError):app.repair_qa_conflicting_checks(raw,self.spec,self.cfg,self.root,'base-variant',[])

    def test_conflicting_full_matches_share_one_computed_expectation(self):
        raw=dict(steps=[dict(op='fill',selector='#item',value='A'),dict(op='click',selector='#save')],
                 checks=[dict(op='text_equals',selector='#summary',value='1件'),dict(op='visible',selector='#item')],
                 exact_check=dict(op='text_equals',selector='#summary',value='2件'),acceptance=[0])
        formats={'#summary':{'template':'{n0}件','slots':1}}
        def model(prompt,cfg,tokens,**kw):
            self.assertIn('{n0}件',prompt)
            return kw['validator'](dict(expected_text='2件',replacement_values=[],basis='入力済みの2件から集計した結果'))
        with patch.object(app,'ai_json',side_effect=model):
            result=app.repair_qa_conflicting_checks(raw,self.spec,self.cfg,self.root,'base-variant',[],formats)
        self.assertEqual(result['checks'][0]['value'],'2件')
        self.assertEqual(result['steps'],raw['steps'])
        app.validate_qa_unit(result,'variant',len(self.spec['acceptance']))

    def test_oracle_census_reports_inputs_without_assuming_population_or_success(self):
        prior=[dict(kind='workflow',steps=[dict(op='select',selector='#status',value='出席'),dict(op='click',selector='#save')])]
        current=[dict(op='select',selector='#status',value='欠席'),dict(op='click',selector='#delete')]
        self.assertEqual(app.qa_independent_input_history(prior,current),[
            dict(phase='prior',op='select',selector='#status',value='出席'),
            dict(phase='current',op='select',selector='#status',value='欠席')])
        raw=dict(steps=current,acceptance=[0],exact_check=dict(selector='#count',value='1'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#count',text='2件')])
        prompts=[]
        def model(prompt,cfg,tokens,**kw):
            prompts.append(prompt)
            return kw['validator'](dict(expected_text='1件',basis='入力状態から独立に検査内容を判断します'))
        with patch.object(app,'ai_json',side_effect=model):
            app.repair_qa_exact_oracle('授業',raw,formats,self.spec,dict(self.cfg,_qa_prior_scenarios=prior),self.root,'base-variant','期待結果と不一致')
            app.repair_qa_exact_oracle('授業',raw,formats,self.spec,dict(self.cfg,_qa_prior_scenarios=prior),self.root,'base-workflow','期待結果と不一致')
        self.assertIn('保存成功・存在人数は意味しない',prompts[0])
        self.assertIn('出席',prompts[0]);self.assertIn('欠席',prompts[0])
        self.assertIn('空のブラウザ保存から開始',prompts[1]);self.assertNotIn('出席',prompts[1])

    def test_independent_clock_arithmetic_does_not_assume_overnight_or_breaks(self):
        steps=[dict(op='fill',selector='#start',value='09:00'),dict(op='fill',selector='#end',value='17:30'),
               dict(op='fill',selector='#next',value='01:00'),dict(op='fill',selector='#invalid',value='25:30')]
        facts=app.qa_independent_clock_differences(steps)
        self.assertEqual(facts[0],dict(start_selector='#start',start='09:00',end_selector='#end',end='17:30',signed_minutes=510))
        self.assertEqual(facts[1]['signed_minutes'],-480)
        self.assertEqual(len(facts),3)

    def test_declared_calculation_is_independent_of_product_output(self):
        spec=dict(independent_calculations=[dict(scenario_kind='workflow', bindings={'start':'#start','end':'#end','breaks':'#break'}, expression='end-start-breaks', output_selector='#total', expected_template='{value}分')])
        value=dict(steps=[dict(op='fill',selector='#start',value='540'),dict(op='fill',selector='#end',value='1020'),dict(op='fill',selector='#break',value='60')], checks=[dict(op='text_equals',selector='#total',value='420分')])
        self.assertEqual(app.qa_validate_declared_calculations(value,spec,'workflow'),value)
        bad=copy.deepcopy(value);bad['checks'][0]['value']='480分'
        with self.assertRaisesRegex(app.AutoQAPlanError,'独立計算'):app.qa_validate_declared_calculations(bad,spec,'workflow')
        self.assertEqual(app.qa_validate_declared_calculations(bad,spec,'variant'),bad)
        missing=copy.deepcopy(value);missing['steps'].pop()
        with self.assertRaises(app.AutoQAPlanError):app.qa_validate_declared_calculations(missing,spec,'workflow')
        duplicate=copy.deepcopy(value);duplicate['steps'].append(dict(op='fill',selector='#end',value='1000'))
        with self.assertRaises(app.AutoQAPlanError):app.qa_validate_declared_calculations(duplicate,spec,'workflow')
        unsafe=copy.deepcopy(spec);unsafe['independent_calculations'][0]['expression']='__import__(1)'
        with self.assertRaises(app.AutoQAPlanError):app.qa_validate_declared_calculations(value,unsafe,'workflow')
        ratio=copy.deepcopy(spec);ratio['independent_calculations'][0]['expression']='start/end'
        with self.assertRaisesRegex(app.AutoQAPlanError,'丸め'):app.qa_validate_declared_calculations(value,ratio,'workflow')
        zero=copy.deepcopy(spec);zero['independent_calculations'][0]['expression']='end/(start-start)'
        with self.assertRaises(app.AutoQAPlanError):app.qa_validate_declared_calculations(value,zero,'workflow')

    def test_targeted_oracle_repair_requires_resolved_complete_text(self):
        raw=dict(steps=[],acceptance=[0],exact_check=dict(selector='#count',value='1'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#count',text='4件')])
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](dict(expected_text='{n0}件',basis='入力から数値だけを計算する根拠があります'))):
            with self.assertRaises(app.AutoQAPlanError):app.repair_qa_exact_oracle('返品管理',raw,formats,self.spec,self.cfg,self.root,'base-workflow','expected_values')

    def test_invalid_submission_repair_is_bound_to_browser_evidence(self):
        steps=[dict(op='fill',selector='#title',value='開発'),dict(op='click',selector='#save')]
        raw=dict(steps=steps,checks=[dict(op='text_equals',selector='#total',value='420')],acceptance=[0])
        observation=dict(steps=steps,operation=steps[-1],invalid_fields=[dict(selector='#date'),dict(selector='#status')])
        inventory=dict(controls=[dict(tag='input',type='date',selector='#date'),dict(tag='select',selector='#status',options=[dict(value='done',label='完了')])],outputs=[])
        def model(prompt,cfg,tokens,**kw):
            self.assertIn('#date',prompt);self.assertIn('done',prompt)
            return kw['validator'](dict(inputs=[dict(selector='#date',value='2026-10-27'),dict(selector='#status',value='done')]))
        with patch.object(app,'ai_json',side_effect=model):
            fixed=app.repair_qa_invalid_submission(raw,observation,inventory,self.cfg)
        self.assertEqual(fixed['checks'],raw['checks']);self.assertEqual(fixed['steps'][-1],steps[-1])
        self.assertEqual(fixed['steps'][1:3],[dict(op='fill',selector='#date',value='2026-10-27'),dict(op='select',selector='#status',value='done')])
        self.assertIsNone(app.repair_qa_invalid_submission(raw,dict(observation,steps=[]),inventory,self.cfg))
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](dict(inputs=[dict(selector='#date',value='2026-10-27'),dict(selector='#status',value='invented')]))):
            with self.assertRaises(app.AutoQAPlanError):app.repair_qa_invalid_submission(raw,observation,inventory,self.cfg)

    def test_malformed_operation_reports_exact_index_for_repair(self):
        value=dict(steps=[dict(op='fill',selector='#date',value='2026-10-27'),dict(op='fill',contains=['#start','start']),dict(op='click',selector='#save')],
            checks=[dict(op='text_equals',selector='#result',value='ok'),dict(op='visible',selector='#result')],acceptance=[0],result_selector='#result')
        with self.assertRaisesRegex(app.AutoQAPlanError,r'steps\[1\].*selector'):
            app.validate_qa_unit(value,'workflow',1)

    def test_number_control_rejects_time_text_without_guessing_conversion(self):
        inventory=dict(controls=[dict(tag='input',type='number',selector='#planned_minutes')],outputs=[])
        value=dict(steps=[dict(op='fill',selector='#planned_minutes',value='08:00')])
        with self.assertRaisesRegex(app.AutoQAPlanError,'単位'):
            app.validate_qa_inventory_actions(value,inventory,'workflow')
        value['steps'][0]['value']='480'
        self.assertEqual(app.validate_qa_inventory_actions(value,inventory,'workflow'),value)

    def test_invalid_case_requires_actual_invalid_required_field_when_known(self):
        inventory=dict(controls=[dict(tag='input',selector='#item',form='#form',required=True),dict(tag='button',selector='#save',form='#form')],outputs=[])
        value=dict(steps=[dict(op='fill',selector='#item',value='invalid_item'),dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#summary',value='unchanged')])
        with self.assertRaisesRegex(app.AutoQAPlanError,'任意文字列'):
            app.validate_qa_inventory_actions(value,inventory,'invalid')
        value['steps'][0]['value']='';value['checks'].append(dict(op='invalid',selector='#item'))
        self.assertEqual(app.validate_qa_inventory_actions(value,inventory,'invalid'),value)

    def test_oracle_rejects_missing_percentage_without_inventing_value(self):
        raw=dict(steps=[],acceptance=[0],exact_check=dict(selector='#summary',value='wrong'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='100%（出席扱い1/1、欠席0）')])
        bad=dict(expected_text='出欠記録一覧（出席扱い1/1、欠席0）',basis='一人が出席し欠席者はいないため')
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](bad)):
            with self.assertRaisesRegex(app.AutoQAPlanError,'割合'):app.repair_qa_exact_oracle('授業',raw,formats,self.spec,self.cfg,self.root,'base-workflow','期待結果と不一致')
        wrapped=dict(expected_text='出欠記録一覧（出席扱い100%（出席扱い1/1、欠席0））',basis='一人が出席し欠席者はいないため')
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](wrapped)):
            with self.assertRaisesRegex(app.AutoQAPlanError,'見出しや一覧'):app.repair_qa_exact_oracle('授業',raw,formats,self.spec,self.cfg,self.root,'base-workflow','期待結果と不一致')
        good=dict(expected_text='50%（出席扱い1/2、欠席1）',basis='一人が出席しもう一人が欠席のため')
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](good)):
            result=app.repair_qa_exact_oracle('授業',raw,formats,self.spec,self.cfg,self.root,'base-workflow','期待結果と不一致')
        self.assertEqual(result['exact_check']['value'],good['expected_text'])

    def test_percentage_retry_uses_only_independent_numeric_and_literal_answers(self):
        raw=dict(steps=[],acceptance=[0],exact_check=dict(selector='#summary',value='wrong'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='100%（出席扱い1/1、欠席0）')])
        def model(prompt,cfg,tokens,**kw):
            self.assertNotIn('100%（出席扱い1/1、欠席0）',prompt)
            return kw['validator'](dict(expected_values=['50','1','2','1'],expected_literals=['','%（出席扱い','/','、欠席','）'],basis='二人中一人が出席し一人が欠席したため'))
        with patch.object(app,'ai_json',side_effect=model):
            result=app.repair_qa_exact_oracle('授業',raw,formats,self.spec,self.cfg,self.root,'base-workflow','対象要素は割合から始まります')
        self.assertEqual(result['exact_check']['value'],'50%（出席扱い1/2、欠席1）')
        self.assertEqual(result['steps'],raw['steps'])

    def test_percentage_variant_retry_receives_prior_steps_and_expectations(self):
        raw=dict(steps=[dict(op='fill',selector='#status',value='欠席')],acceptance=[0],exact_check=dict(selector='#summary',value='wrong'))
        formats=app.qa_display_contracts_from_nodes([dict(selector='#summary',text='100%（出席扱い1/1、欠席0）')])
        prior=[dict(kind='workflow',steps=[dict(op='fill',selector='#status',value='出席')],checks=[dict(op='text_equals',selector='#summary',value='100%（出席扱い1/1、欠席0）')])]
        def model(prompt,cfg,tokens,**kw):
            self.assertIn('先行検査の入力と独立した期待値',prompt)
            self.assertIn('出席',prompt);self.assertIn('欠席',prompt)
            return kw['validator'](dict(expected_values=['50','1','2','1'],expected_literals=['','%（出席扱い','/','、欠席','）'],basis='最初の出席と今回の欠席で二人となるため'))
        with patch.object(app,'ai_json',side_effect=model):
            result=app.repair_qa_exact_oracle('授業',raw,formats,self.spec,dict(self.cfg,_qa_prior_scenarios=prior),self.root,'base-variant','主結果は割合から始まります')
        self.assertEqual(result['exact_check']['value'],'50%（出席扱い1/2、欠席1）')

    def test_literal_check_repair_can_only_change_selector(self):
        fault=dict(op='text_contains',selector='#notice',value='登録者A')
        raw=dict(steps=[dict(op='fill',selector='#name',value='登録者A'),dict(op='click',selector='#save')],checks=[fault,dict(op='text_equals',selector='#rate',value='100%')])
        inventory=dict(controls=[],outputs=[dict(tag='div',selector='#notice',text='通知'),dict(tag='tbody',selector='#rows',text='記録一覧')])
        with patch.object(app,'ai_json',side_effect=lambda p,c,t,**kw:kw['validator'](dict(selector='#rows',reason='登録した内容は記録一覧に表示されるため'))):
            repaired=app.repair_qa_literal_selector(raw,fault,inventory,self.cfg,self.root,'base-workflow')
        self.assertEqual(repaired['steps'],raw['steps'])
        self.assertEqual(repaired['checks'][0],dict(fault,selector='#rows'))
        self.assertEqual(repaired['checks'][1],raw['checks'][1])
        self.assertIsNone(app.repair_qa_literal_selector(raw,dict(fault,value='観測値を採用'),inventory,self.cfg,self.root,'base-workflow'))

