"""Independent aggregate engine controls; not real-model acceptance."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

module=importlib.util.spec_from_file_location('aggregate_module',Path(__file__).resolve().parents[1]/'agent'/'qa_checkpoint_planner.py')
qa=importlib.util.module_from_spec(module);module.loader.exec_module(qa)
qa.AutoQAPlanError=ValueError


class ReferenceAggregateTests(unittest.TestCase):
    def test_state_uses_submitted_records_not_pending_fields(self):
        steps=[dict(op='fill',selector='#status',value='出席'),dict(op='click',selector='#save'),dict(op='fill',selector='#status',value='欠席'),dict(op='click',selector='#save'),dict(op='fill',selector='#status',value='出席'),dict(op='click',selector='#edit'),dict(op='fill',selector='#status',value='遅刻'),dict(op='click',selector='#save')]
        events=[dict(step_index=1,effect='create',target=None),dict(step_index=3,effect='create',target=None),dict(step_index=5,effect='none',target=None),dict(step_index=7,effect='update',target=1)]
        rows=qa.qa_reference_rows(steps,events)
        self.assertEqual(rows,[{'#status':'遅刻'},{'#status':'欠席'}])
        base=dict(metric='percent',where='in',field='#status',members=['出席','遅刻'],rounding='exact',places=0)
        self.assertEqual(qa.qa_evaluate_projection(rows,base,{}),'50')
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows+[{'#status':'出席'}],base,{})
        self.assertEqual(qa.qa_evaluate_projection(rows+[{'#status':'出席'}],dict(base,rounding='nearest'),{}),'67')

    def test_date_count_uses_independent_clock_and_missing_inputs_fail(self):
        projection=dict(metric='count',where='before_date',field='#deadline',members=[],rounding='exact',places=0)
        rows=[{'#deadline':'2035-12-31'},{'#deadline':'2026-10-28'},{'#deadline':'2026-10-29'}]
        self.assertEqual(qa.qa_evaluate_projection(rows,projection,dict(date='2026-10-29')),'1')
        self.assertEqual(qa.qa_evaluate_projection(rows[:1],projection,dict(date='2026-10-29')),'0')
        for bad in ([{}],[{'#deadline':'2026-02-30'}]):
            with self.assertRaises(ValueError):qa.qa_evaluate_projection(bad,projection,dict(date='2026-10-29'))
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows,projection,{})
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows,dict(projection,metric='unknown'),dict(date='2026-10-29'))

    def test_audited_projection_ignores_unexecuted_acceptance_example(self):
        actions=dict(result_selector='#summary',steps=[dict(op='fill',selector='#deadline',value='2035-12-31'),dict(op='click',selector='#save')])
        events=[dict(step_index=1,effect='create',target=None)]
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2)}
        projections=[dict(metric='count',where='all',field='',members=[],rounding='exact',places=0,basis='全保存記録の件数を表示するという元要件に対応'),dict(metric='count',where='before_date',field='#deadline',members=[],rounding='exact',places=0,basis='対応期限が基準日より前の記録を超過として数える元要件')]
        calls=[]
        def generate(name,prompt,schema,validate,dependency):
            calls.append(name)
            self.assertNotIn('未実行の100件',prompt)
            if name.startswith('primary-projection-'):
                self.assertIn('#summary',prompt)
                self.assertEqual(dependency['output']['selector'],'#summary')
                wanted='all' if name.endswith('0') else 'before_date'
                answer=dict(choice=next(i for i,c in enumerate(dependency['candidates']) if c['where']==wanted))
            else:answer=dict(valid=True,reason='元要件と実入力項目に対応し、固定の表示ラベルのみを扱う')
            return validate(answer)
        spec=dict(requested_outcome='返品の全保存件数と期限超過数を表示',must_have=['対応期限が今日より前なら期限超過として数える'],acceptance=['未実行の100件を期待する入力例'])
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events):
            answer=qa.qa_reference_primary_expectation(actions,formats,spec,dict(model='semantic',qa_oracle_model='independent',_qa_reference_clock=dict(date='2026-10-29')),dict(controls=[dict(tag='input',type='date',selector='#deadline')]),Path(t),'case',generate)
            self.assertEqual(answer['exact_check']['value'],'1件 / 超過0件')
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
            self.assertEqual(proof['values'],['1','0'])
            self.assertEqual(proof['rows'],[{'#deadline':'2035-12-31'}])
            self.assertIn('primary-projection-blind-1',calls)
            def reject(name,prompt,schema,validate,dependency):return validate(dict(valid=False,reason='元要件には対応しない集計条件が提案されています'))
            with self.assertRaises(ValueError):qa.qa_reference_primary_expectation(actions,formats,spec,dict(model='semantic'),dict(controls=[]),Path(t),'bad',reject)

    def test_blind_projection_disagreement_rejects_equal_current_numbers(self):
        # With one overdue row both rules return 1; semantic disagreement must
        # still fail instead of accidentally passing a weak input example.
        rows=[{'#deadline':'2026-10-01'}]
        candidates=qa.qa_projection_candidates([dict(selector='#deadline',type='date')],'{n0}件',0)
        self.assertEqual(qa.qa_evaluate_projection(rows,candidates[0],dict(date='2026-10-30')),'1')
        self.assertEqual(qa.qa_evaluate_projection(rows,candidates[1],dict(date='2026-10-30')),'1')
        with self.assertRaises(ValueError):qa.qa_require_independent_agreement(candidates[0],candidates[1],'全件数')
        self.assertTrue(qa.qa_require_independent_agreement(candidates[0],dict(candidates[0]),'全件数')['valid'])

    def test_blind_event_auditor_has_no_proposed_event_assignments(self):
        steps=[dict(op='click',selector='#save')]
        proposed=[dict(step_index=0,effect='create',target=None)]
        calls=[]
        def independent(actual_steps,source,selector,cfg,folder,key):
            calls.append(cfg)
            self.assertTrue(cfg['_qa_blind_binding'])
            self.assertEqual(cfg['qa_mapping_model'],'reviewer')
            self.assertEqual(actual_steps,steps)
            self.assertNotIn('events',cfg)
            return [dict(step_index=0,effect='none',target=None)]
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',side_effect=independent):
            with self.assertRaises(ValueError):qa.qa_blind_record_event_audit(steps,proposed,'保存は記録の追加','#count',dict(model='writer',qa_oracle_model='reviewer'),Path(t),'case')
        self.assertEqual(len(calls),1)

    def test_indexed_repair_changes_only_the_second_identical_submit(self):
        inventory=qa.compact_qa_inventory('<form id="form"><input id="name" required><select id="status" required><option value="">選択</option><option value="open">未着手</option></select><button id="save" type="submit">保存</button></form>')
        steps=[dict(op='fill',selector='#name',value='A'),dict(op='select',selector='#status',value='open'),dict(op='click',selector='#save'),dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')]
        raw=dict(steps=steps,exact_check=dict(op='text_equals',selector='#count',value='2'))
        issue=qa.qa_repeated_form_issue(raw,inventory)
        self.assertEqual(issue['operation_index'],4)
        self.assertEqual(qa.qa_submission_index(steps,issue),4)
        self.assertIsNone(qa.qa_submission_index(steps,{k:v for k,v in issue.items() if k!='operation_index'}))
        self.assertIsNone(qa.qa_submission_index(steps,dict(issue,operation_index=3)))
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            calls.append(prompt)
            self.assertEqual(kw['schema']['properties']['value']['enum'],['open'])
            self.assertEqual(tokens,100)
            return kw['validator'](dict(value='open'))
        with patch.object(qa,'ai_json',side_effect=model,create=True):
            fixed=qa.repair_qa_repeated_form_inputs(raw,inventory,dict(model='planner',qa_mapping_model='semantic'))
        self.assertEqual(len(calls),1)
        self.assertEqual(fixed['steps'][:4],steps[:4])
        self.assertEqual(fixed['steps'][4],dict(op='select',selector='#status',value='open'))
        self.assertEqual(fixed['steps'][5],steps[4])
        self.assertEqual(fixed['exact_check'],raw['exact_check'])
        self.assertEqual(len(raw['steps']),5)

    def test_first_submit_repair_also_handles_a_repeated_button(self):
        inventory=qa.compact_qa_inventory('<form id="f"><select id="state" required><option value="">選択</option><option value="ok">有効</option></select><button id="save" type="submit">保存</button></form>')
        raw=dict(steps=[dict(op='click',selector='#save'),dict(op='click',selector='#save')],checks=[dict(op='count',selector='#rows',value=2)])
        def model(prompt,cfg,tokens,**kw):return kw['validator'](dict(value='ok'))
        with patch.object(qa,'ai_json',side_effect=model,create=True):
            fixed=qa.repair_qa_missing_initial_inputs(raw,inventory,dict(model='semantic'),{})
        self.assertEqual(fixed['steps'],[dict(op='select',selector='#state',value='ok')]+raw['steps'])
        self.assertEqual(fixed['checks'],raw['checks'])

    def test_catalog_binds_native_conditions_and_marks_target_position(self):
        controls=[dict(selector='#date',type='date',label='対応期限'),dict(selector='#status',options=[dict(value=''),dict(value='出席'),dict(value='遅刻'),dict(value='欠席')])]
        count=qa.qa_projection_candidates(controls,'{n0}件 / 超過{n1}件',0)
        self.assertEqual(count[0]['where'],'all')
        self.assertTrue(any(c['where']=='before_date' and c['field']=='#date' for c in count))
        ratios=qa.qa_projection_candidates(controls,'{n0}%（出席扱い{n1}/{n2}）',0)
        self.assertTrue(all(c['metric']=='percent' for c in ratios))
        self.assertTrue(any(c['members']==['出席','遅刻'] for c in ratios))
        self.assertFalse(any('' in c['members'] for c in ratios))

    def test_click_choice_cannot_invent_an_existing_record_target(self):
        steps=[dict(op='click',selector='#save'),dict(op='click',selector='#export'),dict(op='click',selector='#delete')]
        answers=[0,1,3];calls=[]
        def model(prompt,cfg,tokens,**kw):
            self.assertEqual(set(kw['schema']['properties']),{'choice'})
            self.assertEqual(kw['schema']['properties']['choice']['enum'],[0,1] if not calls else [0,1,2,3])
            calls.append(prompt)
            return kw['validator'](dict(choice=answers[len(calls)-1]))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True):
            events=qa.qa_bind_record_clicks(steps,'保存は追加、出力は状態不変、削除は既存記録を消す','#count',dict(model='semantic'),Path(t),'case')
        self.assertEqual(events[-1],dict(step_index=2,effect='delete',target=0))
        self.assertEqual(qa.qa_evaluate_record_events(steps,events)['count'],0)

    def test_required_complete_option_filter_is_not_a_duplicate_candidate(self):
        node=dict(selector='#status',label='状態',required=True,options=[dict(value=''),dict(value='open'),dict(value='done')])
        candidates=qa.qa_projection_candidates([node],'{n0}件',0)
        self.assertEqual(sum(c['where']=='all' for c in candidates),1)
        self.assertFalse(any(set(c['members'])=={'open','done'} for c in candidates))
        optional={k:v for k,v in node.items() if k!='required'}
        optional_candidates=qa.qa_projection_candidates([optional],'{n0}件',0)
        full=next(c for c in optional_candidates if set(c['members'])=={'open','done'})
        self.assertEqual(qa.qa_evaluate_projection([{'#status':''}],full,{}),'0')
        self.assertEqual(qa.qa_evaluate_projection([{'#status':''}],optional_candidates[0],{}),'1')
        explicit_optional=qa.qa_projection_candidates([dict(node,required=False)],'{n0}件',0)
        self.assertTrue(any(set(c['members'])=={'open','done'} for c in explicit_optional))
        disabled=qa.qa_projection_candidates([dict(node,disabled=True)],'{n0}件',0)
        self.assertTrue(any(set(c['members'])=={'open','done'} for c in disabled))

    def test_record_binding_facts_distinguish_new_input_and_export(self):
        steps=[dict(op='fill',selector='#student',value='A'),dict(op='click',selector='#save'),dict(op='fill',selector='#student',value='B'),dict(op='click',selector='#save'),dict(op='click',selector='#export')]
        first=[dict(step_index=1,effect='create',target=None)]
        controls=[dict(selector='#student',label='受講者名'),dict(selector='#save',tag='button',type='submit',form='#f',text='出欠を保存'),dict(selector='#export',tag='button',text='CSV出力')]
        second=qa.qa_record_binding_context(steps,first,3,controls)
        self.assertEqual(second['active_records'],[dict(origin=1,fields={'#student':'A'})])
        self.assertEqual(second['entered_since_commit'],{'#student':'B'})
        self.assertEqual(second['current_control']['text'],'出欠を保存')
        self.assertEqual(second['field_labels'],{'#student':'受講者名'})
        exported=qa.qa_record_binding_context(steps,first+[dict(step_index=3,effect='create',target=None)],4,controls)
        self.assertEqual(len(exported['active_records']),2)
        self.assertEqual(exported['entered_since_commit'],{})
        self.assertEqual(exported['current_control']['text'],'CSV出力')
        self.assertNotIn('effect',exported['current_control'])

    def test_output_labels_use_local_quantity_names_not_section_or_numbers(self):
        html='<section><h2>返品案件一覧</h2><div><span>登録数</span><strong id="count">999</strong></div><div id="summary"><span>未処理 / 期限超過</span><strong id="summaryValue">2件 / 超過1件</strong></div><span id="external">対象日の作業数</span><output id="day" aria-labelledby="external">123</output></section>'
        labels=qa.qa_output_labels_from_html(html)
        self.assertEqual(labels['#count'],'登録数')
        self.assertEqual(labels['#summaryValue'],'未処理 / 期限超過')
        self.assertEqual(labels['#day'],'対象日の作業数')
        self.assertNotIn('999',str(labels))
        inventory=qa.compact_qa_inventory(html)
        child=next(n for n in inventory['outputs'] if n['selector']=='#summaryValue')
        self.assertEqual(child['label'],'未処理 / 期限超過')
        self.assertIn('#summary',child['ancestor_selectors'])

    def test_explicit_total_label_does_not_offer_state_filtered_totals(self):
        controls=[dict(selector='#status',options=[dict(value='open'),dict(value='done')])]
        total=qa.qa_projection_candidates(controls,'{n0}',0,dict(label='登録数'))
        self.assertEqual(len(total),1)
        self.assertEqual(total[0]['where'],'all')
        pending=qa.qa_projection_candidates(controls,'{n0}',0,dict(label='未処理'))
        self.assertTrue(any(c['where']=='in' for c in pending))

    def test_closed_overdue_record_distinguishes_total_open_and_overdue(self):
        controls=[dict(selector='#deadline',type='date',label='対応期限'),dict(selector='#status',label='対応状態',required=True,options=[dict(value='pending'),dict(value='closed')])]
        candidates=qa.qa_projection_candidates(controls,'{n0}件 / 超過{n1}件',1)
        combined=next(c for c in candidates if c['where']=='before_date' and c.get('also',{}).get('members')==['pending'])
        rows=[{'#deadline':'2035-12-31','#status':'pending'},{'#deadline':'2000-01-01','#status':'pending'},{'#deadline':'2000-01-01','#status':'closed'}]
        clock=dict(date='2026-10-30')
        self.assertEqual(qa.qa_evaluate_projection(rows,combined,clock),'1')
        naive=next(c for c in candidates if c['where']=='before_date' and not c.get('also'))
        self.assertEqual(qa.qa_evaluate_projection(rows,naive,clock),'2')
        open_count=next(c for c in candidates if c['where']=='in' and c['members']==['pending'])
        self.assertEqual(qa.qa_evaluate_projection(rows,open_count,clock),'2')
        self.assertEqual(qa.qa_evaluate_projection(rows,candidates[0],clock),'3')

    def test_selected_date_uses_declared_input_and_missing_reference_fails(self):
        controls=[dict(selector='#recordDate',type='date',label='作業日'),dict(selector='#selectedDate',type='date',label='対象日')]
        candidates=qa.qa_projection_candidates(controls,'{n0}件',0,input_values={'#selectedDate':'2026-10-29'},row_fields={'#recordDate'})
        rule=next(c for c in candidates if c['where']=='on_input_date')
        rows=[{'#recordDate':'2026-10-29'},{'#recordDate':'2026-10-30'}]
        self.assertEqual(qa.qa_evaluate_projection(rows,rule,dict(input_values={'#selectedDate':'2026-10-29'})),'1')
        self.assertEqual(qa.qa_evaluate_projection(rows,rule,dict(input_values={'#selectedDate':'2026-10-30'})),'1')
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows,rule,{})
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows,rule,dict(input_values={'#selectedDate':'invalid'}))

    def test_fraction_numerator_and_denominator_derive_from_agreed_rule(self):
        steps=[dict(op='select',selector='#status',value='present'),dict(op='click',selector='#save'),dict(op='select',selector='#status',value='absent'),dict(op='click',selector='#save')]
        events=[dict(step_index=1,effect='create',target=None),dict(step_index=3,effect='create',target=None)]
        inventory=dict(controls=[dict(tag='select',selector='#status',required=True,options=[dict(value='present'),dict(value='absent')])])
        formats={'#summary':dict(template='{n0}%（出席扱い{n1}/{n2}、欠席{n3}）',slots=4,label='出席率')}
        calls=[]
        def generate(name,prompt,schema,validate,dependency):
            calls.append(name)
            self.assertTrue(name.startswith('primary-projection-'))
            wanted='present' if name.endswith('0') else 'absent'
            self.assertIn(name.rsplit('-',1)[-1],('0','3'))
            choice=next(i for i,c in enumerate(dependency['candidates']) if c['where']=='in' and c['members']==[wanted])
            return validate(dict(choice=choice))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events):
            result=qa.qa_reference_primary_expectation(dict(steps=steps,result_selector='#summary'),formats,dict(must_have=['出席扱いの数を全体で割った割合と欠席数']),dict(model='mapper',qa_oracle_model='reviewer'),inventory,Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'50%（出席扱い1/2、欠席1）')
        self.assertEqual(len(calls),4)
        self.assertEqual(proof['projection_audits'][1]['derived_from'],0)
        self.assertEqual(proof['projection_audits'][2]['derived_from'],0)

    def test_quantity_format_grammar_does_not_adopt_business_verdicts(self):
        base=dict(metric='percent',where='in',field='#status',members=['present'],rounding='exact',places=0,basis='出席')
        projections=[base,dict(base,metric='count'),dict(base,metric='count',where='all',field='',members=[]),dict(base,metric='count',members=['absent'])]
        self.assertTrue(qa.qa_fixed_quantity_format('{n0}%（出席扱い{n1}/{n2}、欠席{n3}）','出席率',projections))
        self.assertFalse(qa.qa_fixed_quantity_format('合格{n0}%（正解{n1}/{n2}、不正解{n3}）','合格',projections))
        self.assertFalse(qa.qa_fixed_quantity_format('{n0}件 / 稼働枠内','今日の状況',[dict(base,metric='count')]))

    def test_primary_container_resolves_to_unique_numeric_child(self):
        inventory=qa.compact_qa_inventory('<input id="name"><button id="save">保存</button><div id="summary"><span>出席率</span><strong id="summaryValue">0</strong></div><tbody id="rows"></tbody>')
        formats={'#summary':dict(template='出席率{n0}%',slots=1,label='出席率'),'#summaryValue':dict(template='{n0}%',slots=1,label='出席率')}
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            name=Path(cfg['_json_transport_evidence']).stem.removesuffix('-transport');calls.append(name)
            if name=='actions':
                self.assertEqual(kw['schema']['properties']['result_selector']['enum'],['#summaryValue'])
                answer=dict(steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#save')],acceptance=[0],rationale='入力した記録を保存して独立した結果を検査する',result_selector='#summary')
            elif name=='secondary-0':answer=dict(check=dict(op='value_equals',selector='#name',value='A'))
            else:answer=dict(check=dict(op='text_contains',selector='#rows',value='A'))
            return kw['validator'](answer)
        def primary(actions,*args):
            self.assertEqual(actions['result_selector'],'#summaryValue')
            return dict(exact_check=dict(op='text_equals',selector='#summaryValue',value='100%'))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True),patch.object(qa,'qa_reference_primary_expectation',side_effect=primary):
            result=qa.qa_split_unit_generation('元要件',dict(model='x',qa_reference_aggregates=True,_qa_display_contracts=formats),Path(t),'base-workflow','input',qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)
        self.assertEqual(result['result_selector'],'#summaryValue')
        self.assertEqual(result['steps'][0]['value'],'A')
        self.assertEqual(calls,['actions','secondary-0','secondary-1'])

    def component_fixture(self):
        inventory=qa.compact_qa_inventory('<form id="recordForm"><input id="title" required><button id="saveRecord" type="submit">保存</button><button id="clearForm" type="button">消去</button></form><strong id="recordCount">0</strong><tbody id="recordRows"></tbody><button id="downloadCsv" type="button">CSV出力</button><button id="saveCapacity" type="button">稼働枠を保存</button>')
        return inventory,dict(model='mapper',qa_component_contract='native-record-create-v1',qa_component_passive_buttons=['#saveCapacity'],_qa_binding_controls=inventory['controls'],_qa_binding_outputs=inventory['outputs'])

    def test_declared_component_commands_do_not_ask_ai_to_guess_clicks(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#saveRecord'),dict(op='click',selector='#downloadCsv'),dict(op='fill',selector='#title',value='B'),dict(op='click',selector='#saveRecord'),dict(op='click',selector='#saveCapacity')]
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=AssertionError('AI must not infer a declared protocol'),create=True):
            events=qa.qa_bind_record_clicks(steps,'記録の追加とCSV出力','#recordCount',cfg,Path(t),'case')
            audit=qa.qa_blind_record_event_audit(steps,events,'同じ元要件','#recordCount',cfg,Path(t),'case')
        self.assertEqual([e['effect'] for e in events],['create','none','create','none'])
        self.assertEqual(qa.qa_evaluate_record_events(steps,events)['count'],2)
        self.assertIn('not AI inference',audit['method'])

    def test_component_driver_declines_unknown_lifecycle_and_unselected_contract(self):
        inventory,cfg=self.component_fixture()
        self.assertIsNone(qa.qa_component_events([dict(op='click',selector='#recordRows button')],cfg))
        self.assertIsNone(qa.qa_component_events([dict(op='restore_file',selector='#file')],cfg))
        self.assertIsNone(qa.qa_component_events([dict(op='click',selector='#saveRecord')],dict(cfg,qa_component_contract='unregistered')))
        self.assertIsNone(qa.qa_component_events([dict(op='click',selector='#saveRecord')],dict(cfg,_qa_binding_outputs=[])))
        self.assertIsNone(qa.qa_component_events([dict(op='click',selector='#saveCapacity')],dict(cfg,qa_component_passive_buttons=[])))

    def test_component_clear_drops_draft_fields_without_deleting_records(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#notes',value='discard'),dict(op='click',selector='#clearForm'),dict(op='fill',selector='#title',value='B'),dict(op='click',selector='#saveRecord')]
        events=qa.qa_component_events(steps,cfg)
        self.assertTrue(events[0]['reset_inputs'])
        self.assertEqual(qa.qa_reference_rows(steps,events),[{'#title':'B'}])
        self.assertEqual(qa.qa_evaluate_record_events(steps,events)['count'],1)

    def test_quantity_scope_separates_adjacent_metrics(self):
        contract=dict(template='{n0}件 / 超過{n1}件',slots=2,label='未処理 / 期限超過')
        self.assertEqual(qa.qa_quantity_scope(contract,0),'未処理')
        self.assertEqual(qa.qa_quantity_scope(contract,1),'期限超過')
        fraction=dict(template='{n0}%（出席扱い{n1}/{n2}、欠席{n3}）',slots=4,label='出席率')
        self.assertEqual(qa.qa_quantity_scope(fraction,3),'欠席')

    def test_counterexample_resolution_is_order_invariant_and_source_grounded(self):
        left=dict(metric='count',where='in',field='#status',members=['pending'],rounding='exact',places=0,basis='未処理の件数')
        right=dict(metric='count',where='before_date',field='#date',members=[],rounding='exact',places=0,basis='期限超過の件数')
        rows=[{'#status':'pending','#date':'2035-12-31'}]
        controls=[dict(selector='#status',options=[dict(value='pending'),dict(value='closed')]),dict(selector='#date',type='date')]
        calls=[]
        def generate(name,prompt,schema,validate,dependency):
            calls.append(name)
            self.assertTrue(dependency['witnesses'])
            self.assertIn('未処理',dependency['output']['target_label'])
            self.assertNotIn('actual',dependency)
            return validate(dict(choice=1 if name.endswith('reverse') else 0,evidence_id=0))
        selected,audit=qa.qa_resolve_projection_binding(left,right,dict(outcome='未処理はpendingの記録件数'),dict(selector='#summary',target_label='未処理'),rows,controls,dict(date='2026-10-30'),generate,'0')
        self.assertEqual(selected,left)
        self.assertTrue(audit['valid'])
        self.assertEqual(len(calls),2)
        self.assertEqual(audit['witnesses'][0]['first_result'],'1')
        self.assertEqual(audit['witnesses'][0]['second_result'],'0')
        def biased(name,prompt,schema,validate,dependency):return validate(dict(choice=0,evidence_id=0))
        with self.assertRaises(ValueError):qa.qa_resolve_projection_binding(left,right,dict(outcome='未処理を表示'),dict(target_label='未処理'),rows,controls,dict(date='2026-10-30'),biased,'0')
        def undecided(name,prompt,schema,validate,dependency):return validate(dict(choice=-1,evidence_id=0))
        with self.assertRaises(ValueError):qa.qa_resolve_projection_binding(left,right,dict(outcome='未処理を表示'),dict(target_label='未処理'),rows,controls,dict(date='2026-10-30'),undecided,'0')

    def test_disagreement_without_a_valid_distinguishing_input_stays_failed(self):
        a=dict(metric='count',where='all',field='',members=[],rounding='exact',places=0,basis='全件')
        b=dict(a,where='in',field='#status',members=['pending'])
        def no_call(*args):raise AssertionError('No valid witness: do not guess')
        with self.assertRaises(ValueError):qa.qa_resolve_projection_binding(a,b,dict(outcome='件数'),dict(target_label='件数'),[],[],{},no_call,'0')

    def test_duplicate_input_normalization_preserves_differences_and_submit_boundaries(self):
        fill=dict(op='fill',selector='#field',value='A');save=dict(op='click',selector='#saveRecord')
        raw=dict(steps=[fill,dict(fill),save,dict(fill),dict(fill,value='B')],exact_check=dict(value='unchanged'))
        normalized=qa.qa_normalize_component_inputs(raw)
        self.assertEqual(normalized['steps'],[fill,save,fill,dict(fill,value='B')])
        self.assertEqual(normalized['exact_check'],raw['exact_check'])
        self.assertEqual(len(raw['steps']),5)

    def test_unknown_edit_uses_semantic_mapping_after_preserved_component_prefix(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#saveRecord'),dict(op='click',selector='#recordRows button',nth=0),dict(op='fill',selector='#title',value='B'),dict(op='click',selector='#saveRecord')]
        calls=[]
        def model(prompt,cfg,tokens,**kw):
            calls.append(prompt)
            return kw['validator'](dict(choice=1 if len(calls)==1 else 2))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True):
            events=qa.qa_bind_record_clicks(steps,'既存記録を選択して編集保存する','#recordCount',cfg,Path(t),'case')
        self.assertEqual(len(calls),2)
        self.assertEqual([e['effect'] for e in events],['create','none','update'])
        self.assertEqual(events[-1]['target'],1)
        self.assertEqual(qa.qa_evaluate_record_events(steps,events)['count'],1)

    def test_primary_disagreement_is_repaired_only_after_order_reversed_agreement(self):
        steps=[dict(op='select',selector='#status',value='pending'),dict(op='fill',selector='#date',value='2035-12-31'),dict(op='click',selector='#save')]
        events=[dict(step_index=2,effect='create',target=None)]
        controls=[dict(tag='select',selector='#status',options=[dict(value='pending'),dict(value='closed')]),dict(tag='input',selector='#date',type='date')]
        formats={'#summary':dict(template='{n0}件 / 超過{n1}件',slots=2,label='未処理 / 期限超過')}
        calls=[]
        def generate(name,prompt,schema,validate,dependency):
            calls.append(name)
            if '-resolution-' in name:return validate(dict(choice=1 if name.endswith('reverse') else 0,evidence_id=0))
            index=int(name.rsplit('-',1)[1]);candidates=dependency['candidates']
            if index==0 and '-blind-' not in name:wanted=lambda c:c['where']=='in' and c['members']==['pending']
            elif index==0:wanted=lambda c:c['where']=='before_date' and not c.get('also')
            else:wanted=lambda c:c['where']=='before_date' and c.get('also',{}).get('members')==['pending']
            return validate(dict(choice=next(i for i,c in enumerate(candidates) if wanted(c))))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events):
            result=qa.qa_reference_primary_expectation(dict(steps=steps,result_selector='#summary'),formats,dict(outcome='未完了はpending。期限超過は未完了かつ期限が今日より前。',requested_outcome='未完了はpending。期限超過は未完了かつ期限が今日より前。'),dict(model='x',_qa_reference_clock=dict(date='2026-10-30')),dict(controls=controls),Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'1件 / 超過0件')
        self.assertEqual(proof['projections'][0]['where'],'in')
        self.assertEqual(proof['projection_audits'][0]['original_independent']['where'],'before_date')
        self.assertEqual(len([name for name in calls if '-resolution-' in name]),2)

    def test_declared_registration_total_is_computed_before_model_mapping(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#saveRecord'),dict(op='click',selector='#downloadCsv'),dict(op='fill',selector='#title',value='B'),dict(op='click',selector='#saveRecord')]
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=AssertionError('Counter protocol is declared'),create=True):
            result=qa.qa_reference_count_oracle(dict(steps=steps,exact_check=dict(selector='#recordCount',value='incorrect')),{},dict(must_have=['登録と出力']),cfg,Path(t),'case',[])
        self.assertEqual(result['exact_check']['value'],'2')
        self.assertEqual([v['count'] for v in result['reference_count']['trace']],[1,1,2])

    def test_declared_total_component_keeps_business_metrics_separate(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#title',value='A'),dict(op='click',selector='#saveRecord')]
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        def no_model(*args,**kwargs):raise AssertionError('Declared total does not need a model opinion')
        with tempfile.TemporaryDirectory() as t:
            result=qa.qa_reference_primary_expectation(dict(steps=steps,result_selector='#recordCount'),{'#recordCount':dict(template='{n0}',slots=1,label='登録数')},dict(must_have=['保存した記録の総数を表示']),cfg,inventory,Path(t),'case',no_model)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'1')
        self.assertIn('not AI inference',proof['projection_audits'][0]['method'])

    def test_second_submit_requires_required_select_again(self):
        inventory=qa.compact_qa_inventory('<form id="form"><input id="name" required><select id="status" required><option value="">選択</option><option value="open">未着手</option></select><button id="save" type="submit">保存</button></form>')
        steps=[dict(op='fill',selector='#name',value='A'),dict(op='select',selector='#status',value='open'),dict(op='click',selector='#save'),dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')]
        with self.assertRaises(ValueError):qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)
        steps.insert(-1,dict(op='select',selector='#status',value='open'))
        self.assertEqual(qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)['steps'],steps)
