"""Structured model answers must recover formatting without fabricating valid plans."""
import io,json,unittest
from unittest.mock import patch
import test_system_baseline as baseline
app=baseline.app

class StructuredResponseTests(unittest.TestCase):
 def setUp(self):baseline.FrameworkTests.setUp(self)
 def tearDown(self):baseline.FrameworkTests.tearDown(self)
 def test_prose_fence_thinking_and_nested_json(self):
  value={'audience':'講師','workflow':['入力','確認','保存'],'nested':{'text':'引用の { と } はデータ'}}
  raw=json.dumps(value,ensure_ascii=False)
  for response in (raw,'以下が設計です。\n'+raw+'\n設計は以上です。','```json\n'+raw+'\n```','<think>検討中です。</think>\n'+raw):
   self.assertEqual(app.qa_json(response),value)
 def test_incomplete_or_ambiguous_answers_never_become_accepted_objects(self):
  for response in ('','説明だけ','{"a":1','{"outer":{"ok":true}', '{"a":1}{"a":2}', '[{"a":1}]','{"a":1,"a":2}','{"a":NaN}'):
   with self.subTest(response=response),self.assertRaises(app.AutoQAPlanError):app.qa_json(response)
 def test_format_retry_is_bounded_and_does_not_mutate_configuration(self):
  cfg=dict(app.DEFAULT)
  with patch.object(app,'ai',side_effect=['説明のみ','{"result":"valid"}']) as model:
   self.assertEqual(app.ai_json('元の要件を含む設計',cfg),{'result':'valid'})
   self.assertEqual(model.call_count,2);self.assertTrue(model.call_args.args[1]['_json_response'])
   self.assertIn('元の要件',model.call_args.args[0]);self.assertNotIn('_json_response',cfg)
  with patch.object(app,'ai',return_value='{"cut":') as model:
   with self.assertRaises(app.AutoQAPlanError):app.ai_json('設計',cfg)
   self.assertEqual(model.call_count,2)
 def test_spec_can_recover_and_save_before_build_without_quality_permission(self):
  name='回答形式の復旧試作';spec=dict(audience='個人講師',requested_outcome='出欠を記録して集計保存する',differentiation='未回答を区別する',workflow=['入力','集計','保存'],must_have=['入力','集計','保存'],acceptance=['入力確認','集計確認','保存確認'],delivery_mode='browser_local',dependencies=[])
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  with patch.object(app,'ai',side_effect=['説明のみ','```json\n'+json.dumps(spec,ensure_ascii=False)+'\n```\n設計は以上です。']):
   saved=app.ensure_product_spec(name,dict(app.DEFAULT));self.assertEqual(saved['audience'],'個人講師')
  self.assertIsNotNone(app.get_product_spec(name));self.assertFalse(app.candidate_production_acceptance(name))
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def test_valid_json_with_missing_requirements_is_still_rejected(self):
  with patch.object(app,'ai',return_value='{"audience":"講師"}'):
   with self.assertRaises(ValueError):app.ensure_product_spec('不十分な設計',dict(app.DEFAULT))
  self.assertIsNone(app.get_product_spec('不十分な設計'))
 def test_transport_enforces_json_only_for_structured_requests(self):
  for structured in (False,True):
   response=io.BytesIO(json.dumps({'response':'{"ok":true}'}).encode())
   with patch.object(app.urllib.request,'urlopen',return_value=response) as request:
    app.local_ai_request('設計',dict(app.DEFAULT,_json_response=structured))
    payload=json.loads(request.call_args.args[0].data)
    if structured:self.assertEqual(payload['format'],'json')
    else:self.assertNotIn('format',payload)
 def test_dashboard_explains_json_failure_as_development_block_not_no_demand(self):
  issue,next_action=app.development_brief(dict(stage='設計・修正待ち',details='JSONDecodeError: Extra data line 19 column 1'))
  self.assertIn('開発処理を進められていません',issue);self.assertIn('再生成',next_action)

 def test_planning_failure_is_visible_in_job_history_and_keeps_retry_state(self):
  name='履歴に出る設計失敗';app.execute('UPDATE autonomous_control SET enabled=1')
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  with patch.object(app,'ensure_product_spec',side_effect=app.AutoQAPlanError('AI回答形式の再生成にも失敗')):
   app.quality_development_cycle(job,dict(app.DEFAULT))
  history=app.query('SELECT details FROM agent_jobs WHERE id=?',(job,))[0]['details']
  self.assertIn(name+': 完成条件の設計・読み込みを開始',history)
  self.assertIn('設計・修正を進められませんでした',history);self.assertIn('AI回答形式',history)
  self.assertEqual(app.query('SELECT stage FROM venture_product_development WHERE idea=?',(name,))[0]['stage'],'設計・修正待ち')
 def test_saved_development_with_no_html_attempt_is_resumed(self):
  name='試作前に設計失敗した案';app.execute('UPDATE autonomous_control SET enabled=1')
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,0,?,?)',(name,app.now(),app.now()))
  app.product_development_state(name,'設計・修正待ち','前回はAI回答形式の失敗')
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  with patch.object(app,'ensure_product_spec',side_effect=app.AutoQAPlanError('今回も形式エラー')) as design:
   app.quality_development_cycle(job,dict(app.DEFAULT))
  self.assertEqual(design.call_count,1)
  self.assertIn(name,app.query('SELECT details FROM agent_jobs WHERE id=?',(job,))[0]['details'])
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])

if __name__=='__main__':unittest.main()
