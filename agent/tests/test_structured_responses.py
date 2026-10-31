"""Structured model answers must recover formatting without fabricating valid plans."""
import io,json,unittest
from pathlib import Path
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
   saved=app.ensure_product_spec('不十分な設計',dict(app.DEFAULT))
  # The incomplete AI answer is not accepted as-is (1e2d037): a labelled compiler draft replaces it.
  self.assertEqual(saved['requirements_method'],'requirements_compiler_fallback');self.assertNotEqual(saved['audience'],'講師')
  self.assertGreaterEqual(len(saved['acceptance']),3);self.assertFalse(app.candidate_production_acceptance('不十分な設計'))
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

 def qa_plan(self):
  def scenario(kind,steps,checks,covers):
   return dict(kind=kind,steps=steps,checks=checks,acceptance=covers,rationale='完成条件の入力と結果を照合する')
  checks=[dict(op='text_equals',selector='#result',value='記録を保存しました'),dict(op='visible',selector='#result')]
  return dict(audience_quotes=['個人講師が使う出欠管理','名簿と出欠を簡単に整理'],result_selector='#result',scenarios=[
   scenario('workflow',[dict(op='fill',selector='#name',value='青木'),dict(op='click',selector='#save')],checks,[0]),
   scenario('variant',[dict(op='fill',selector='#name',value='佐藤'),dict(op='click',selector='#save')],checks,[1]),
   scenario('reload',[dict(op='reload')],[dict(op='visible',selector='#result'),dict(op='visible',selector='#save')],[2]),
   scenario('roundtrip',[dict(op='download_json',selector='#backup'),dict(op='fill',selector='#name',value='変更'),dict(op='click',selector='#save'),dict(op='cancel_restore',selector='#cancel'),dict(op='download_csv',selector='#csv',contains=['青木','佐藤']),dict(op='restore_file',selector='#restore')],checks,[0,1,2]),
   scenario('invalid',[dict(op='restore_invalid',selector='#restore'),dict(op='fill',selector='#name',value=''),dict(op='click',selector='#save')],[dict(op='text_contains',selector='#error',value='入力'),dict(op='visible',selector='#error')],[0,1,2])])

 def test_qa_plan_semantic_errors_are_repaired_before_retesting_same_app(self):
  name='テスト計画を同じ運転中に直す';spec=self.complete_spec();app.store_product_spec(name,spec)
  with patch.object(app,'ai') as model:
   with self.assertRaises(app.AutoQAPlanError) as err:
    app.make_qa_plan(name,'<html><body><h1>個人講師が使う出欠管理</h1></body></html>',dict(app.DEFAULT))
  model.assert_not_called();self.assertIn('画面を改善',str(err.exception))
  page='<html><body><h1>個人講師が使う出欠管理</h1><p>オンライン授業の講師が受講者ごとの出欠を記録します。</p><p>名簿を登録して授業日を選び、出欠を入力すると集計されます。</p><input id="name"><button id="save">保存</button><div id="result"></div></body></html>'
  with patch.object(app,'ai',return_value='{"scenarios":[]}') as model:
   with self.assertRaises(app.AutoQAPlanError) as err:app.make_qa_plan(name,page,dict(app.DEFAULT))
  self.assertEqual(model.call_count,1);self.assertIn('5件',str(err.exception))

 def test_repeated_qa_plan_failure_is_bounded_then_returns_to_product_repair(self):
  name='検証計画を無限に繰り返さない';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  failure=app.AutoQAPlanError('期待結果を仕様から確認できません')
  with patch.object(app,'ensure_autoqa_environment'),patch.object(app,'ensure_competitive_brief',return_value={'design_patterns':[]}),patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'make_qa_plan',side_effect=failure),patch.object(app,'event'):
   first=app.automated_product_qa(1,name,'<html><body><h1>出欠記録</h1></body></html>',dict(app.DEFAULT))
   second=app.automated_product_qa(1,name,'<html><body><h1>出欠記録</h1></body></html>',dict(app.DEFAULT))
  self.assertEqual(first[2],'自動検証の再試行待ち')
  self.assertEqual(second[2],'自動検証で要修正')
  self.assertNotIn(second[2],app.AUTO_QA_RETRY_STAGES)
  self.assertIn('次の運転で製品側の改善に戻します',second[1])

 def test_browser_failure_is_repaired_and_retested_in_the_same_development_cycle(self):
  name='実ブラウザ失敗から即時修正';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  first='<!doctype html><html><body><h1>改善前の候補</h1></body></html>'
  second='<!doctype html><html><body><h1>修正後の候補</h1></body></html>'
  with patch.object(app,'product_source',return_value=''),patch.object(app,'build',side_effect=[(first,'コード検査合格',True),(second,'修正・再検査合格',True)]) as build,patch.object(app,'automated_product_qa',side_effect=[(False,'保存操作で例外が発生','自動検証で要修正'),(True,'実操作・画面検査合格','のぼるさん確認待ち')]) as qa,patch.object(app,'event'):
   app.quality_development_cycle(job,dict(app.DEFAULT))
  self.assertEqual(build.call_count,2);self.assertEqual(qa.call_count,2)
  self.assertEqual(build.call_args_list[1].kwargs['existing_page'],first)
  self.assertIn('保存操作で例外が発生',build.call_args_list[1].args[3])
  self.assertEqual(app.query('SELECT stage FROM venture_product_development WHERE idea=?',(name,))[0]['stage'],'のぼるさん確認待ち')

 def test_environment_failure_keeps_the_same_product_without_spurious_rebuild(self):
  name='検証環境障害で製品を改変しない';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  page='<!doctype html><html><body><h1>検査対象の候補</h1></body></html>'
  with patch.object(app,'product_source',return_value=''),patch.object(app,'build',return_value=(page,'コード検査合格',True)) as build,patch.object(app,'automated_product_qa',return_value=(False,'Playwrightの準備待ち','検証環境の準備待ち')) as qa,patch.object(app,'event'):
   app.quality_development_cycle(job,dict(app.DEFAULT))
  self.assertEqual(build.call_count,1);self.assertEqual(qa.call_count,1)
  self.assertEqual(app.query('SELECT stage FROM venture_product_development WHERE idea=?',(name,))[0]['stage'],'検証環境の準備待ち')

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
   saved=app.ensure_product_spec('不足が直らない設計',dict(app.DEFAULT))
  # Bounded: max_attempts=1 plus the schema slot in ai_json = 2 calls; the inadequate design is neither saved nor padded.
  self.assertEqual(model.call_count,2);self.assertIn('前回の検査で次の不足',model.call_args.args[0]);self.assertEqual(saved['requirements_method'],'requirements_compiler_fallback')
  self.assertNotEqual(saved['must_have'],bad['must_have']);self.assertIn('requirements_recovery_reason',saved)
  self.assertFalse(app.candidate_production_acceptance('不足が直らない設計'))
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
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'ensure_implementation_plan',return_value={'features':[]}),patch.object(app,'incremental_product_repair',side_effect=lambda *a,**k:(a[2].replace('existing-function;','improved-function;',1), '部品サイズの修正')) as repair,patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',return_value=(True,'簡易検査合格')),patch.object(app,'review_connected_layout',side_effect=[ValueError('1280pxの接続待ち画面に改善が必要: smallControls inputValue calculate'),(True,'画面検査: 合格（API実動作は別）')]),patch.object(app,'ai',return_value='<html><body>'+('regenerated-function;'*100)+'</body></html>') as model,patch.object(app,'event'):
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=2),'操作部品の改善',existing_page=source,allow_partial=True)
  # Current contract (05551a2): one local repair, then the same build regenerates with the exact layout failure.
  self.assertEqual(repair.call_count,1);self.assertEqual(model.call_count,1);self.assertIn('smallControls',model.call_args.args[0]);self.assertIn('画面検査: 合格',detail)
  self.assertFalse(ready);self.assertFalse(app.candidate_production_acceptance(name));self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def comparison_fixture(self,name):
  baseline.FrameworkTests.add(self,name);sources,patterns=baseline.DesignEvidenceTests.fixture(self)
  comparisons=[dict(source_url=u,source_quote=r['text'],relevance='利用者の予定と結果を同じ作業で整理する方法です。',comparison='同じ入力の保存と再表示の手順を比較し不明点を区別する。') for u,r in sources.items()]
  item=dict(comparisons=comparisons,target_task='具体的な予定を入力して保存し結果を比較する。',proposed_advantage='未確認の予定を区別し入力の迷いを減らす仮説。',own_acceptance_index=0,benchmark={k:'同じ入力を使って完了率と時間と迷いを測定する。' for k in ('scenario','measure','continue_if','reconsider_if')},design_patterns=patterns)
  long='。'.join(['公式資料に記載された予定の入力と保存、集計、CSV出力、共有の手順を確認する説明']*3)
  references=[dict(r,text=long+u,status='本文取得',url=u,checked_at=app.now(),content_sha='a'*64) for u,r in sources.items()]
  return item,references
 def test_mismatched_competitor_quote_is_repaired_using_retrieved_text(self):
  import copy
  name='引用の不一致を直す比較';valid,refs=self.comparison_fixture(name)
  with patch.object(app,'competitive_reference_candidates',return_value=[r['url'] for r in refs]),patch.object(app,'read_research_reference',side_effect=refs),patch.object(app,'ai') as model:
   brief=app.ensure_competitive_brief(name,dict(app.DEFAULT,competitive_visual_research=False))
  model.assert_not_called();self.assertTrue(app.competitive_design_ready(brief));self.assertFalse(brief['measured_advantage'])
  texts={r['url']:r['text'] for r in refs}
  for part in brief['comparisons']+brief['design_patterns']:self.assertIn(part['source_quote'],texts[part['source_url']])
 def test_persistent_invented_comparison_is_not_cached_as_valid(self):
  name='不一致が残る比較';bad,refs=self.comparison_fixture(name);refs[1]=dict(refs[1],text='短い本文')
  with patch.object(app,'competitive_reference_candidates',return_value=[r['url'] for r in refs]),patch.object(app,'read_research_reference',side_effect=refs),patch.object(app,'ai') as model:
   with self.assertRaises(app.AutoQAEnvironmentError):app.ensure_competitive_brief(name,dict(app.DEFAULT,competitive_visual_research=False))
  model.assert_not_called();self.assertIsNone(app.competitive_context(name)['brief'])

 def test_invalid_edit_anchor_is_repaired_against_same_original_code(self):
  name='置換元の修正';baseline.FrameworkTests.add(self,name)
  source='<html><body><div id="value">original-value</div>'+('preserve-existing;'*100)+'</body></html>'
  bad={'reason':'該当しない置換案','edits':[{'old':'missing-original-value','new':'new-value'}]}
  valid={'reason':'一致する置換元に修正','edits':[{'old':'original-value','new':'improved-value'}]}
  with patch.object(app,'ai',return_value=json.dumps(bad)) as model:
   with self.assertRaises(app.AutoQAPlanError) as err:app.incremental_product_repair(1,name,source,'JavaScriptエラーを修正',dict(app.DEFAULT))
  self.assertEqual(model.call_count,1);self.assertIn('一致数: 0',str(err.exception));self.assertIn('original-value',model.call_args.args[0])
  with patch.object(app,'ai',return_value=json.dumps(valid)):
   page,reason=app.incremental_product_repair(1,name,source,'JavaScriptエラーを修正',dict(app.DEFAULT))
  self.assertEqual(page,source.replace('original-value','improved-value'));self.assertNotIn('missing-original-value',page)
 def test_unresolved_connected_work_does_not_log_successful_improvement(self):
  name='改善未完了の表示';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  app.store_product_spec(name,dict(app.get_product_spec(name),delivery_mode='connected',dependencies=['共有サーバー']))
  job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中',''))
  with patch.object(app,'build',return_value=('draft','JavaScriptエラー: Unexpected token .',False)):
   app.quality_development_cycle(job,dict(app.DEFAULT))
  history=app.query('SELECT details FROM agent_jobs WHERE id=?',(job,))[0]['details'];self.assertIn('改善は未完了',history);self.assertNotIn('画面・独立機能を改善。',history)

 def stub_fixture(self):
  return (Path(__file__).parent/'fixtures'/'legacy_customer_stub.html').read_text()
 def test_actual_uploaded_legacy_stub_is_not_a_basis_for_incremental_work(self):
  name='顧客エンゲージメント管理';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  app.store_product_spec(name,dict(app.get_product_spec(name),delivery_mode='connected',dependencies=['顧客データ共有']))
  old=self.stub_fixture();self.assertTrue(app.legacy_placeholder_reason(name,old))
  old_path=self.root/'old.html';old_path.write_text(old)
  replacement='<!doctype html><html><body><h1>顧客の対応履歴を記録する</h1><input id="customer"><button>記録を保存</button></body></html>'
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'ensure_implementation_plan',return_value={'features':[]}),patch.object(app,'ai',return_value=replacement) as model,patch.object(app,'incremental_product_repair') as incremental,patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',return_value=(True,'簡易検査')),patch.object(app,'review_connected_layout',return_value=(True,'画面検査: 合格（接続機能は未確認）')),patch.object(app,'event') as events:
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=1),'顧客対応を記録する',existing_page=old,allow_partial=True)
  incremental.assert_not_called();self.assertEqual(page,app.apply_generated_layout_safety(replacement));self.assertGreaterEqual(model.call_count,1)
  self.assertEqual(old_path.read_text(),old);self.assertFalse(ready);self.assertFalse(app.candidate_production_acceptance(name))
  self.assertTrue(any('旧版を保持' in str(call) for call in events.call_args_list))
 def test_explicit_doubling_tool_is_not_automatically_rebuilt(self):
  name='二倍計算の練習';baseline.FrameworkTests.add(self,name)
  app.store_product_spec(name,dict(app.get_product_spec(name),requested_outcome='数を2倍する計算を練習して結果を保存する'))
  self.assertEqual(app.legacy_placeholder_reason(name,self.stub_fixture()),'')
 def test_regenerating_the_same_stub_is_rejected_without_claiming_completion(self):
  name='顧客対応の整理';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  app.store_product_spec(name,dict(app.get_product_spec(name),delivery_mode='connected',dependencies=['顧客データ共有']))
  old=self.stub_fixture()
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'ensure_implementation_plan',return_value={'features':[]}),patch.object(app,'ai',return_value=old) as model,patch.object(app,'validate_html',return_value=[]),patch.object(app,'event'):
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=2),'顧客対応を整理する',existing_page=old,allow_partial=True)
  self.assertFalse(ready);self.assertFalse(app.candidate_production_acceptance(name));self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
  saved=[r['validation'] for r in app.query("SELECT validation FROM agent_assets WHERE idea=?",(name,))]
  self.assertTrue(any('中心機能がない' in v for v in saved),saved)

 def test_reference_ids_resolve_only_to_actual_retrieved_quotes(self):
  item,refs=self.comparison_fixture('参照IDから引用を取得する比較')
  catalog,lookup=app.comparison_reference_catalog(refs)
  for group in ('comparisons','design_patterns'):
   for part,reference in zip(item[group],catalog):
    part.pop('source_quote',None);part['source_ref']=reference['excerpts'][0]['id']
  resolved=app.resolve_comparison_references(item,lookup)
  for part in resolved['comparisons']:
   self.assertEqual(part['source_quote'],lookup[part['source_ref']]['text'])
  item['comparisons'][0]['source_ref']='invented-id'
  with self.assertRaises(app.AutoQAPlanError):app.resolve_comparison_references(item,lookup)
 def test_repeated_patch_failure_switches_strategy_without_destroying_source(self):
  name='部分修正の方式を切り替える';baseline.FrameworkTests.add(self,name);app.execute('UPDATE autonomous_control SET enabled=1')
  app.store_product_spec(name,dict(app.get_product_spec(name),delivery_mode='connected',dependencies=['共有サーバー']))
  source='<html><body>'+('keep-working;'*100)+'</body></html>';fresh='<html><body><h1>新しい具体的な作業画面</h1></body></html>'
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'ensure_implementation_plan',return_value={'features':[]}),patch.object(app,'incremental_product_repair',side_effect=ValueError('oldが一致しない')) as repair,patch.object(app,'ai',return_value=fresh) as model,patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',return_value=(True,'簡易検査')),patch.object(app,'review_connected_layout',return_value=(True,'画面検査: 合格（機能未確認）')),patch.object(app,'event'):
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=3),'作業機能を改善',existing_page=source,allow_partial=True)
  self.assertEqual(repair.call_count,1);self.assertEqual(model.call_count,1);self.assertEqual(page,app.apply_generated_layout_safety(fresh));self.assertFalse(ready)
 def test_numeric_smoke_values_respect_limits_and_steps(self):
  self.assertEqual(app.smoke_number_value('1','5',None,1),'1');self.assertEqual(app.smoke_number_value('1','5',None,2),'5')
  self.assertEqual(app.smoke_number_value('2','10','3',2),'8')
  self.assertNotEqual(app.smoke_number_value(None,None,None,1),app.smoke_number_value(None,None,None,2))

if __name__=='__main__':unittest.main()
