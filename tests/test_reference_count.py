"""Reference-state tests. These do not claim real-model or product acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('reference_module',Path(__file__).resolve().parents[1]/'agent'/'qa_checkpoint_planner.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
qa.AutoQAPlanError=ValueError

class ReferenceCountTests(unittest.TestCase):
    def test_wrapping_labels_feed_real_input_units_to_normalization(self):
        inventory=qa.compact_qa_inventory('<label><span>休憩（分）</span><input id="break" type="number"></label><label>状態<select id="status"><option>選択</option></select></label>')
        self.assertEqual(inventory['controls'][0]['label'],'休憩（分）')
        self.assertEqual(inventory['controls'][1]['label'],'状態')
        raw=dict(steps=[dict(op='fill',selector='#break',value='01:00')])
        self.assertEqual(qa.qa_normalize_duration_inputs(raw,inventory)['steps'][0]['value'],'60')

    def test_explicit_duration_normalization_does_not_guess_units(self):
        raw=dict(steps=[dict(op='fill',selector='#break',value='01:00')],exact_check=dict(value='unchanged'))
        result=qa.qa_normalize_duration_inputs(raw,dict(controls=[dict(selector='#break',type='number',label='休憩時間（分）')]))
        self.assertEqual(result['steps'][0]['value'],'60')
        self.assertEqual(result['exact_check'],raw['exact_check'])
        self.assertEqual(raw['steps'][0]['value'],'01:00')
        for label in ('休憩','開始時間（分）','休憩時間（時間）'):
            self.assertEqual(qa.qa_normalize_duration_inputs(raw,dict(controls=[dict(selector='#break',type='number',label=label)])),raw)

    def test_impossible_percentage_denominator_is_rejected(self):
        with self.assertRaises(ValueError):qa.qa_validate_explicit_percentage('1%（出席扱い1/0、欠席0）')
        self.assertEqual(qa.qa_validate_explicit_percentage('100%（出席扱い1/1、欠席0）'),'100%（出席扱い1/1、欠席0）')

    def test_fraction_oracle_computes_percentage_without_model_arithmetic(self):
        from unittest.mock import patch
        raw=dict(steps=[dict(op='click',selector='#save')],acceptance=[0],exact_check=dict(selector='#summary',value='1%'))
        formats={'#summary':dict(template='{n0}%（出席扱い{n1}/{n2}、欠席{n3}）',slots=4)}
        def model(prompt,cfg,tokens,**kw):
            self.assertEqual(kw['schema']['properties']['expected_values']['maxItems'],3)
            return kw['validator'](dict(expected_values=['1','1','0'],basis='空の保存状態から一人を登録し、出席一人、総数一人、欠席ゼロ'))
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t, patch.object(qa,'qa_audit_date_oracle',side_effect=lambda r,s,c,p,a:a):
            fixed=qa.repair_qa_exact_oracle('授業',raw,formats,dict(acceptance=['登録して出席率を確認']),dict(model='x'),Path(t),'base-workflow','期待結果と不一致')
        self.assertEqual(fixed['exact_check']['value'],'100%（出席扱い1/1、欠席0）')
        self.assertEqual(fixed['steps'],raw['steps'])

    def test_mapping_role_survives_coding_planner_retry(self):
        cfg=dict(model='coder',qa_mapping_model='semantic',qa_oracle_model='auditor')
        self.assertEqual(qa.qa_reference_model_config(cfg)['model'],'semantic')
        self.assertEqual(cfg['model'],'coder')
        self.assertEqual(qa.qa_reference_model_config(dict(model='coder',qa_oracle_model='auditor'))['model'],'auditor')

    def test_create_edit_delete_state_and_mutants(self):
        steps=[dict(op='click',selector='#save') for _ in range(4)]
        events=[dict(step_index=0,effect='create',target=None),dict(step_index=1,effect='create',target=None),dict(step_index=2,effect='update',target=0),dict(step_index=3,effect='delete',target=1)]
        good=qa.qa_evaluate_record_events(steps,events)
        self.assertEqual([x['count'] for x in good['trace']],[1,2,2,1])
        for index,effect in ((2,'create'),(3,'none')):
            mutant=[dict(x) for x in events];mutant[index]=dict(step_index=index,effect=effect,target=None)
            self.assertNotEqual([x['count'] for x in qa.qa_evaluate_record_events(steps,mutant)['trace']],[1,2,2,1])

    def test_missing_duplicate_reordered_and_nonexistent_targets_fail_closed(self):
        steps=[dict(op='click'),dict(op='fill'),dict(op='click')]
        first=dict(step_index=0,effect='create',target=None)
        second=dict(step_index=2,effect='delete',target=0)
        for events in ([first],[first,first],[second,first],[first,dict(second,target=9)],[dict(first,effect='update',target=0),second]):
            with self.assertRaises(ValueError):qa.qa_evaluate_record_events(steps,events)

    def test_non_count_output_has_no_reference_claim(self):
        self.assertIsNone(qa.qa_reference_count_oracle({'exact_check':{'selector':'#minutes'}},{},{},{},None,'base-workflow',[]))

    def test_numeric_answer_is_computed_after_binding_and_audit(self):
        calls=[];models=[]
        def model(prompt,cfg,tokens,**kwargs):
            calls.append(prompt);models.append(cfg['model'])
            answer=(dict(quantity='record_count',source_index=0,events=[]) if len(calls)==1 else dict(effect='create',target=None) if prompt.startswith('一つのclick') else dict(valid=True,reason='二つの保存操作は元仕様に基づく別記録の追加である'))
            return kwargs['validator'](answer)
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        prior=[dict(steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#save')])]
        raw=dict(steps=[dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')],exact_check=dict(selector='#recordCount',value='999'))
        with tempfile.TemporaryDirectory() as t:
            result=qa.qa_reference_count_oracle(raw,{},dict(must_have=['返品記録を追加']),dict(model='coder-retry',qa_mapping_model='semantic',qa_oracle_model='auditor'),Path(t),'base-variant',prior)
            self.assertEqual(result['exact_check']['value'],'2')
            self.assertEqual(result['steps'],raw['steps'])
            self.assertTrue((Path(t)/'base-variant-reference-count-proof.json').exists())
        self.assertEqual(len(calls),4)
        self.assertEqual(models,['semantic','semantic','semantic','auditor'])
        self.assertNotIn('999',''.join(calls))


    def test_composite_preserves_other_business_values_and_repairs_duplicates(self):
        from unittest.mock import patch
        raw=dict(steps=[dict(op='click',selector='#save')],exact_check=dict(selector='#summary',value='1件 / 超過3件'),checks=[dict(op='text_equals',selector='#summary',value='1件 / 超過3件'),dict(op='text_contains',selector='#summary',value='1件'),dict(op='text_contains',selector='#rows',value='商品A')])
        def model(prompt,cfg,tokens,**kw):
            return kw['validator'](dict(suffix='件 / 超過3件',contains_values=['2件'],basis='期限と状態に基づいて超過件数を独立判定する'))
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t, patch.object(qa,'qa_reference_count_oracle',return_value=dict(reference_count=dict(count=2),oracle_basis='参照状態による計算')):
            result=qa.qa_reference_composite_oracle(raw,{'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2)},dict(acceptance=['返品を追加']),dict(model='x'),Path(t),'base-variant',[])
        self.assertEqual(result['exact_check']['value'],'2件 / 超過3件')
        self.assertEqual(result['checks'][0]['value'],'2件 / 超過3件')
        self.assertEqual(result['checks'][1]['value'],'2件')
        self.assertEqual(result['checks'][2],raw['checks'][2])
        self.assertEqual(result['steps'],raw['steps'])
        self.assertEqual(raw['exact_check']['value'],'1件 / 超過3件')

    def test_first_submit_required_inputs_and_defaults(self):
        controls=[dict(selector='#title',tag='input',required=True,form='#f'),dict(selector='#status',tag='select',required=True,form='#f',options=[dict(value='',label='選択'),dict(value='open',label='未処理',selected=True)]),dict(selector='#save',tag='button',form='#f')]
        value=dict(steps=[dict(op='click',selector='#save')])
        self.assertEqual(qa.qa_missing_initial_required_inputs(value,dict(controls=controls)),['#title'])
        value['steps'].insert(0,dict(op='fill',selector='#title',value='仕事A'))
        self.assertEqual(qa.qa_missing_initial_required_inputs(value,dict(controls=controls)),[])
        controls[0]['disabled']=True;value['steps']=value['steps'][1:]
        self.assertEqual(qa.qa_missing_initial_required_inputs(value,dict(controls=controls)),[])


    def test_missing_input_repair_changes_only_missing_control(self):
        inventory=dict(controls=[dict(tag='input',selector='#title',form='#f',required=True),dict(tag='input',selector='#minutes',form='#f'),dict(tag='button',selector='#save',form='#f')],outputs=[])
        raw=dict(steps=[dict(op='fill',selector='#minutes',value='30'),dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#total',value='30')])
        def model(prompt,cfg,tokens,**kw):
            self.assertIn('事前検査',prompt)
            self.assertIn('元仕様',prompt)
            self.assertNotIn('ブラウザが送信を拒否した',prompt)
            return kw['validator'](dict(inputs=[dict(selector='#title',value='仕事A')]))
        qa.ai_json=model
        fixed=qa.repair_qa_missing_initial_inputs(raw,inventory,dict(model='x'),dict(must_have=['仕事を登録']))
        self.assertEqual(fixed['checks'],raw['checks'])
        self.assertEqual(fixed['steps'][0],raw['steps'][0])
        self.assertEqual(fixed['steps'][1],dict(op='fill',selector='#title',value='仕事A'))
        self.assertEqual(fixed['steps'][2],raw['steps'][1])
        self.assertEqual(len(raw['steps']),2)

    def test_source_number_cannot_select_nonexistent_requirement(self):
        def model(prompt,cfg,tokens,**kw):
            return kw['validator'](dict(quantity='record_count',source_index=99,events=[]))
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t, self.assertRaises(ValueError):
            qa.qa_reference_count_oracle(dict(steps=[],exact_check=dict(selector='#recordCount')),{},dict(must_have=['記録を登録']),dict(model='x'),Path(t),'base-workflow',[])


    def test_type_repair_replaces_only_rejected_values_and_preserves_oracle(self):
        inventory=dict(controls=[dict(selector='#minutes',type='number',label='予定（分）'),dict(selector='#deadline',type='date')])
        raw=dict(steps=[dict(op='fill',selector='#minutes',value='08:00'),dict(op='fill',selector='#deadline',value='2026-10-29T23:59:59'),dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#total',value='480')])
        def model(prompt,cfg,tokens,**kw):
            return kw['validator'](dict(inputs=[dict(step_index=0,value='480'),dict(step_index=1,value='2026-10-29')]))
        qa.ai_json=model
        fixed=qa.repair_qa_typed_inputs(raw,inventory,dict(model='x'),dict(must_have=['予定8時間を分で保存']))
        self.assertEqual([s.get('value') for s in fixed['steps'][:2]],['480','2026-10-29'])
        self.assertEqual(fixed['checks'],raw['checks'])
        self.assertEqual(fixed['steps'][2],raw['steps'][2])
        self.assertEqual(raw['steps'][0]['value'],'08:00')
        self.assertEqual(qa.qa_bad_typed_inputs(fixed,inventory),[])

    def test_calendar_validation_rejects_nonexistent_and_timestamp_dates(self):
        inventory=dict(controls=[dict(selector='#date',type='date')])
        for value in ('2026-02-30','2026-10-29T12:00:00','29/10/2026'):
            self.assertEqual(len(qa.qa_bad_typed_inputs(dict(steps=[dict(op='fill',selector='#date',value=value)]),inventory)),1)
        self.assertEqual(qa.qa_bad_typed_inputs(dict(steps=[dict(op='fill',selector='#date',value='2028-02-29')]),inventory),[])


    def test_click_enumeration_excludes_fill_and_reuses_completed_binding(self):
        steps=[dict(op='fill',selector='#field'+str(i),value=str(i)) for i in range(10)]+[dict(op='click',selector='#save')]
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            calls.append(prompt)
            self.assertNotIn('step_index',kw['schema']['properties'])
            return kw['validator'](dict(effect='create',target=None))
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t:
            first=qa.qa_bind_record_clicks(steps,'元仕様','#recordCount',dict(model='x'),Path(t),'workflow')
            second=qa.qa_bind_record_clicks(steps,'元仕様','#recordCount',dict(model='x'),Path(t),'workflow')
        self.assertEqual(first,[dict(step_index=10,effect='create',target=None)])
        self.assertEqual(second,first)
        self.assertEqual(len(calls),1)
        self.assertEqual(qa.qa_evaluate_record_events(steps,first)['count'],1)


    def test_reference_audit_targets_component_mapping_not_product_coverage(self):
        binding=dict(quantity='record_count',source_quote='返品記録を登録する',events=[dict(step_index=0,effect='create',target=None)],source_index=0)
        prompt=qa.qa_reference_mapping_audit_prompt('#recordCount',[dict(op='click',selector='#save')],binding)
        self.assertIn('全製品機能の網羅性を採点しない',prompt)
        self.assertIn('返品記録を登録する',prompt)
        self.assertIn('具体的な対応誤り',prompt)
        self.assertIn('情報不足はvalid:false',prompt)
        self.assertNotIn('source_index',prompt)


    def test_event_schema_only_offers_existing_record_origins(self):
        empty=qa.qa_record_event_schema([])
        self.assertEqual(empty['properties']['effect']['enum'],['create','none'])
        self.assertEqual(empty['properties']['target']['enum'],[None])
        existing=qa.qa_record_event_schema([7,2])
        self.assertEqual(existing['properties']['target']['enum'],[None,2,7])
        self.assertIn('delete',existing['properties']['effect']['enum'])
        prompt=qa.qa_reference_mapping_audit_prompt('#count',[],dict(quantity='record_count',source_quote='記録を保存',events=[]))
        self.assertIn('createは新しい記録を作るため既存対象targetはnullが正しい',prompt)
        self.assertIn('対象情報不足と判断しない',prompt)


    def test_audit_material_never_presents_field_edits_as_records(self):
        steps=[dict(op='fill',selector='#f'+str(i),value=str(i)) for i in range(6)]+[dict(op='click',selector='#save')]
        events=[dict(step_index=6,effect='create',target=None)]
        cases=qa.qa_reference_click_audit_cases(steps,events)
        self.assertEqual(len(cases),1)
        self.assertEqual(cases[0]['click_index'],6)
        self.assertEqual(len(cases[0]['entered_fields']),6)
        self.assertEqual(cases[0]['proposed_effect'],events[0])
        prompt=qa.qa_reference_mapping_audit_prompt('#count',steps,dict(quantity='record_count',source_quote='返品記録を追加',events=events))
        self.assertIn('初期状態は空の保存領域',prompt)
        self.assertIn('入力欄の数を記録数と解釈しない',prompt)

if __name__=='__main__':unittest.main()







