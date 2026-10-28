"""Reference-state tests. These do not claim real-model or product acceptance."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('reference_module',Path(__file__).resolve().parents[1]/'agent'/'qa_checkpoint_planner.py')
qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(qa)
qa.AutoQAPlanError=ValueError

class ReferenceCountTests(unittest.TestCase):
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
        calls=[]
        def model(prompt,cfg,tokens,**kwargs):
            calls.append(prompt)
            answer=(dict(quantity='record_count',source_quote='返品記録を追加',events=[dict(step_index=1,effect='create',target=None),dict(step_index=3,effect='create',target=None)]) if len(calls)==1 else dict(valid=True,reason='二つの保存操作は元仕様に基づく別記録の追加である'))
            return kwargs['validator'](answer)
        qa.ai_json=model;qa.write_framework_json=lambda p,v:p.write_text(qa.json.dumps(v,ensure_ascii=False))
        prior=[dict(steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#save')])]
        raw=dict(steps=[dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#save')],exact_check=dict(selector='#recordCount',value='999'))
        with tempfile.TemporaryDirectory() as t:
            result=qa.qa_reference_count_oracle(raw,{},dict(must_have=['返品記録を追加']),dict(model='planner'),Path(t),'base-variant',prior)
            self.assertEqual(result['exact_check']['value'],'2')
            self.assertEqual(result['steps'],raw['steps'])
            self.assertTrue((Path(t)/'base-variant-reference-count-proof.json').exists())
        self.assertEqual(len(calls),2)
        self.assertNotIn('999',''.join(calls))

if __name__=='__main__':unittest.main()
