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
            if name in ('primary-projection-0','primary-projection-1'):answer=projections[int(name[-1])]
            else:answer=dict(valid=True,reason='元要件と実入力項目に対応し、固定の表示ラベルのみを扱う')
            return validate(answer)
        spec=dict(requested_outcome='返品の全保存件数と期限超過数を表示',must_have=['対応期限が今日より前なら期限超過として数える'],acceptance=['未実行の100件を期待する入力例'])
        qa.write_framework_json=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False))
        with tempfile.TemporaryDirectory() as t,patch.object(qa,'qa_bind_record_clicks',return_value=events):
            answer=qa.qa_reference_primary_expectation(actions,formats,spec,dict(_qa_reference_clock=dict(date='2026-10-29')),dict(controls=[dict(tag='input',type='date',selector='#deadline')]),Path(t),'case',generate)
            self.assertEqual(answer['exact_check']['value'],'1件 / 超過0件')
            proof=json.loads((Path(t)/'case-aggregate-proof.json').read_text())
            self.assertEqual(proof['values'],['1','0'])
            self.assertEqual(proof['rows'],[{'#deadline':'2035-12-31'}])
            self.assertIn('primary-projection-audit-1',calls)
            def reject(name,prompt,schema,validate,dependency):return validate(dict(valid=False,reason='元要件には対応しない集計条件が提案されています'))
            with self.assertRaises(ValueError):qa.qa_reference_primary_expectation(actions,formats,spec,{},dict(controls=[]),Path(t),'bad',reject)

    def test_second_submit_requires_required_select_again(self):
        inventory=qa.compact_qa_inventory('<form id="form"><input id="name" required><select id="status" required><option value="">選択</option><option value="open">未着手</option></select><button id="save" type="submit">保存</button></form>')
        steps=[dict(op='fill',selector='#name',value='A'),dict(op='select',selector='#status',value='open'),dict(op='click',selector='#save'),dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')]
        with self.assertRaises(ValueError):qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)
        steps.insert(-1,dict(op='select',selector='#status',value='open'))
        self.assertEqual(qa.qa_validate_repeated_form_inputs(dict(steps=steps),inventory)['steps'],steps)
