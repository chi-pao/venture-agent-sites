import hashlib,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_system_baseline as baseline
app=baseline.app

class ModelBenchmarkTests(unittest.TestCase):
 def setUp(self):baseline.FrameworkTests.setUp(self)
 def tearDown(self):baseline.FrameworkTests.tearDown(self)
 def record(self,model,task,passed=True):
  root=self.root/'out'/model.replace(':','-')/task;root.mkdir(parents=True,exist_ok=True)
  path=root/'candidate.html';path.write_text('<html><body>test artifact</body></html>')
  shots={}
  for width in (1280,390):
   shot=root/(str(width)+'.png');shot.write_bytes(b'unit-test-image-placeholder');shots[str(shot)]=hashlib.sha256(shot.read_bytes()).hexdigest()
  return dict(model=model,task=task,label=task,passed=passed,path=str(path),content_sha=hashlib.sha256(path.read_bytes()).hexdigest(),screenshots=shots,
    checks=[dict(width=w,check=c,passed=True) for w in (1280,390) for c in ('layout','two_records','invalid_input','reload','csv','result_layout')],seconds=1)
 def report(self):
  old='qwen2.5:7b';new='qwen2.5-coder:7b'
  return dict(policy=app.MODEL_BENCHMARK_POLICY,task_signature=app.benchmark_task_signature(),baseline=old,candidate=new,general_model=old,status='完了',installed={old:'old-digest',new:'new-digest'},results=[self.record(m,t,passed=(m==new or t=='new')) for m in (old,new) for t in ('new','repair')])
 def test_winner_requires_complete_actual_artifacts_and_strictly_more_passes(self):
  report=self.report();self.assertTrue(app.benchmark_candidate_wins(report))
  report['results'][1]['passed']=True;self.assertFalse(app.benchmark_candidate_wins(report))
  report=self.report();report['results'][-1]['passed']=False;self.assertFalse(app.benchmark_candidate_wins(report))
  report=self.report();Path(report['results'][-1]['path']).write_text('changed');self.assertFalse(app.benchmark_candidate_wins(report))
  report=self.report();report['results'][0].pop('path');self.assertFalse(app.benchmark_candidate_wins(report))
 def test_adoption_is_manual_scoped_and_can_be_rolled_back(self):
  report=self.report();app.save_benchmark_state(report)
  self.assertNotIn('code_model',app.config())
  with patch.object(app,'benchmark_model_digests',return_value=report['installed']):
   self.assertEqual(app.adopt_benchmark_candidate(app.config()),report['candidate'])
  cfg=app.config();self.assertEqual(cfg['model'],report['baseline']);self.assertEqual(app.coding_config(cfg)['model'],report['candidate'])
  cfg['payment_url']='https://example.com/preserved';app.execute('UPDATE autonomous_control SET config=? WHERE id=1',(json.dumps(cfg),))
  self.assertEqual(app.restore_previous_code_model(),report['baseline']);self.assertEqual(app.config()['payment_url'],'https://example.com/preserved')
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def test_incomplete_or_changed_models_cannot_be_adopted(self):
  report=self.report();report['status']='実行中';app.save_benchmark_state(report)
  with self.assertRaises(ValueError):app.adopt_benchmark_candidate(app.config())
  report=self.report();app.save_benchmark_state(report)
  with patch.object(app,'benchmark_model_digests',return_value={report['baseline']:'changed',report['candidate']:'new-digest'}):
   with self.assertRaises(ValueError):app.adopt_benchmark_candidate(app.config())
 def test_comparison_and_development_do_not_start_together(self):
  app.execute('UPDATE autonomous_control SET enabled=1')
  with self.assertRaises(ValueError):app.start_model_benchmark(app.config(),'qwen2.5-coder:7b')
  app.execute('UPDATE autonomous_control SET enabled=0')
  with patch.object(app,'benchmark_active',return_value=True):
   self.assertIn('比較中',app.start(app.config()))
  self.assertFalse(app.state()['enabled'])
 def test_only_code_requests_use_candidate_and_settings_are_not_mutated(self):
  cfg=dict(app.DEFAULT,code_model='qwen2.5-coder:7b');routed=app.coding_config(cfg)
  self.assertEqual(routed['model'],'qwen2.5-coder:7b');self.assertEqual(cfg['model'],'qwen2.5:7b')
  report=self.report();report['task_signature']='outdated';self.assertFalse(app.benchmark_candidate_wins(report))
 def test_worker_uses_same_prompts_and_generation_settings_without_auto_adoption(self):
  report=self.report();report.update(status='実行中',run_id='test-run',results=[])
  def evaluated(source,root):
   task=Path(root).name.split('-')[0];model=report['baseline'] if source=='old-output' else report['candidate']
   return self.record(model,task,passed=model==report['candidate'])
  with patch.object(app,'ensure_autoqa_environment'),patch.object(app,'local_ai_request',side_effect=lambda prompt,cfg,tokens:'old-output' if cfg['model']==report['baseline'] else 'new-output') as generate,patch.object(app,'execute_model_benchmark_page',side_effect=evaluated),patch.object(app,'benchmark_model_digests',return_value=report['installed']):
   app.model_benchmark_worker(app.config(),report,'test-owner')
  calls=generate.call_args_list;self.assertEqual(len(calls),4)
  self.assertEqual(calls[0].args[0],calls[1].args[0]);self.assertEqual(calls[2].args[0],calls[3].args[0])
  self.assertTrue(all(c.args[1]['_seed']==42 and c.args[1]['_temperature']==0 and c.args[2]==5000 for c in calls))
  self.assertEqual(app.benchmark_state()['status'],'完了');self.assertTrue(app.benchmark_candidate_wins(app.benchmark_state()));self.assertNotIn('code_model',app.config())

if __name__=='__main__':unittest.main()
