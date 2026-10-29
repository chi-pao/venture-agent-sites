"""Reference-state tests. These do not claim real-model or product acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('reference_module',Path(__file__).resolve().parents[1]/'agent'/'qa_checkpoint_planner.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
qa.AutoQAPlanError=ValueError
contract_spec=importlib.util.spec_from_file_location('spec_contract',Path(__file__).resolve().parents[1]/'agent'/'department_spec_contract.py')
contract=importlib.util.module_from_spec(contract_spec);contract_spec.loader.exec_module(contract)

class ReferenceCountTests(unittest.TestCase):
    def test_bound_primary_cannot_omit_numeric_display_slots(self):
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2)}
        original=qa.qa_unit_schema(1,'workflow')['properties']['exact_check']
        schema=qa.qa_bound_primary_schema(original,'#summary',formats)
        props=schema['properties']['exact_check']['properties']
        self.assertNotIn('value',props)
        self.assertEqual(set(props['display_parts']['required']),{'n0','n1','l0','l1','l2'})
        self.assertEqual(props['display_parts']['properties']['l0']['enum'],[''])
        with self.assertRaises(ValueError):qa.qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector='#summary',value='1')),'#summary',formats)
        answer=dict(exact_check=dict(op='text_equals',selector='#summary',expected_values=['2','0'],expected_literals=['','件 / 超過','件']))
        result=qa.qa_compile_bound_primary(answer,'#summary',formats)
        self.assertEqual(result['exact_check']['value'],'2件 / 超過0件')

    def test_named_display_slots_reject_units_and_fabricated_headings(self):
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2)}
        parts=dict(n0='1',n1='0',l0='',l1='件 / 超過',l2='件')
        raw=dict(exact_check=dict(op='text_equals',selector='#summary',display_parts=parts))
        self.assertEqual(qa.qa_compile_bound_primary(raw,'#summary',formats)['exact_check']['value'],'1件 / 超過0件')
        for change in (dict(n0='1%'),dict(l0='集計:'),dict(l1='1件 / 超過'),dict(n2='9')):
            bad=dict(exact_check=dict(raw['exact_check'],display_parts=dict(parts,**change)))
            with self.assertRaises(ValueError):qa.qa_compile_bound_primary(bad,'#summary',formats)
        self.assertNotIn('expected_values',raw['exact_check'])

    def test_split_oracle_receives_masked_format_contract(self):
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2),'#other':dict(template='{n0}円',slots=1)}
        spec=dict(acceptance=['登録して件数と超過を確認する'])
        view=qa.json.loads(qa.qa_split_stage_context('',dict(_qa_spec=spec,_qa_display_contracts=formats),dict(controls=[],outputs=[]),'base-workflow',dict(result_selector='#summary',acceptance=[0],steps=[])))
        self.assertEqual(view['display_contracts'],{'#summary':formats['#summary']})
    def test_json_fallback_still_rejects_wrong_native_operations(self):
        inventory=qa.compact_qa_inventory('<input id="date" type="date"><input id="minutes" type="number"><select id="status"><option value="open">未着手</option></select><button id="save">保存</button>')
        schema=qa.qa_bound_step_schema(qa.qa_unit_schema(1,'workflow')['properties']['steps']['items'],inventory,'workflow')
        for step in (dict(op='select',selector='#date',value='2026-10-29'),dict(op='select',selector='#status',value='missing'),dict(op='fill',selector='#minutes',value='01:00'),dict(op='click',selector='#invented')):
            with self.assertRaises(ValueError):qa.qa_validate_step_choices(dict(steps=[step]),schema)
        raw=dict(steps=[dict(op='fill',selector='#date',value='2026-10-29'),dict(op='select',selector='#status',value='open'),dict(op='click',selector='#save')])
        self.assertEqual(qa.qa_validate_step_choices(raw,schema),raw)
    def test_bound_schema_never_offers_date_input_as_select(self):
        inventory=qa.compact_qa_inventory('<input id="date" type="date"><input id="minutes" type="number"><select id="status"><option value="open">未着手</option></select><button id="save">保存</button>')
        schema=qa.qa_bound_step_schema(qa.qa_unit_schema(1,'workflow')['properties']['steps']['items'],inventory,'workflow')
        select=[b for b in schema['anyOf'] if b['properties']['op'].get('enum')==['select']]
        self.assertEqual(len(select),1)
        self.assertEqual(select[0]['properties']['selector']['enum'],['#status'])
        self.assertEqual(select[0]['properties']['value']['enum'],['open'])
        date=[b for b in schema['anyOf'] if b['properties']['op'].get('enum')==['fill'] and '#date' in b['properties']['selector']['enum']]
        self.assertEqual(date[0]['properties']['value']['pattern'],r'^\d{4}-\d{2}-\d{2}$')

    def test_oracle_context_keeps_only_selected_full_criteria_and_operations(self):
        spec=dict(audience='講師',requested_outcome='出欠確認',acceptance=['登録Aの具体的な正解を最後まで記載','無関係な別条件の長い入力例'],acceptance_source_requirements=['登録','別条件'])
        inventory=dict(controls=[dict(tag='input',selector='#a'),dict(tag='input',selector='#b')],outputs=[dict(tag='strong',selector='#count',text='999')])
        actions=dict(acceptance=[0],steps=[dict(op='fill',selector='#a',value='A')])
        view=qa.json.loads(qa.qa_split_stage_context('old',dict(_qa_spec=spec),inventory,'base-workflow',actions))
        self.assertEqual(view['conditions_by_index'],{'0':spec['acceptance'][0]})
        self.assertEqual([n['selector'] for n in view['controls']],['#a'])
        self.assertNotIn('999',qa.json.dumps(view))
        self.assertNotIn(spec['acceptance'][1],qa.json.dumps(view,ensure_ascii=False))

    def test_workflow_cannot_overwrite_three_records_before_one_save(self):
        bad=dict(steps=[dict(op='fill',selector='#student',value=name) for name in ('A','B','C')]+[dict(op='click',selector='#save')])
        with self.assertRaises(ValueError):qa.qa_validate_workflow_overwrites(bad)
        good=dict(steps=[dict(op='fill',selector='#student',value='A'),dict(op='click',selector='#save'),dict(op='fill',selector='#student',value='B'),dict(op='click',selector='#save')])
        self.assertEqual(qa.qa_validate_workflow_overwrites(good),good)

    def test_split_generation_resumes_only_timed_out_assertion(self):
        inventory=qa.compact_qa_inventory('<form id="f"><input id="title"><button id="save" type="submit">保存</button></form><strong id="count">0</strong><tbody id="rows"></tbody>')
        calls=[];timeout=[True]
        def model(prompt,cfg,tokens,**kw):
            name=Path(cfg['_json_transport_evidence']).stem.removesuffix('-transport');calls.append(name)
            if name.startswith('secondary-'):
                options=kw['schema']['properties']['check']['properties']['selector']['enum']
                self.assertNotIn('#count',options)
                if name=='secondary-1':self.assertNotIn('#title',options)
            if name=='actions':answer=dict(steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#save')],acceptance=[0],rationale='入力した記録を保存して件数を照合',result_selector='#count')
            elif name=='primary':answer=dict(exact_check=dict(op='text_equals',selector='#count',value='1'))
            elif name=='secondary-0':answer=dict(check=dict(op='value_equals',selector='#title',value='A'))
            else:
                if timeout[0]:timeout[0]=False;raise TimeoutError('fixed failed assertion')
                answer=dict(check=dict(op='text_contains',selector='#rows',value='A'))
            return kw['validator'](answer)
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t:
            args=('固定の元仕様',dict(model='planner',qa_mapping_model='semantic',qa_oracle_model='auditor'),Path(t),'base-workflow','fixed-sha',qa.qa_unit_schema(1,'workflow'),lambda raw:qa.validate_qa_unit(raw,'workflow',1),inventory)
            with self.assertRaises(TimeoutError):qa.qa_split_unit_generation(*args)
            result=qa.qa_split_unit_generation(*args,hint='時間切れの項目だけ再開')
            self.assertEqual(result['checks'][0],dict(op='text_equals',selector='#count',value='1'))
            path=Path(t)/'base-workflow-split'/'actions.json'
            receipt=qa.json.loads(path.read_text());receipt['value']['result_selector']='#invented'
            path.write_text(qa.json.dumps(receipt))
            qa.qa_split_unit_generation(*args)
        self.assertEqual(calls,['actions','primary','secondary-0','secondary-1','secondary-1','actions'])

    def test_browser_fault_invalidates_only_its_split_checkpoint(self):
        raw=dict(exact_check=dict(op='text_equals',selector='#count',value='1'),checks=[dict(op='text_contains',selector='#rows',value='A'),dict(op='visible',selector='#save')])
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)/'base-workflow-split';directory.mkdir()
            for name in ('actions','primary','secondary-0','secondary-1'):(directory/(name+'.json')).write_text('{}')
            qa.qa_invalidate_split_failure(Path(t),'base-workflow',raw,dict(check=raw['checks'][0]))
            self.assertFalse((directory/'secondary-0.json').exists())
            for name in ('actions','primary','secondary-1'):self.assertTrue((directory/(name+'.json')).exists())

    def test_vague_saved_acceptance_is_returned_to_spec_owner(self):
        source=dict(must_have=['出欠を保存'],acceptance=['出席率集計が完了し、出席率が表示される','CSV出力が完了し、CSVファイルがダウンロードされる'])
        self.assertTrue(contract.department_spec_contract_issue(source,{}))
        self.assertEqual(contract.department_spec_source_requirements(source),source['must_have']+source['acceptance'])
        concrete=dict(acceptance=['出席1人、総数2人を保存すると出席率50%を表示する'])
        self.assertFalse(contract.department_spec_contract_issue(concrete,{}))

    def test_repaired_spec_does_not_recursively_add_its_own_examples(self):
        source=dict(must_have=['保存'],acceptance=['入力: A / 操作: 保存 / 期待結果: 1件'],acceptance_contract_policy='old',acceptance_source_requirements=['保存','CSV出力'],acceptance_original_criteria=['CSV出力'])
        self.assertEqual(contract.department_spec_source_requirements(source),['保存','CSV出力'])

    def test_missing_select_is_bounded_and_cached_without_changing_oracle(self):
        inventory=qa.compact_qa_inventory('<form id="f"><select id="status" required><option value="">選択</option><option value="open">未着手</option></select><button id="save" type="submit">保存</button></form>')
        raw=dict(steps=[dict(op='click',selector='#save')],checks=[dict(op='text_equals',selector='#count',value='1')])
        observation=dict(steps=raw['steps'],operation=raw['steps'][0],invalid_fields=[dict(selector='#status')])
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            calls.append(prompt)
            self.assertEqual(tokens,100)
            self.assertEqual(kw['schema']['properties']['value']['enum'],['open'])
            return kw['validator'](dict(value='open'))
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t:
            cfg=dict(model='x',_qa_input_repair_directory=t)
            fixed=qa.repair_qa_required_selects(raw,observation,inventory,cfg)
            again=qa.repair_qa_required_selects(raw,observation,inventory,cfg)
        self.assertEqual(len(calls),1)
        self.assertEqual(fixed,again)
        self.assertEqual(fixed['steps'][0],dict(op='select',selector='#status',value='open'))
        self.assertEqual(fixed['checks'],raw['checks'])
        self.assertEqual(raw['steps'],[dict(op='click',selector='#save')])

    def test_select_normalization_preserves_intent_and_assertions(self):
        inventory=qa.compact_qa_inventory('<label>状態<select id="status"><option value="open">未着手</option><option value="done">完了</option></select></label>')
        for entered in ('完了','done'):
            raw=dict(steps=[dict(op='fill',selector='#status',value=entered)],checks=[dict(op='text_equals',selector='#count',value='2')])
            fixed=qa.qa_normalize_select_inputs(raw,inventory)
            self.assertEqual(fixed['steps'],[dict(op='select',selector='#status',value='done')])
            self.assertEqual(fixed['checks'],raw['checks'])
            self.assertEqual(raw['steps'][0]['op'],'fill')
        raw=dict(steps=[dict(op='fill',selector='#status',value='存在しない値')])
        self.assertEqual(qa.qa_normalize_select_inputs(raw,inventory),raw)

    def test_ambiguous_option_is_not_guessed(self):
        inventory=qa.compact_qa_inventory('<select id="s"><option value="a">同名</option><option value="b">同名</option></select>')
        raw=dict(steps=[dict(op='fill',selector='#s',value='同名')])
        self.assertEqual(qa.qa_normalize_select_inputs(raw,inventory),raw)

    def test_display_boundary_does_not_take_numbers_from_browser(self):
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2)}
        with self.assertRaises(ValueError):qa.qa_validate_display_boundary(dict(exact_check=dict(selector='#summary',value='1')),formats)
        raw=dict(exact_check=dict(selector='#summary',value='2件 / 超過1件'))
        self.assertEqual(qa.qa_validate_display_boundary(raw,formats),raw)

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







