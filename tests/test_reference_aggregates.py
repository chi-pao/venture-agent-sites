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
            if '-membership-' in name:
                wanted='absent' if dependency['output']['target_label']=='欠席' else 'present'
                return validate(dict(membership=[int(v==wanted) for v in dependency['ordered_statuses']],evidence_id=0))
            wanted='present' if name.endswith('0') else 'absent'
            self.assertIn(name.rsplit('-',1)[-1],('0','3'))
            choice=next(i for i,c in enumerate(dependency['candidates']) if c['where']=='in' and c['members']==[wanted])
            return validate(dict(choice=choice))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events):
            result=qa.qa_reference_primary_expectation(dict(steps=steps,result_selector='#summary'),formats,dict(must_have=['出席扱いの数を全体で割った割合と欠席数']),dict(model='mapper',qa_oracle_model='reviewer'),inventory,Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'50%（出席扱い1/2、欠席1）')
        self.assertEqual(len(calls),8)
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
            if '-membership-' in name:return validate(dict(membership=[int(v=='pending') for v in dependency['ordered_statuses']],evidence_id=0))
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

    def test_saved_secondary_checks_target_collection_not_cleared_draft(self):
        inventory,cfg=self.component_fixture()
        steps=[dict(op='fill',selector='#title',value='保存済みA'),dict(op='click',selector='#saveRecord'),dict(op='fill',selector='#title',value='未保存B'),dict(op='click',selector='#clearForm')]
        checks=qa.qa_component_saved_checks(dict(steps=steps),dict(selector='#summaryValue'),inventory,cfg)
        self.assertEqual(checks,[dict(op='text_equals',selector='#recordCount',value='1'),dict(op='text_contains',selector='#recordRows',value='保存済みA')])
        self.assertFalse(any(c['selector']=='#title' or c['value']=='未保存B' for c in checks))

    def test_saved_secondary_checks_retain_prior_variant_records(self):
        inventory,cfg=self.component_fixture()
        prior=[dict(op='fill',selector='#title',value='先行A'),dict(op='click',selector='#saveRecord')]
        current=[dict(op='fill',selector='#title',value='追加B'),dict(op='click',selector='#saveRecord')]
        checks=qa.qa_component_saved_checks(dict(steps=current),dict(selector='#recordCount'),inventory,dict(cfg,_qa_prior_scenarios=[dict(kind='workflow',steps=prior)]))
        self.assertEqual(checks,[dict(op='text_contains',selector='#recordRows',value='追加B'),dict(op='text_contains',selector='#recordRows',value='先行A')])
        self.assertTrue(all(c['op']!='text_equals' for c in checks))

    def test_saved_secondary_declines_unknown_actor_and_insufficient_values(self):
        inventory,cfg=self.component_fixture()
        actions=dict(steps=[dict(op='fill',selector='#title',value='保存A'),dict(op='click',selector='#saveRecord')])
        self.assertIsNone(qa.qa_component_saved_checks(actions,dict(selector='#recordCount'),inventory,cfg))
        self.assertIsNone(qa.qa_component_saved_checks(actions,dict(selector='#summaryValue'),inventory,dict(cfg,qa_component_contract='unknown')))
        self.assertIsNone(qa.qa_component_saved_checks(dict(steps=actions['steps']+[dict(op='click',selector='#edit')]),dict(selector='#summaryValue'),inventory,cfg))

    def test_today_projection_is_distinct_from_all_and_overdue(self):
        nodes=[dict(selector='#date',type='date',label='日付')]
        choices=qa.qa_projection_candidates(nodes,'{n0}件',0,output=dict(label='今日の件数'),row_fields={'#date'})
        projection=next(p for p in choices if p['where']=='on_reference_date')
        rows=[{'#date':'2026-10-28'},{'#date':'2026-10-29'},{'#date':'2026-10-30'}]
        self.assertEqual(qa.qa_evaluate_projection(rows,projection,dict(date='2026-10-29')),'1')
        self.assertEqual(qa.qa_evaluate_projection(rows[:1],projection,dict(date='2026-10-29')),'0')
        with self.assertRaises(ValueError):qa.qa_evaluate_projection(rows,projection,{})

    def test_same_variant_is_rejected_before_primary_generation_and_cache_reuse(self):
        inventory,cfg=self.component_fixture()
        actions=dict(steps=[dict(op='fill',selector='#title',value='同一A'),dict(op='click',selector='#saveRecord')],acceptance=[0],rationale='入力後保存する',result_selector='#recordCount')
        cfg=dict(cfg,qa_component_contract='unknown',_qa_prior_scenarios=[dict(actions,kind='workflow')],_qa_display_contracts={'#recordCount':dict(slots=1,template='{n0}',label='登録数')})
        calls=[]
        def model(prompt,config,tokens,**kw):
            calls.append(Path(config['_json_transport_evidence']).name)
            return kw['validator'](actions)
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'同一操作'):
                    qa.qa_split_unit_generation('元要件',cfg,Path(t),'base-variant','input',qa.qa_unit_schema(1,'variant'),lambda raw:raw,inventory)
            self.assertFalse((Path(t)/'base-variant-split'/'actions.json').exists())
        self.assertEqual(calls,['actions-transport.json','actions-transport.json'])

    def test_compact_choices_preserve_predicates_and_reduce_real_five_state_prompt(self):
        controls=[dict(selector='#date',type='date',label='対応期限'),dict(selector='#state',label='対応状況',options=[dict(value=x) for x in ['受付','返送待ち','確認中','返金済み','対象外']],required=True)]
        choices=qa.qa_projection_candidates(controls,'{n0}件 / 超過{n1}件',1,output=dict(label='未完了 / 期限超過'))
        short=qa.qa_compact_projection_choices(choices,controls)
        long=[dict(choice=i,meaning=p['basis']) for i,p in enumerate(choices)]
        self.assertLess(len(json.dumps(short,ensure_ascii=False)),len(json.dumps(long,ensure_ascii=False))*.8)
        self.assertFalse(any(p['where']=='on_reference_date' for p in choices))
        for i,p in enumerate(choices):
            self.assertEqual(short[i][0],i)
            if p['where']=='in':self.assertTrue(all(m in short[i][1] for m in p['members']))
            if p['where']=='before_date':self.assertIn('<基準日',short[i][1])
            if p.get('also'):self.assertIn(' AND ',short[i][1])

    def test_split_component_compiles_saved_checks_without_replacing_primary(self):
        inventory,cfg=self.component_fixture()
        cfg=dict(cfg,qa_reference_aggregates=True,_qa_display_contracts={'#recordCount':dict(slots=1,template='{n0}',label='登録数'),'#summaryValue':dict(slots=1,template='{n0}件',label='未完了')})
        inventory['outputs'].append(dict(selector='#summaryValue',tag='strong'))
        calls=[]
        def model(prompt,config,tokens,**kw):
            calls.append(Path(config['_json_transport_evidence']).name)
            return kw['validator'](dict(steps=[dict(op='fill',selector='#title',value='記録A'),dict(op='click',selector='#saveRecord')],acceptance=[0],result_selector='#summaryValue',rationale='保存して集計と記録を確認する'))
        primary=dict(exact_check=dict(op='text_equals',selector='#summaryValue',value='1件'))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True),patch.object(qa,'qa_reference_primary_expectation',return_value=primary) as independent:
            result=qa.qa_split_unit_generation('元要件',cfg,Path(t),'base-workflow','input',qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)
            independent.assert_called_once()
            self.assertTrue((Path(t)/'base-workflow-split'/'secondary-component-contract.json').exists())
        self.assertEqual(result['exact_check'],primary['exact_check'])
        self.assertEqual(result['checks'][0],dict(op='text_equals',selector='#recordCount',value='1'))
        self.assertEqual(calls,['actions-transport.json'])

    def test_initial_survey_masks_numbers_and_resumes_before_any_failed_case(self):
        import sys
        import types
        from contextlib import nullcontext
        clock=dict(date=qa.qa_current_reference_clock(None)['date'],source='browser local clock')
        calls=[]
        tab=types.SimpleNamespace(goto=lambda *a,**k:calls.append('load'),evaluate=lambda script:{'#start':'09:00','#end':'17:00','#break':'60'} if 'Object.fromEntries' in script else clock)
        context=types.SimpleNamespace(route=lambda *a:None,new_page=lambda:tab,close=lambda:None)
        browser=types.SimpleNamespace(new_context=lambda **k:context,close=lambda:None)
        sync=types.SimpleNamespace(sync_playwright=lambda:nullcontext(types.SimpleNamespace(chromium=types.SimpleNamespace(launch=lambda **k:browser))))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        def capture(page):return qa.qa_display_contracts_from_nodes([dict(selector='#summaryValue',text='999件 / 超過888件',label='未完了 / 期限超過')])
        with tempfile.TemporaryDirectory() as t,patch.dict(sys.modules,{'playwright.sync_api':sync}),patch.object(qa,'ensure_product_preview',return_value=dict(local_url='http://local/app'),create=True),patch.object(qa,'capture_qa_display_contracts',side_effect=capture,create=True):
            first=qa.qa_initial_display_context('商品','same source',Path(t))
            second=qa.qa_initial_display_context('商品','same source',Path(t))
            self.assertEqual(first,second)
            self.assertEqual(first['input_defaults']['#break'],'60')
            self.assertEqual(json.dumps(first,ensure_ascii=False),json.dumps(second,ensure_ascii=False))
            self.assertEqual(first['display_contracts']['#summaryValue']['template'],'{n0}件 / 超過{n1}件')
            self.assertNotIn('999',json.dumps(first));self.assertNotIn('888',json.dumps(first))
            self.assertEqual(calls,['load'])
            qa.qa_initial_display_context('商品','changed source',Path(t))
            self.assertEqual(calls,['load','load'])

    def test_whole_unit_identity_cannot_reuse_legacy_or_changed_semantic_roles(self):
        cfg=dict(qa_split_units=True,qa_reference_aggregates=True,qa_oracle_model='independent',qa_component_contract='native-record-create-v1')
        identity=qa.qa_compilation_identity(cfg)
        self.assertNotEqual(identity,qa.qa_compilation_identity(dict(cfg,qa_split_units=False)))
        self.assertNotEqual(identity,qa.qa_compilation_identity(dict(cfg,qa_oracle_model='other')))
        self.assertNotEqual(identity,qa.qa_compilation_identity(dict(cfg,qa_component_contract='unknown')))
        self.assertIn('survey-before-plan',identity['policy'])

    def test_aggregate_planner_does_not_fallback_to_free_text_without_format(self):
        inventory=qa.compact_qa_inventory('<input id="title"><button id="save">保存</button><strong id="result">保存しました</strong>')
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=AssertionError('must survey first'),create=True):
            with self.assertRaisesRegex(ValueError,'初期画面'):
                qa.qa_split_unit_generation('元要件',dict(model='x',qa_reference_aggregates=True),Path(t),'base-workflow','input',qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)

    def test_disputed_status_sets_can_recover_a_third_source_grounded_set(self):
        controls=[dict(selector='#state',label='対応状況',options=[dict(value=s) for s in ['受付','返送待ち','確認中','返金済み','対象外']])]
        left=dict(metric='count',where='in',field='#state',members=['返送待ち'],rounding='exact',places=0,basis='first wrong subset')
        right=dict(left,members=['返送待ち','確認中'],basis='second wrong subset')
        calls=[]
        def judge(name,prompt,schema,validate,dependency):
            calls.append(name)
            self.assertNotIn('first wrong subset',prompt);self.assertNotIn('second wrong subset',prompt)
            included=[int(s not in ('返金済み','対象外')) for s in dependency['ordered_statuses']]
            return validate(dict(membership=included,evidence_id=0))
        projection,audit=qa.qa_resolve_projection_binding(left,right,dict(outcome='未完了は返金済み・対象外を除く件数'),dict(selector='#summaryValue',target_label='未完了'),[{'#state':'確認中'}],controls,{},judge,'0')
        self.assertEqual(projection['members'],['受付','返送待ち','確認中'])
        self.assertNotEqual(projection['members'],left['members']);self.assertNotEqual(projection['members'],right['members'])
        self.assertTrue(audit['valid']);self.assertEqual(len(calls),2)
        self.assertEqual(qa.qa_evaluate_projection([{'#state':o['value']} for o in controls[0]['options']],projection,{}),'3')

    def test_overdue_status_repair_preserves_independent_date_condition(self):
        controls=[dict(selector='#state',options=[dict(value=s) for s in ['受付','返金済み']])]
        base=dict(metric='count',where='before_date',field='#due',members=[],rounding='exact',places=0,basis='overdue')
        left=dict(base,also=dict(field='#state',members=['受付']))
        def judge(name,prompt,schema,validate,dependency):
            self.assertEqual(dependency['fixed_condition'],dict(where='before_date',field='#due'))
            return validate(dict(membership=[int(s=='受付') for s in dependency['ordered_statuses']],evidence_id=0))
        projection,audit=qa.qa_resolve_status_partition(left,base,dict(outcome='期限が今日より前で未完了だけ。返金済みは除く'),dict(target_label='期限超過'),controls,judge,'1')
        self.assertEqual(projection['where'],'before_date');self.assertEqual(projection['also'],dict(field='#state',members=['受付']))
        rows=[{'#due':'2000-01-01','#state':'受付'},{'#due':'2000-01-01','#state':'返金済み'},{'#due':'2035-12-31','#state':'受付'}]
        self.assertEqual(qa.qa_evaluate_projection(rows,projection,dict(date='2026-10-30')),'1')

    def test_status_partition_unknown_or_order_biased_answers_stay_failed(self):
        controls=[dict(selector='#state',options=[dict(value='open'),dict(value='closed')])]
        a=dict(metric='count',where='in',field='#state',members=['open'])
        b=dict(a,members=['closed'])
        def unknown(name,prompt,schema,validate,dependency):return validate(dict(membership=[1,-1],evidence_id=0))
        def positional(name,prompt,schema,validate,dependency):return validate(dict(membership=[1,0],evidence_id=0))
        for judge in (unknown,positional):
            with self.assertRaises(ValueError):qa.qa_resolve_status_partition(a,b,dict(outcome='openだけ数える'),dict(target_label='未完了'),controls,judge,'0')

    def test_primary_browser_failure_discards_semantic_repair_receipts_only(self):
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)
            for name in ('primary-projection-membership-0-forward.json','primary-projection-resolution-1-reverse.json','primary-projection-0.json','primary-projection-membership-0-forward-request.json','actions.json'):(directory/name).write_text('{}')
            qa.qa_clear_primary_components(directory)
            self.assertEqual(sorted(p.name for p in directory.iterdir()),['actions.json','primary-projection-membership-0-forward-request.json'])

    def test_grouped_currency_is_one_slot_and_independent_value_keeps_grouping(self):
        formats=qa.qa_display_contracts_from_nodes([dict(selector='#amount',text='¥8,000',label='返金予定の合計')])
        self.assertEqual(formats['#amount']['slots'],1)
        self.assertEqual(formats['#amount']['template'],'¥{n0}')
        raw=dict(exact_check=dict(op='text_equals',selector='#amount',expected_values=['12000.5'],expected_literals=['¥','']))
        self.assertEqual(qa.qa_compile_bound_primary(raw,'#amount',formats)['exact_check']['value'],'¥12,000.5')
        self.assertNotIn('8000',str(raw))

    def test_anonymous_numeric_leaves_are_bound_and_container_is_not_primary(self):
        inventory,cfg=self.component_fixture()
        leaf='#totals > div:nth-child(1) > strong:nth-child(2)'
        formats={'#totals':dict(template='未完了{n0}件 / 超過{n1}件',slots=2,label='対応状況',tag='div'),'#recordCount':dict(template='{n0}',slots=1,label='登録数'),leaf:dict(template='{n0}件',slots=1,label='未完了',tag='strong',ancestor_selectors=['#totals'])}
        inventory['outputs'].append(dict(selector='#totals',tag='div'))
        inventory=qa.qa_merge_display_inventory(inventory,formats)
        cfg=dict(cfg,qa_reference_aggregates=True,_qa_display_contracts=formats)
        seen=[]
        def model(prompt,config,tokens,**kw):
            choices=kw['schema']['properties']['result_selector']['enum'];seen.extend(choices)
            self.assertNotIn('#totals',choices);self.assertIn(leaf,choices)
            return kw['validator'](dict(steps=[dict(op='fill',selector='#title',value='記録A'),dict(op='click',selector='#saveRecord')],result_selector=leaf,acceptance=[0],rationale='登録を確認する'))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True),patch.object(qa,'qa_reference_primary_expectation',return_value=dict(exact_check=dict(op='text_equals',selector=leaf,value='1件'))):
            result=qa.qa_split_unit_generation('元要件',cfg,Path(t),'base-workflow','input',qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)
        self.assertEqual(result['result_selector'],leaf)
        self.assertEqual(len([n for n in inventory['outputs'] if n['selector']==leaf]),1)
        self.assertEqual(len(qa.qa_merge_display_inventory(inventory,formats)['outputs']),len(inventory['outputs']))

    def test_declared_actor_variant_changes_record_inputs_before_oracle(self):
        inventory,cfg=self.component_fixture()
        prior=dict(kind='workflow',result_selector='#recordCount',steps=[dict(op='fill',selector='#title',value='記録A'),dict(op='click',selector='#saveRecord'),dict(op='fill',selector='#title',value='記録B'),dict(op='click',selector='#saveRecord')])
        cfg=dict(cfg,_qa_prior_scenarios=[prior])
        variant=qa.qa_component_variant_actions(cfg,inventory)
        self.assertFalse(qa.qa_variant_repeats_workflow(variant,[prior]))
        self.assertNotIn('exact_check',variant);self.assertNotIn('checks',variant)
        self.assertEqual(variant['acceptance'],[])
        steps=prior['steps']+variant['steps']
        events=qa.qa_component_events(steps,cfg)
        self.assertEqual(len(qa.qa_reference_rows(steps,events)),4)
        self.assertEqual(len({r['#title'] for r in qa.qa_reference_rows(steps,events)}),4)
        self.assertIsNone(qa.qa_component_variant_actions(dict(cfg,qa_component_contract='unknown'),inventory))
        constrained=dict(inventory,controls=[dict(n,pattern='[A-Z]+') if n['selector']=='#title' else n for n in inventory['controls']])
        self.assertIsNone(qa.qa_component_variant_actions(cfg,constrained))

    def test_agreeing_wrong_subset_still_gets_complete_native_state_check(self):
        options=['受付','返送待ち','返金済み'];controls=[dict(selector='#state',tag='select',options=[dict(value=x) for x in options])]
        steps=[]
        for value in options:steps.extend([dict(op='select',selector='#state',value=value),dict(op='click',selector='#save')])
        events=[dict(step_index=i,effect='create',target=None) for i in (1,3,5)]
        def generate(name,prompt,schema,validate,dependency):
            if '-membership-' in name:return validate(dict(membership=[int(s!='返金済み') for s in dependency['ordered_statuses']],evidence_id=0))
            return validate(dict(choice=next(i for i,p in enumerate(dependency['candidates']) if p['where']=='in' and p['members']==['返送待ち'])))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events),patch.object(qa,'qa_blind_record_event_audit',return_value=dict(valid=True)):
            result=qa.qa_reference_primary_expectation(dict(result_selector='#summary',steps=steps),{'#summary':dict(template='{n0}件',slots=1,label='未完了')},dict(requested_outcome='返金済みを除く未完了件数'),dict(model='x'),dict(controls=controls),Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'2件')
        self.assertEqual(proof['projections'][0]['members'],['受付','返送待ち'])
        self.assertEqual(proof['projection_audits'][0]['original_proposed']['members'],['返送待ち'])

    def test_selected_day_binding_receives_named_input_setting_not_just_ids(self):
        controls=[dict(tag='input',selector='#day',type='date',label='作業日'),dict(tag='input',selector='#target',type='date',label='対象日')]
        steps=[dict(op='fill',selector='#day',value='2023-10-29'),dict(op='click',selector='#save'),dict(op='fill',selector='#target',value='2023-10-29')]
        def generate(name,prompt,schema,validate,dependency):
            self.assertIn('対象日',prompt);self.assertIn('explicit view setting',prompt)
            selected=next(c for c in dependency['input_conditions'] if c['selector']=='#target')
            self.assertEqual(selected['label'],'対象日')
            return validate(dict(choice=next(i for i,p in enumerate(dependency['candidates']) if p['where']=='on_input_date')))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=[dict(step_index=1,effect='create',target=None)]),patch.object(qa,'qa_blind_record_event_audit',return_value=dict(valid=True)):
            result=qa.qa_reference_primary_expectation(dict(result_selector='#summary',steps=steps),{'#summary':dict(template='{n0}件',slots=1,label='対象日の件数')},dict(requested_outcome='対象日の作業件数'),dict(model='x',_qa_reference_clock=dict(date='2026-10-30')),dict(controls=controls),Path(t),'case',generate)
        self.assertEqual(result['exact_check']['value'],'1件')

    def time_fixture(self):
        controls=[dict(selector='#date',type='date',label='作業日'),dict(selector='#target',type='date',label='対象日'),dict(selector='#planned',type='number',label='予定（分）'),dict(selector='#actual',type='number',label='実績（分）'),dict(selector='#start',type='time',label='開始'),dict(selector='#end',type='time',label='終了'),dict(selector='#pause',type='number',label='休憩（分）')]
        controls=[dict(n,tag='input') for n in controls]
        inputs={'#target':'2023-10-01','#start':'09:00','#end':'17:00','#pause':'60'}
        choices=qa.qa_projection_candidates(controls,'{n0}分',0,input_values=inputs,row_fields={'#date','#planned','#actual'})
        return controls,inputs,choices

    def test_duration_candidates_compute_native_start_end_break_in_minutes(self):
        controls,inputs,choices=self.time_fixture()
        duration=next(p for p in choices if p['metric']=='duration' and p.get('break_input'))
        self.assertEqual(qa.qa_evaluate_projection([],duration,dict(input_values=inputs)),'420')
        self.assertEqual(qa.qa_evaluate_projection([],duration,dict(input_values=dict(inputs,**{'#start':'09:30','#pause':'45'}))),'405')
        no_pause=next(p for p in choices if p['metric']=='duration' and not p.get('break_input'))
        self.assertEqual(qa.qa_evaluate_projection([],no_pause,dict(input_values=inputs)),'480')
        short=qa.qa_compact_projection_choices(choices,controls)
        self.assertTrue(any('終了−開始−休憩' in p[1] for p in short))

    def test_duration_missing_malformed_overnight_and_pause_overflow_are_rejected(self):
        controls,inputs,choices=self.time_fixture()
        duration=next(p for p in choices if p['metric']=='duration' and p.get('break_input'))
        for change in ({'#end':''},{'#start':'25:00'},{'#end':'08:00'},{'#pause':'999'},{'#pause':'-1'}):
            with self.assertRaises(ValueError):qa.qa_evaluate_projection([],duration,dict(input_values=dict(inputs,**change)))
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([],duration,{})

    def test_date_scoped_sums_and_duration_differences_use_declared_parameters(self):
        controls,inputs,choices=self.time_fixture()
        rows=[{'#date':'2023-10-01','#planned':'60','#actual':'45'},{'#date':'2023-10-01','#planned':'90','#actual':'75'},{'#date':'2026-10-30','#planned':'999','#actual':'888'}]
        planned=next(p for p in choices if p['metric']=='sum' and p.get('value_field')=='#planned')
        self.assertEqual(qa.qa_evaluate_projection(rows,planned,dict(input_values=inputs)),'150')
        remaining=next(p for p in choices if p['metric']=='difference' and p['left']['metric']=='duration' and p['left'].get('break_input') and p['right'].get('value_field')=='#planned')
        self.assertEqual(qa.qa_evaluate_projection(rows,remaining,dict(input_values=inputs)),'270')
        gap=next(p for p in choices if p['metric']=='difference' and p['left'].get('value_field')=='#planned' and p['right'].get('value_field')=='#actual')
        self.assertEqual(qa.qa_evaluate_projection(rows,gap,dict(input_values=inputs)),'30')
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([],planned,{})

    def test_compound_projection_is_bounded_and_does_not_execute_code(self):
        leaf=dict(metric='count',where='all',field='',members=[])
        nested=leaf
        for _ in range(5):nested=dict(metric='difference',left=nested,right=leaf)
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([],nested,{})
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([],dict(metric='exec',expression='anything'),{})

    def test_default_parameters_and_explicit_override_feed_independent_duration(self):
        controls,inputs,choices=self.time_fixture()
        def generate(name,prompt,schema,validate,dependency):
            self.assertIn('09:30',prompt);self.assertIn('開始',prompt)
            return validate(dict(choice=next(i for i,p in enumerate(dependency['candidates']) if p['metric']=='duration' and p.get('break_input'))))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=[]),patch.object(qa,'qa_blind_record_event_audit',return_value=dict(valid=True)):
            result=qa.qa_reference_primary_expectation(dict(result_selector='#total',steps=[dict(op='fill',selector='#start',value='09:30')]),{'#total':dict(template='{n0}分',slots=1,label='使える稼働時間')},dict(requested_outcome='終了から開始と休憩を引いた稼働可能分数'),dict(model='x',_qa_input_defaults=inputs),dict(controls=controls),Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'390分')
        self.assertEqual(proof['reference_clock']['input_values']['#start'],'09:30')
        self.assertEqual(proof['reference_clock']['input_values']['#pause'],'60')

    def test_same_native_workflow_actions_resume_across_oracle_policy_inputs_only(self):
        inventory,cfg=self.component_fixture();inventory['outputs'].append(dict(selector='#summaryValue',tag='strong'))
        cfg=dict(cfg,qa_reference_aggregates=True,_qa_display_contracts={'#summaryValue':dict(slots=1,template='{n0}件',label='件数'),'#recordCount':dict(slots=1,template='{n0}',label='登録数')})
        calls=[]
        def model(prompt,config,tokens,**kw):
            calls.append(config['model'])
            return kw['validator'](dict(steps=[dict(op='fill',selector='#title',value='保存A'),dict(op='click',selector='#saveRecord')],result_selector='#summaryValue',acceptance=[0],rationale='登録して確認する'))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        primary=dict(exact_check=dict(op='text_equals',selector='#summaryValue',value='1件'))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'ai_json',side_effect=model,create=True),patch.object(qa,'qa_reference_primary_expectation',return_value=primary):
            args=('same scope',cfg,Path(t),'base-workflow')
            for identity in ('first oracle policy','changed input default policy'):
                qa.qa_split_unit_generation(*args,identity,qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)
            self.assertEqual(calls,['mapper'])
            self.assertTrue((Path(t)/'base-workflow-split'/'actions-resumed.json').exists())
            qa.qa_split_unit_generation('same scope',dict(cfg,qa_action_model='different'),Path(t),'base-workflow','third',qa.qa_unit_schema(1,'workflow'),lambda raw:raw,inventory)
            self.assertEqual(calls,['mapper','different'])
            self.assertFalse((Path(t)/'base-workflow-split'/'actions-resumed.json').exists())

    def test_single_disputed_state_gets_independent_positive_negative_questions(self):
        controls=[dict(selector='#state',options=[dict(value=s) for s in ['受付','返送待ち','返金済み']])]
        rule=dict(metric='count',where='in',field='#state',members=['返送待ち'])
        names=[]
        def generate(name,prompt,schema,validate,dependency):
            names.append(name)
            self.assertNotIn('initial_classifications',prompt)
            if '-state-' in name:
                self.assertEqual(dependency['status'],'受付')
                return validate(dict(decision='included',evidence_id=0))
            membership=[int(s!='返金済み') for s in dependency['ordered_statuses']]
            if name.endswith('reverse'):membership[dependency['ordered_statuses'].index('受付')]=0
            return validate(dict(membership=membership,evidence_id=0))
        projection,audit=qa.qa_resolve_status_partition(rule,rule,dict(outcome='返金済み以外の受付・返送待ちを未完了として数える'),dict(target_label='未完了'),controls,generate,'0')
        self.assertEqual(projection['members'],['受付','返送待ち'])
        self.assertEqual(len(names),4)
        self.assertEqual(audit['initial_classifications'][1]['受付'],0)
        self.assertEqual(audit['classified_states']['受付'],1)
        self.assertEqual(len(audit['resolved_disagreements']),1)

    def test_disputed_state_unconfirmed_inverted_answers_cannot_pass(self):
        controls=[dict(selector='#state',options=[dict(value='open'),dict(value='closed')])]
        rule=dict(metric='count',where='in',field='#state',members=['open'])
        def generate(name,prompt,schema,validate,dependency):
            if '-state-' in name:return validate(dict(decision=1,evidence_id=0))
            return validate(dict(membership=[1,0],evidence_id=0))
        with self.assertRaises(ValueError):qa.qa_resolve_status_partition(rule,rule,dict(outcome='openだけ'),dict(target_label='未完了'),controls,generate,'0')

    def test_native_invalid_protocol_preserves_all_prior_saved_checks(self):
        inventory,cfg=self.component_fixture();inventory['controls'].append(dict(selector='#restoreFile',tag='input',type='file'))
        workflow=dict(kind='workflow',steps=[dict(op='fill',selector='#title',value='保存A'),dict(op='click',selector='#saveRecord')])
        prior=dict(kind='roundtrip',steps=[dict(op='restore_file',selector='#restoreFile')],checks=[dict(op='text_equals',selector='#recordCount',value='1'),dict(op='text_contains',selector='#recordRows',value='保存A')])
        case=qa.qa_component_invalid_case(cfg,inventory,[workflow,prior],1)
        self.assertEqual(case['steps'],[dict(op='restore_invalid',selector='#restoreFile'),dict(op='fill',selector='#title',value=''),dict(op='click',selector='#saveRecord')])
        self.assertEqual(case['checks'][:2],prior['checks'])
        self.assertIn(dict(op='invalid',selector='#title'),case['checks'])
        qa.validate_qa_inventory_actions(case,inventory,'invalid')
        self.assertIsNone(qa.qa_component_invalid_case(dict(cfg,qa_component_contract='unknown'),inventory,[workflow,prior],1))
        self.assertIsNone(qa.qa_component_invalid_case(cfg,inventory,[workflow,dict(prior,steps=[])],1))

    def test_hour_minute_slots_derive_from_one_independent_minute_rule(self):
        controls,inputs,choices=self.time_fixture()
        formats=qa.qa_display_contracts_from_nodes([dict(selector='#time',text='7時間00分',label='使える稼働時間')])
        calls=[]
        def generate(name,prompt,schema,validate,dependency):
            calls.append(name)
            return validate(dict(choice=next(i for i,p in enumerate(dependency['candidates']) if p['metric']=='duration' and p.get('break_input'))))
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=[]),patch.object(qa,'qa_blind_record_event_audit',return_value=dict(valid=True)):
            result=qa.qa_reference_primary_expectation(dict(result_selector='#time',steps=[]),formats,dict(requested_outcome='開始終了から休憩を引いた分数を時間と分で表示'),dict(model='x',_qa_input_defaults=inputs),dict(controls=controls),Path(t),'case',generate)
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
        self.assertEqual(result['exact_check']['value'],'7時間00分')
        self.assertEqual(proof['values'],['7','0'])
        self.assertEqual(proof['projection_audits'][1]['derived_from'],0)
        self.assertEqual(len(calls),2)
        changed=dict(input_values=dict(inputs,**{'#start':'09:30','#pause':'45'}))
        self.assertEqual([qa.qa_evaluate_projection([],p,changed) for p in proof['projections']],['6','45'])

    def test_zero_padding_formats_independent_numbers_without_copying_display(self):
        formats=qa.qa_display_contracts_from_nodes([dict(selector='#time',text='7時間00分',label='時間')])
        self.assertEqual(formats['#time']['number_widths'],[0,2])
        raw=dict(exact_check=dict(op='text_equals',selector='#time',expected_values=['8','5'],expected_literals=['','時間','分']))
        self.assertEqual(qa.qa_compile_bound_primary(raw,'#time',formats)['exact_check']['value'],'8時間05分')
        source=dict(metric='duration',start_input='#start',end_input='#end',break_input='#pause')
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([],dict(metric='time_component',component='bad',source_rule=source),{})
        with self.assertRaises(ValueError):qa.qa_evaluate_projection([{'#n':'-5'}],dict(metric='time_component',component='hours',source_rule=dict(metric='sum',where='all',field='#n')),{})

    def test_feature_create_submissions_use_the_same_required_input_repair(self):
        inventory,cfg=self.component_fixture()
        inventory['controls'].extend([dict(selector='#date',tag='input',type='date',required=True,form='#recordForm'),dict(selector='#status',tag='select',required=True,form='#recordForm',options=[dict(value='open')])])
        raw=dict(steps=[dict(op='fill',selector='#title',value='保存A'),dict(op='click',selector='#saveRecord')])
        def repair(value,*args):
            return dict(value,steps=value['steps'][:-1]+[dict(op='fill',selector='#date',value='2026-10-30'),dict(op='select',selector='#status',value='open')]+value['steps'][-1:])
        with patch.object(qa,'repair_qa_missing_initial_inputs',side_effect=repair) as fix:
            result=qa.qa_prepare_native_submissions(raw,inventory,'feature',cfg)
        fix.assert_called_once()
        self.assertEqual(result['steps'][-1]['selector'],'#saveRecord')
        self.assertEqual(result['steps'][1]['selector'],'#date')
        self.assertEqual(result['steps'][2]['selector'],'#status')

    def test_feature_multiple_record_overwrites_reject_but_explicit_draft_edit_remains_valid(self):
        inventory,cfg=self.component_fixture()
        raw=dict(steps=[dict(op='fill',selector='#title',value='Aさん'),dict(op='fill',selector='#title',value='Bさん'),dict(op='click',selector='#saveRecord')])
        with self.assertRaisesRegex(ValueError,'上書き'):qa.qa_prepare_native_submissions(raw,inventory,'feature',cfg)
        edit_cfg=dict(cfg,_qa_feature_context=dict(condition_index=0),_qa_spec=dict(acceptance=['名前の誤入力を修正して保存する']))
        self.assertEqual(qa.qa_prepare_native_submissions(raw,inventory,'feature',edit_cfg),raw)
        unknown=dict(cfg,qa_component_contract='unknown')
        self.assertEqual(qa.qa_prepare_native_submissions(raw,inventory,'feature',unknown),raw)

    def test_unknown_vector_state_requires_positive_inverse_confirmation_before_pass(self):
        controls=[dict(selector='#state',options=[dict(value='open'),dict(value='closed')])]
        rule=dict(metric='count',where='in',field='#state',members=['open'])
        names=[]
        def generate(name,prompt,schema,validate,dependency):
            names.append(name)
            if '-state-' in name:return validate(dict(decision='excluded',evidence_id=0))
            return validate(dict(membership=[-1 if s=='closed' else 1 for s in dependency['ordered_statuses']],evidence_id=0))
        projection,audit=qa.qa_resolve_status_partition(rule,rule,dict(outcome='closedを除く'),dict(target_label='未完了'),controls,generate,'0')
        self.assertEqual(projection['members'],['open'])
        self.assertEqual(audit['initial_classifications'][0]['closed'],-1)
        self.assertEqual(audit['classified_states']['closed'],0)
        self.assertEqual(len(names),4)

    def test_causal_variant_changes_capacity_dependency_not_only_record_identity(self):
        inventory,cfg=self.component_fixture()
        extra=qa.compact_qa_inventory('<input id="start" type="time"><input id="end" type="time"><input id="break" type="number" min="0" max="120"><input id="windowDate" type="date">')['controls']
        inventory=dict(inventory,controls=inventory['controls']+extra)
        prior=dict(kind='workflow',result_selector='#capacity',steps=[dict(op='fill',selector='#title',value='記録A'),dict(op='click',selector='#saveRecord'),dict(op='fill',selector='#windowDate',value='2026-10-30'),dict(op='click',selector='#saveCapacity')])
        rule=dict(metric='duration',where='inputs',start_input='#start',end_input='#end',break_input='#break')
        values={'#start':'09:00','#end':'17:00','#break':'60'}
        proof=dict(steps=prior['steps'],expected=dict(selector='#capacity'),projections=[dict(metric='time_component',component=c,source_rule=rule) for c in ('hours','minutes')],reference_clock=dict(input_values=values))
        cfg=dict(cfg,_qa_workflow_projection_proof=proof,_qa_prior_scenarios=[prior])
        variant=qa.qa_component_variant_actions(cfg,inventory)
        changed=dict(values,**{s['selector']:s['value'] for s in variant['steps'] if s['op']=='fill'})
        self.assertEqual(qa.qa_evaluate_projection([],rule,dict(input_values=values)),'420')
        self.assertEqual(qa.qa_evaluate_projection([],rule,dict(input_values=changed)),'405')
        self.assertEqual(changed['#windowDate'],'2026-10-30')
        self.assertEqual(variant['steps'][-1],dict(op='click',selector='#saveCapacity'))
        self.assertFalse(any(k in variant for k in ('checks','exact_check')))
        # An unrelated receipt or invalid native bound must not invent a causal input.
        self.assertEqual(qa.qa_duration_variant_inputs(dict(cfg,_qa_workflow_projection_proof=dict(proof,steps=[])),inventory,prior),[])
        limited=dict(inventory,controls=[dict(n,max='60') if n['selector']=='#break' else n for n in inventory['controls']])
        self.assertIsNone(qa.qa_component_variant_actions(cfg,limited))

    def test_roundtrip_mutation_is_distinct_from_prior_variant_and_preserves_independent_checks(self):
        inventory,cfg=self.component_fixture()
        prior=dict(kind='workflow',result_selector='#recordCount',steps=[dict(op='fill',selector='#title',value='記録A'),dict(op='click',selector='#saveRecord')])
        cfg=dict(cfg,_qa_prior_scenarios=[prior])
        variant=qa.qa_component_variant_actions(cfg,inventory)
        mutation=qa.qa_component_variant_actions(dict(cfg,_qa_variant_suffix='復元変更C'),inventory)
        self.assertNotEqual(variant['steps'],mutation['steps'])
        checks=[dict(op='text_equals',selector='#recordCount',value='2'),dict(op='text_contains',selector='#recordRows',value='記録A')]
        compiled=qa.compile_qa_roundtrip(dict(csv_selector='#downloadCsv',csv_contains=['記録A','記録A 別入力B1'],json_selector='#downloadJson',restore_selector='#restoreFile',confirmation_mode='native',confirmation_steps=[],mutation_steps=mutation['steps'],checks=checks,acceptance=[],rationale='保存済みの独立検査へ実ファイルから復元する'),1)
        self.assertEqual(compiled['checks'],checks)
        self.assertEqual([s['op'] for s in compiled['steps']][-3:],['cancel_restore','restore_file','restore_file'])

    def test_focused_status_labels_have_fixed_meaning_and_contradictions_still_fail(self):
        controls=[dict(selector='#state',options=[dict(value='open'),dict(value='closed')])]
        rule=dict(metric='count',where='in',field='#state',members=['open'])
        def model(name,prompt,schema,validate,dependency):
            if '-state-' in name:
                self.assertEqual(schema['properties']['decision']['enum'],['included','excluded','unknown'])
                return validate(dict(decision='included' if dependency['question']=='included' else 'excluded',evidence_id=0))
            return validate(dict(membership=[1,0],evidence_id=0))
        with self.assertRaisesRegex(ValueError,'独立対応が不一致'):
            qa.qa_resolve_status_partition(rule,rule,dict(outcome='openだけ数える'),dict(target_label='未完了'),controls,model,'0')
