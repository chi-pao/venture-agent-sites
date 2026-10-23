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

 def complete_spec(self):
  return dict(audience='個人講師',requested_outcome='出欠を登録して集計保存する',differentiation='未回答と欠席を区別して確認する',workflow=['名簿を登録する','出欠を入力する','集計を保存する'],must_have=['名簿登録','出欠集計','保存と復元'],acceptance=['名簿の再表示を確認','欠席と未回答の集計を照合','保存後の再読込を照合'],delivery_mode='browser_local',dependencies=[])
 def test_missing_list_entries_are_repaired_using_actual_validation_feedback(self):
  name='項目不足から修正する設計';valid=self.complete_spec();bad=dict(valid,workflow=['入力'],acceptance={'check':'保存'})
  with patch.object(app,'ai',side_effect=[json.dumps(bad,ensure_ascii=False),json.dumps(valid,ensure_ascii=False)]) as model:
   spec=app.ensure_product_spec(name,dict(app.DEFAULT))
  self.assertEqual(spec['workflow'],valid['workflow']);self.assertEqual(model.call_count,2)
  retry=model.call_args.args[0];self.assertIn('workflow（利用手順）が1件',retry);self.assertIn('acceptance（操作確認）は文字列配列',retry)
  self.assertIn('前回のJSON',retry);self.assertIn('出欠',retry)
  schema=model.call_args.args[1]['_json_response'];self.assertEqual(schema['properties']['workflow']['minItems'],3)
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def test_repeated_inadequate_design_is_bounded_and_never_saved_or_padded(self):
  valid=self.complete_spec();bad=dict(valid,must_have=['登録','集計'])
  with patch.object(app,'ai',return_value=json.dumps(bad,ensure_ascii=False)) as model:
   with self.assertRaises(app.AutoQAPlanError):app.ensure_product_spec('不足が直らない設計',dict(app.DEFAULT))
  self.assertEqual(model.call_count,3);self.assertIsNone(app.get_product_spec('不足が直らない設計'))
 def test_successful_design_repair_reaches_build_in_same_cycle(self):
  name='修正して制作に進む案';app.execute('UPDATE autonomous_control SET enabled=1')
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  valid=self.complete_spec();bad=dict(valid,must_have=['登録'])
  with patch.object(app,'ai',side_effect=[json.dumps(bad),json.dumps(valid)]),patch.object(app,'build',return_value=('draft','制作検査は未合格',False)) as build:
   app.quality_development_cycle(job,dict(app.DEFAULT))
  self.assertEqual(build.call_count,1);self.assertIsNotNone(app.get_product_spec(name));self.assertFalse(app.candidate_production_acceptance(name))
  history=app.query('SELECT details FROM agent_jobs WHERE id=?',(job,))[0]['details'];self.assertIn('開発開始基準',history)
 def test_transport_sends_required_keys_and_minimum_list_lengths_as_schema(self):
  cfg=dict(app.DEFAULT,_json_response=app.PRODUCT_SPEC_SCHEMA)
  with patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(b'{"response":"{}"}')) as request:
   app.local_ai_request('設計',cfg)
  schema=json.loads(request.call_args.args[0].data)['format']
  self.assertIn('must_have',schema['required']);self.assertEqual(schema['properties']['acceptance']['minItems'],3)

 def test_layout_exception_returns_to_repair_in_same_build_without_release(self):
  name='小さい操作部品を直す試作';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  spec=app.get_product_spec(name);app.store_product_spec(name,dict(spec,delivery_mode='connected',dependencies=['共有サーバー']))
  source='<html><body>'+('existing-function;'*100)+'</body></html>'
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'incremental_product_repair',side_effect=lambda *a,**k:(a[2].replace('existing-function;','improved-function;',1), '部品サイズの修正')) as repair,patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',return_value=(True,'簡易検査合格')),patch.object(app,'review_connected_layout',side_effect=[ValueError('1280pxの接続待ち画面に改善が必要: smallControls inputValue calculate'),(True,'画面検査: 合格（API実動作は別）')]),patch.object(app,'event'):
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=2),'操作部品の改善',existing_page=source,allow_partial=True)
  self.assertEqual(repair.call_count,2);self.assertIn('smallControls',repair.call_args.args[3]);self.assertIn('画面検査: 合格',detail)
  self.assertFalse(ready);self.assertFalse(app.candidate_production_acceptance(name));self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def comparison_fixture(self,name):
  baseline.FrameworkTests.add(self,name);sources,patterns=baseline.DesignEvidenceTests.fixture(self)
  comparisons=[dict(source_url=u,source_quote=r['text'],relevance='利用者の予定と結果を同じ作業で整理する方法です。',comparison='同じ入力の保存と再表示の手順を比較し不明点を区別する。') for u,r in sources.items()]
  item=dict(comparisons=comparisons,target_task='具体的な予定を入力して保存し結果を比較する。',proposed_advantage='未確認の予定を区別し入力の迷いを減らす仮説。',own_acceptance_index=0,benchmark={k:'同じ入力を使って完了率と時間と迷いを測定する。' for k in ('scenario','measure','continue_if','reconsider_if')},design_patterns=patterns)
  references=[dict(r,status='本文取得',url=u,checked_at=app.now(),content_sha='a'*64) for u,r in sources.items()]
  return item,references
 def test_mismatched_competitor_quote_is_repaired_using_retrieved_text(self):
  import copy
  name='引用の不一致を直す比較';valid,refs=self.comparison_fixture(name);bad=copy.deepcopy(valid);bad['comparisons'][0]['source_quote']='公式本文にない作り話なので比較の根拠には使えません。'
  with patch.object(app,'competitive_reference_candidates',return_value=[r['url'] for r in refs]),patch.object(app,'read_research_reference',side_effect=refs),patch.object(app,'ai',side_effect=[json.dumps(bad),json.dumps(valid)]) as model:
   brief=app.ensure_competitive_brief(name,dict(app.DEFAULT))
  self.assertEqual(model.call_count,2);self.assertIn('公式の取得本文と一致しません',model.call_args.args[0]);self.assertTrue(app.competitive_design_ready(brief));self.assertFalse(brief['measured_advantage'])
 def test_persistent_invented_comparison_is_not_cached_as_valid(self):
  name='不一致が残る比較';bad,refs=self.comparison_fixture(name);bad['comparisons'][0]['source_quote']='公式本文にない作り話なので比較の根拠には使えません。'
  with patch.object(app,'competitive_reference_candidates',return_value=[r['url'] for r in refs]),patch.object(app,'read_research_reference',side_effect=refs),patch.object(app,'ai',return_value=json.dumps(bad)) as model:
   with self.assertRaises(app.AutoQAPlanError):app.ensure_competitive_brief(name,dict(app.DEFAULT))
  self.assertEqual(model.call_count,3);self.assertIsNone(app.competitive_context(name)['brief'])

 def test_invalid_edit_anchor_is_repaired_against_same_original_code(self):
  name='置換元の修正';baseline.FrameworkTests.add(self,name)
  source='<html><body><div id="value">original-value</div>'+('preserve-existing;'*100)+'</body></html>'
  bad={'reason':'該当しない置換案','edits':[{'old':'missing-original-value','new':'new-value'}]}
  valid={'reason':'一致する置換元に修正','edits':[{'old':'original-value','new':'improved-value'}]}
  with patch.object(app,'ai',side_effect=[json.dumps(bad),json.dumps(valid)]) as model:
   page,reason=app.incremental_product_repair(1,name,source,'JavaScriptエラーを修正',dict(app.DEFAULT))
  self.assertEqual(model.call_count,2);self.assertIn('一致数: 0',model.call_args.args[0]);self.assertIn(source,model.call_args.args[0])
  self.assertEqual(page,source.replace('original-value','improved-value'));self.assertNotIn('missing-original-value',page)
 def test_unresolved_connected_work_does_not_log_successful_improvement(self):
  name='改善未完了の表示';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  app.store_product_spec(name,dict(app.get_product_spec(name),delivery_mode='connected',dependencies=['共有サーバー']))
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  with patch.object(app,'build',return_value=('draft','JavaScriptエラー: Unexpected token .',False)):
   app.quality_development_cycle(job,dict(app.DEFAULT))
  history=app.query('SELECT details FROM agent_jobs WHERE id=?',(job,))[0]['details'];self.assertIn('改善は未完了',history);self.assertNotIn('画面・独立機能を改善。',history)

if __name__=='__main__':unittest.main()
