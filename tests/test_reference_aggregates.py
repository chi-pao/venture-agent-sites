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

    def test_second_submit_requires_required_select_again(self):
        inventory=qa.compact_qa_inventory('<form id="form"><input id="name" required><select id="status" required><option value="">選択</option><option value="open">未着手</option></select><button id="save" type="submit">保存</button></form>')
        steps=[dict(op='fill',selector='#name',value='A'),dict(op='select',selector='#status',value='open'),dict(op='click',selector='#save'),dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')]
        with self.assertRaises(ValueError):qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)
        steps.insert(-1,dict(op='select',selector='#status',value='open'))
        self.assertEqual(qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)['steps'],steps)
