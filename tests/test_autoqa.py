from test_quality_continuation import ContinuationTests,app,blueprint_fixture,implementation_plan_fixture
from unittest.mock import patch
from pathlib import Path
import json,hashlib,copy,io

def step(op,selector=None,value=None,**kw):
 d={'op':op,**kw}
 if selector:d['selector']=selector
 if value is not None:d['value']=value
 return d

def scenario(kind,steps,checks,acceptance):return dict(kind=kind,steps=steps,checks=checks,acceptance=acceptance)
def add_feature_cases(plan,acceptance_count):
 workflow=plan['scenarios'][0]
 plan['feature_cases']=[]
 for i in range(acceptance_count):
  steps=copy.deepcopy(workflow['steps']);checks=copy.deepcopy(workflow['checks'])
  for j in (0,1):
   case_steps=copy.deepcopy(steps);case_checks=copy.deepcopy(checks)
   if j:
    def vary(value):
     if isinstance(value,str):return value.replace('検証A','検証A2')
     if isinstance(value,list):return [vary(x) for x in value]
     if isinstance(value,dict):return {k:vary(v) for k,v in value.items()}
     return value
    case_steps=vary(case_steps);case_checks=vary(case_checks)
   plan['feature_cases'].append(dict(acceptance_index=i,case_index=j,steps=case_steps,checks=case_checks,rationale='共通の完全な操作フローを別入力で実行して完成条件を確認する。専用テストは共通シナリオで補う'))
 return plan
def text(sel,value):return step('text_equals',sel,value)
def count(sel,n):return step('count',sel,n)
def task(title,estimate):return [step('fill','#title',title),step('fill','#taskDate','2026-10-23'),step('fill','#estimate',str(estimate)),step('click','#taskForm button')]
def work_plan():
 return add_feature_cases(dict(audience_quotes=['在宅勤務・フリーランス向け。','開始・終了・休憩を入力'],result_selector='#planned',scenarios=[
 scenario('workflow',[step('fill','#day','2026-10-23'),step('fill','#start','09:00'),step('fill','#end','12:00'),step('fill','#breaks','30'),step('click','#dayForm button')]+task('検証A',180)+[step('select','#logTask',label='検証A / 2026-10-23'),step('fill','#logDate','2026-10-23'),step('fill','#minutes','45'),step('click','#logForm button'),step('select','#tasks select','完了',nth=0)],[text('#capacity','150分'),text('#planned','180分'),text('#actual','45分'),step('text_contains','#tasks','-135分')],[0,1]),
 scenario('variant',task('検証B',30),[text('#planned','210分'),step('text_contains','#balance','60分')],[0]),
 scenario('reload',[step('reload'),step('fill','#day','2026-10-23')],[text('#planned','210分'),text('#actual','45分')],[2]),
 scenario('roundtrip',[step('download_csv','#csv',contains=['検証A','180','45']),step('download_json','#backup')]+task('検証C',60)+[step('restore_file','#restoreButton'),step('cancel_restore','#cancelRestore'),step('restore_file','#restoreButton'),step('click','#applyRestore')],[text('#planned','210分'),count('#tasks .task',2)],[3]),
 scenario('invalid',[step('restore_invalid','#restoreButton'),step('fill','#start','13:00'),step('fill','#end','12:00'),step('click','#dayForm button')],[step('text_contains','#message','終了'),text('#planned','210分')],[4])]),5)
def person(name):return [step('fill','#personName',name),step('click','#personForm button')]
def attendance_plan():
 return add_feature_cases(dict(audience_quotes=['個人講師・少人数スクール向け。','名簿を登録し、授業ごとに出欠を記録。'],result_selector='#summary',scenarios=[
 scenario('workflow',person('検証A')+person('検証B')+[step('fill','#course','検証授業'),step('fill','#lessonDate','2026-10-23T10:00'),step('click','#sessionForm button'),step('select','#attendance select','遅刻',nth=0),step('select','#attendance select','欠席',nth=1)],[text('#summary tr:nth-child(1) td:last-child','100%'),text('#summary tr:nth-child(2) td:last-child','0%')],[0]),
 scenario('variant',[step('fill','#personName','検証C'),step('click','#personForm button'),step('select','#attendance select','出席',nth=1)],[text('#summary tr:nth-child(2) td:last-child','100%'),count('#people .person',3)],[0]),
 scenario('reload',[step('reload')],[text('#summary tr:nth-child(2) td:last-child','100%'),count('#people .person',3)],[1]),
 scenario('roundtrip',[step('download_csv','#csv',contains=['検証授業','検証A','遅刻']),step('download_json','#backup')]+person('検証D')+[step('restore_file','#restoreButton'),step('cancel_restore','#cancelRestore'),step('restore_file','#restoreButton'),step('click','#applyRestore')],[count('#people .person',3),text('#summary tr:nth-child(2) td:last-child','100%')],[2]),
 scenario('invalid',[step('restore_invalid','#restoreButton')]+person('検証A'),[step('text_contains','#message','同じ名前'),count('#people .person',3)],[3])]),4)

def design_brief(name):
 text='これは比較先の公式本文のテスト用取得内容です。'
 urls=['https://nicody.jp/','https://wanderlog.com/']
 spec=app.get_product_spec(name) or {}
 content_comparison=[dict(acceptance_index=i,required_feature=requirement,
  competitor_observations=[dict(source_url=u,source_quote=text,matched_terms=[],evidence_status='取得本文では未確認。未提供とは断定しない。') for u in urls],
  own_build_and_test='この完成条件を専用機能へ実装し、入力・結果・保存をブラウザーで検査します。') for i,requirement in enumerate(spec.get('acceptance',[]))]
 # Unit-test-only captures exercise the hash and viewport gate without claiming live competitor evidence.
 fixture_root=app.OUT/'test-competitor-captures';fixture_root.mkdir(parents=True,exist_ok=True)
 observations=[]
 for index,url in enumerate(urls):
  views={}
  from PIL import Image
  for label,width,height in (('desktop',1280,900),('mobile',390,844)):
   path=fixture_root/f'{index}-{label}.png';Image.new('RGB',(width,height),(35+index*30,90,160)).save(path,format='PNG');image=path.read_bytes()
   views[label]=dict(width=width,height=height,metrics=dict(viewportWidth=width,bodyTextLength=120,heading='テスト画面'),screenshot_path=str(path),screenshot_sha256=hashlib.sha256(image).hexdigest())
  observations.append(dict(source_url=url,capture_status='ok',views=views))
 return dict(policy=app.COMPETITIVE_POLICY,scope_sha=app.product_scope_sha(name),sources=[dict(url=u,content_sha='a'*64) for u in urls],visual_observations=observations,content_comparison=content_comparison,design_patterns=[dict(source_url=u,source_quote=text,evidence_type='official_text',pattern='同じ作業の入力から結果までを一画面で整理します。',adapt='対象者の予定入力と結果をまとめる構成を実装します。',improvement='不要な入力を減らし誤入力から復帰できる導線を設計。',acceptance='具体的な予定を入力して結果とエラーが見えるか確認。') for u in urls])

class AutomaticQATests(ContinuationTests):
 def install(self,index):
  product=json.loads(Path('product-rebuilds/product-candidates.json').read_text())['products'][index]
  app.store_product_spec(self.name,product['spec']);return Path('product-rebuilds/'+('attendance' if index==0 else 'workday')+'.html').read_text()
 def test_browser_workflow_actual_chromium(self):
  for index,plan in ((0,attendance_plan()),(1,work_plan())):
   with self.subTest(product=index):
    page=self.install(index);directory=self.root/str(index);directory.mkdir()
    app.validate_qa_plan(plan,app.get_product_spec(self.name))
    result=app.execute_browser_qa(self.name,page,plan,directory)
    self.assertEqual(len(result['scenarios']),10+4*len(app.get_product_spec(self.name)['acceptance']));self.assertEqual(len(result['screenshots']),4)
 def structured_candidate(self,name):
  spec=dict(audience='小規模事業者・個人利用者',requested_outcome='中心作業を整理し、入力から結果・保存までを一続きで行う',differentiation='専用操作の結果を入力条件に応じて表示する',workflow=['対象情報を入力する','用途別処理を実行して結果を確認する','保存・検索・出力する'],must_have=['必須入力の検証','用途別処理と結果','保存・再読込','CSVとJSONバックアップ'],acceptance=['中心作業の具体値を入力し用途別の結果を確認できる','異なる入力値で結果の変化を確認できる','登録後に再読込して同じ記録を確認できる','CSVとJSONバックアップを取得して復元できる'],delivery_mode='browser_local',dependencies=[])
  app.execute('INSERT OR REPLACE INTO autonomous_ideas(name,rationale,attempts,created,updated) VALUES(?,?,?,?,?)',(name,json.dumps({'customer_pain':'手作業の困りごと','target_customer':'小規模利用者'}),1,app.now(),app.now()))
  app.store_product_spec(name,spec)
  interface=app.deterministic_product_interface(name,spec)
  return spec,app.render_product_interface(name,interface,spec)
 def test_structured_planner_covers_registered_operations_without_model_calls(self):
  names=['オンライン授業参加管理アプリ','会議スケジューリング助手','英会話フレーズ練習ノート','業務タスク管理','FAQ回答ライブラリ','会計業務自動化アプリ','返品対応管理アプリ','顧客満足度調査ツール','費用比較メモ','予定整理ボード','業務記録管理アプリ','オンラインマインドフルネス教室','音楽理論クイズ練習帳','顧客依頼案件管理','在宅ワーク支援アプリ']
  with patch.object(app,'ai_json',side_effect=AssertionError('構造化画面のQA計画に生成AIを呼んではいけません')) as model:
   for name in names:
    with self.subTest(name=name):
     spec,page=self.structured_candidate(name)
     plan=app.make_qa_plan(name,page,dict(app.DEFAULT))
     app.validate_qa_plan(plan,spec)
     self.assertEqual(len(plan['scenarios']),5)
     self.assertEqual(len(plan['feature_cases']),2*len(spec['acceptance']))
  model.assert_not_called()
 def test_generated_structured_plans_run_in_real_chromium(self):
  for name in ('オンライン授業参加管理アプリ','会議スケジューリング助手','在宅ワーク支援アプリ'):
   with self.subTest(name=name):
    spec,page=self.structured_candidate(name);plan=app.make_qa_plan(name,page,dict(app.DEFAULT))
    directory=self.root/name.replace('/','_');directory.mkdir()
    result=app.execute_browser_qa(name,page,plan,directory)
    self.assertTrue(result['passed'])
    self.assertEqual(len(result['scenarios']),10+4*len(spec['acceptance']))
    self.assertEqual(len(result['screenshots']),4)
 def test_connected_layout_uses_real_desktop_mobile_images_without_release(self):
  page=self.install(1);self.layout_patch.stop()
  visual={key:dict(score=4,reason='実画面の画像入力接続を模擬し顧客評価や実機能の合格とは扱いません') for key in ('audience','design','readability','mobile','usefulness')}
  with patch.object(app,'ensure_autoqa_environment'),patch.object(app,'review_qa_images',return_value=visual) as image_model:
   passed,detail=app.review_connected_layout(1,self.name,page,dict(app.DEFAULT))
  self.assertTrue(passed);data=image_model.call_args.args[1];self.assertTrue(data['draft_only']);self.assertEqual(len(data['screenshots']),2)
  self.assertTrue(all(Path(path).is_file() for path in data['screenshots']));self.assertFalse(app.candidate_production_acceptance(self.name))
 def test_real_small_controls_failure_is_repaired_without_leaving_build_loop(self):
  self.layout_patch.stop()
  app.store_product_spec(self.name,dict(self.spec,delivery_mode='connected',dependencies=['共有サーバー']))
  source='<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>body{font:16px sans-serif}h1{font-size:28px}input,button{width:180px;height:20px;font:16px sans-serif}</style></head><body><h1>実践記録の確認ページ</h1><label for="inputValue">今日の記録</label><input id="inputValue"><button id="calculate">記録を確認する</button></body></html>'
  fixed=source.replace('height:20px','height:44px')
  visual={key:dict(score=4,reason='実画像の送信と検査経路を検証するためのモデル応答') for key in ('audience','design','readability','mobile','usefulness')}
  with patch.object(app,'incremental_product_repair',return_value=(source,'最初の修正')) as repair,patch.object(app,'ai',return_value=fixed) as model,patch.object(app,'legacy_placeholder_reason',return_value=''),patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',side_effect=[(False,'入力とボタンが小さい'),(True,'簡易検査合格')]),patch.object(app,'review_connected_layout',return_value=(True,'画面検査: 合格')),patch.object(app,'review_qa_images',return_value=visual):
   page,detail,ready=app.build(1,self.name,dict(app.DEFAULT,max_revisions=2),'画面を修正',existing_page=source.replace('実践記録','以前の記録'),allow_partial=True)
  self.assertEqual(repair.call_count,1);model.assert_called_once();self.assertIn('検査失敗に対する自動回復',model.call_args.args[0]);self.assertIn('画面検査: 合格',detail)
  self.assertIn('height:44px',page);self.assertFalse(ready);self.assertFalse(app.candidate_production_acceptance(self.name))
 def test_plan_forbidden_code_and_missing_coverage_rejected(self):
  self.install(1);plan=work_plan();plan['scenarios'][0]['steps'].append(step('evaluate','#title','alert(1)'))
  with self.assertRaises(app.AutoQAPlanError):app.validate_qa_plan(plan,app.get_product_spec(self.name))
  plan=work_plan();plan['scenarios'][-1]['acceptance']=[]
  with self.assertRaises(app.AutoQAPlanError):app.validate_qa_plan(plan,app.get_product_spec(self.name))
  plan=work_plan();plan['feature_cases'].pop()
  with self.assertRaises(app.AutoQAPlanError):app.validate_qa_plan(plan,app.get_product_spec(self.name))
  plan=work_plan();plan['feature_cases'][1]['steps']=copy.deepcopy(plan['feature_cases'][0]['steps'])
  with self.assertRaises(app.AutoQAPlanError):app.validate_qa_plan(plan,app.get_product_spec(self.name))
 def test_qa_planner_compiles_real_screen_copy_and_generates_tests_in_small_batches(self):
  full=work_plan();features=[c for c in full['feature_cases'] if c['acceptance_index']<3]
  base=dict(result_selector=full['result_selector'],scenarios=copy.deepcopy(full['scenarios']))
  base['scenarios'][0]['acceptance']=[0,1,2];base['scenarios'][1]['acceptance']=[0,1,2]
  base['scenarios'][2]['acceptance']=[2];base['scenarios'][3]['acceptance']=[2]
  base['scenarios'][4]['acceptance']=[0,2]
  batches=[dict(feature_cases=[c for c in features if c['acceptance_index'] in ids]) for ids in ([0,1],[2])]
  copy_page='<!doctype html><html><body><main><h1>家族旅行の予定を整理する</h1><p>家族で旅行の希望を入力できます。</p><p>出発地と日程を入力して候補を比べます。</p><script>secret phrase</script></main></body></html>'
  with patch.object(app,'get_implementation_plan',return_value=implementation_plan_fixture(self.name)),patch.object(app,'ai_json',side_effect=[base,*[b['feature_cases'] for b in batches],dict(valid=True,reasons=[])]) as model:
   result=app.make_qa_plan(self.name,copy_page,dict(app.DEFAULT))
  self.assertEqual(result['audience_quotes'],['家族旅行の予定を整理する','家族で旅行の希望を入力できます。'])
  self.assertEqual(len(result['feature_cases']),6)
  self.assertEqual(model.call_count,4)
  self.assertIn('共通品質検査',model.call_args_list[0].args[0])
  self.assertIn('小さなバッチ',model.call_args_list[1].args[0])
  self.assertIn('小さなバッチ',model.call_args_list[2].args[0])
 def test_real_browser_fail_cannot_grant_acceptance(self):
  page=self.install(1);plan=work_plan();plan['scenarios'][0]['checks'][0]['value']='999分'
  with patch.object(app,'ensure_competitive_brief',return_value=design_brief(self.name)),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'make_qa_plan',return_value=plan),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'自動検証で要修正');self.assertIn('999分',detail)
  self.assertIsNone(app.production_acceptance(self.name,hashlib.sha256(page.encode()).hexdigest()))
 def test_verified_browser_proof_and_image_mock_bound_to_exact_artifacts(self):
  page=self.install(1);visual={**{key:dict(score=4,reason='画像判定の接続だけを模擬し実際の画像品質を合格と主張しません') for key in ('audience','design','readability','mobile','usefulness')},'review_mode':'vision_model','competitor_reference_count':2,'competitor_reference_sources':['https://example.com/a','https://example.com/b']}
  with patch.object(app,'ensure_competitive_brief',return_value=design_brief(self.name)),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'make_qa_plan',return_value=work_plan()),patch.object(app,'review_qa_images',return_value=visual),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertTrue(passed);self.assertEqual(stage,'のぼるさん確認待ち')
  digest=hashlib.sha256(page.encode()).hexdigest();proof=app.production_acceptance(self.name,digest);self.assertTrue(proof)
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
  Path(next(iter(proof['screenshots']))).write_bytes(b'changed')
  self.assertIsNone(app.production_acceptance(self.name,digest))
 def test_programmatic_visual_metrics_cannot_grant_owner_review(self):
  page=self.install(1)
  visual={key:dict(score=4,reason='DOMやCSSの計測で画像AI判定を行っていない模擬結果です') for key in ('audience','design','readability','mobile','usefulness')}
  visual.update(review_mode='programmatic_browser_metrics',competitor_reference_count=2)
  with patch.object(app,'ensure_competitive_brief',return_value=design_brief(self.name)),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'make_qa_plan',return_value=work_plan()),patch.object(app,'execute_browser_qa',return_value=dict(scenarios=[],screenshots=[])),patch.object(app,'review_qa_images',return_value=visual),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'検証環境の準備待ち');self.assertIn('画像AI',detail)
  self.assertIsNone(app.production_acceptance(self.name,hashlib.sha256(page.encode()).hexdigest()))

 def test_environment_does_not_pass_or_trigger_product_repair(self):
  with patch.object(app,'ensure_autoqa_environment',side_effect=app.AutoQAEnvironmentError('画像モデル未準備')),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,'<html>draft</html>',dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'検証環境の準備待ち')
 def test_resume_old_manual_wait_without_rebuilding(self):
  build,row=self.run_cycle('制作側の実操作・見た目検証待ち')
  build.assert_not_called();self.assertEqual(row['stage'],'のぼるさん確認待ち')

 def test_image_low_score_returns_to_repair(self):
  page=self.install(1);visual={key:dict(score=3 if key=='design' else 4,reason='画面の余白や入力と結果の区分に改善が必要です') for key in ('audience','design','readability','mobile','usefulness')}
  browser=dict(scenarios=[],screenshots=[])
  with patch.object(app,'ensure_competitive_brief',return_value=design_brief(self.name)),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'make_qa_plan',return_value=work_plan()),patch.object(app,'execute_browser_qa',return_value=browser),patch.object(app,'review_qa_images',return_value=visual),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'自動検証で要修正');self.assertIn('余白',detail)
 def test_stop_during_qa_never_accepts(self):
  page=self.install(1);visual={key:dict(score=4,reason='画像応答のテスト用模擬値です。実画像を判定したとは主張しません') for key in ('audience','design','readability','mobile','usefulness')}
  def cancel(*args):app.execute('UPDATE autonomous_control SET enabled=0');return visual
  with patch.object(app,'ensure_competitive_brief',return_value=design_brief(self.name)),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'make_qa_plan',return_value=work_plan()),patch.object(app,'execute_browser_qa',return_value=dict(scenarios=[],screenshots=[])),patch.object(app,'review_qa_images',side_effect=cancel),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'検証環境の準備待ち')
 def test_vision_request_contains_compacted_real_image_bytes(self):
  from PIL import Image
  shot=self.root/'test.png';Image.new('RGB',(1400,900),'white').save(shot,format='PNG');calls=[]
  visual={key:dict(score=4,reason='画像APIの構造だけを模擬して確認しています') for key in ('audience','design','readability','mobile','usefulness')}
  def response(request,**kw):
   value=json.loads(request.data);calls.append(value)
   return io.BytesIO(json.dumps({'response':json.dumps(visual)}).encode())
  brief=design_brief(self.name)
  with patch.object(app.urllib.request,'urlopen',side_effect=response),patch.object(app,'competitive_context',return_value=dict(brief=brief)):
   got=app.review_qa_images(self.name,dict(screenshots=[str(shot)]*4,scenarios=[]),dict(app.DEFAULT))
  self.assertEqual(got,{**visual,'review_mode':'vision_model'});self.assertEqual(len(calls[-1]['images']),6)
  self.assertIn('最初の2枚は同業・代替サービスの実画面',calls[-1]['prompt'])
  reference=app.base64.b64decode(calls[-1]['images'][0])
  with Image.open(io.BytesIO(reference)) as image:self.assertEqual(image.size,(480,338))
  processed=app.base64.b64decode(calls[-1]['images'][-1])
  self.assertTrue(processed.startswith(bytes([255,216,255])))
  with Image.open(io.BytesIO(processed)) as image:self.assertEqual(image.size,(640,411))
  self.assertFalse(calls[-1]['stream'])
 def test_blueprint_compiles_product_specific_design_after_three_ai_repairs_fail(self):
  self.blueprint_patch.stop()
  with patch.object(app,'ensure_competitive_brief',return_value={}),patch.object(app,'get_product_blueprint',return_value=None),patch.object(app,'ai_json',side_effect=app.AutoQAPlanError('対象者の画面設計が不十分です')):
   result=app.ensure_product_blueprint(self.name,dict(app.DEFAULT),allow_unverified=True)
  self.assertEqual(result['design_method'],'requirements_compiler_fallback')
  self.assertIn(app.get_product_spec(self.name)['audience'],result['user_scene'])
  self.assertGreaterEqual(len(result['screen_sections']),3)
  covered={i for flow in result['core_flows'] for i in flow['acceptance']}
  self.assertEqual(covered,set(range(len(app.get_product_spec(self.name)['acceptance']))))
  self.assertGreaterEqual(len({x['source_url'] for x in result['adaptations']}),2)

 def test_competitive_quote_must_match_actual_reference(self):
  urls=app.competitive_context(self.name)['official_comparison_candidates'][:2]
  text=('公式ページの機能説明を取得したテスト用本文です。利用者が予定や作業を記録し、一覧で整理し、必要な情報を確認できる仕組みを紹介しています。'
        '条件の入力や検索、集計、共有など、掲載ページで確認できた内容だけを比較の根拠として扱います。' * 2)
  def reference(url):return dict(url=url,status='本文取得',text=text,checked_at=app.now(),content_sha='a'*64)
  # The evidence-backed compiler must avoid the model transcription bottleneck.
  self.research_patch.stop()
  with patch.object(app,'read_research_reference',side_effect=reference):
   result=app.ensure_competitive_brief(self.name,dict(app.DEFAULT))
  self.assertTrue(app.competitive_design_ready(result))
  self.assertGreaterEqual(len(result['comparisons']),2)
  matrix=result['content_comparison'];self.assertEqual(len(matrix),len(app.get_product_spec(self.name)['acceptance']))
  self.assertEqual({row['acceptance_index'] for row in matrix},set(range(len(matrix))))
  for row in matrix:
   self.assertTrue(all(obs['source_quote'] in text for obs in row['competitor_observations']))
   self.assertTrue(all('未提供とは断定しない' in obs['evidence_status'] for obs in row['competitor_observations'] if obs['evidence_status'].startswith('取得本文では未確認')))
  self.assertEqual(result['summary_method'],'official_text_rules')
  self.assertFalse(result['measured_advantage'])
  for part in result['design_patterns']:
   self.assertIn(part['source_quote'],text)
  broken=dict(result)
  broken['design_patterns']=[dict(part) for part in result['design_patterns']]
  broken['design_patterns'][0]['source_quote']='実際には取得していない競合の機能の説明です'
  with self.assertRaises(app.AutoQAPlanError):
   app.validate_competitive_design(broken,{url:reference(url) for url in urls})
 def test_text_only_cached_competitor_brief_retries_visual_capture(self):
  urls=['https://nicody.jp/','https://wanderlog.com/']
  text='公式ページの機能説明を取得したテスト用本文です。利用者が予定や作業を記録し、一覧で整理し、必要な情報を確認できる仕組みを紹介しています。'*2
  refs=[dict(url=u,status='本文取得',text=text,checked_at=app.now(),content_sha=('a' if i==0 else 'b')*64) for i,u in enumerate(urls)]
  cached=app.deterministic_competitive_brief(self.name,refs)
  self.assertFalse(app.competitive_visual_ready(cached))
  visual=design_brief(self.name)['visual_observations']
  context=dict(brief=cached,official_comparison_candidates=urls)
  self.research_patch.stop()
  with patch.object(app,'competitive_context',return_value=context),patch.object(app,'read_research_reference',side_effect=refs),patch.object(app,'capture_competitor_visual_references',return_value=visual) as capture:
   refreshed=app.ensure_competitive_brief(self.name,dict(app.DEFAULT))
  capture.assert_called_once()
  self.assertTrue(app.competitive_visual_ready(refreshed))
 def test_missing_or_single_design_source_never_passes(self):
  brief=design_brief(self.name);self.assertTrue(app.competitive_design_ready(brief))
  brief['design_patterns'][1]['source_url']=brief['design_patterns'][0]['source_url']
  self.assertFalse(app.competitive_design_ready(brief))
  self.assertFalse(app.competitive_design_ready(dict(policy=app.COMPETITIVE_POLICY)))
 def test_task_specific_reference_candidates(self):
  for name,domain in [('在宅ワーク管理アプリ','clockify.me'),('授業参加管理アプリ','classdojo.com'),('CSV照合アプリ','openrefine.org')]:
   self.assertTrue(any(domain in u for u in app.competitive_reference_candidates(name)))
 def test_unresearched_design_does_not_reach_owner_review(self):
  page=self.install(1);visual={key:dict(score=4,reason='試験用画像判定。実利用や競合比較の証明とは区別しています。') for key in ('audience','design','readability','mobile','usefulness')}
  result=dict(scenarios=[],screenshots=[])
  with patch.object(app,'ensure_competitive_brief',side_effect=app.AutoQAEnvironmentError('競合資料を取得できません')),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'ensure_product_blueprint',return_value=blueprint_fixture(self.name)),patch.object(app,'validate_product_blueprint',return_value=True),patch.object(app,'ensure_implementation_plan',return_value=implementation_plan_fixture(self.name)),patch.object(app,'validate_implementation_plan',return_value=True),patch.object(app,'make_qa_plan',return_value=work_plan()),patch.object(app,'execute_browser_qa',return_value=result) as browser,patch.object(app,'review_qa_images',return_value=visual),patch.object(app,'event'):
   passed,detail,stage=app.automated_product_qa(1,self.name,page,dict(app.DEFAULT))
  self.assertFalse(passed);self.assertEqual(stage,'自動検証の再試行待ち');browser.assert_called_once()
  self.assertIn('競合比較の根拠が未完了',detail)
  self.assertIsNone(app.candidate_production_acceptance(self.name))

 def test_competitor_failure_uses_internal_design_heuristics_but_never_claims_competitive_proof(self):
  self.blueprint_patch.stop()
  valid=blueprint_fixture(self.name)
  urls=['internal:quality-baseline/one-clear-workflow','internal:quality-baseline/recoverable-data-flow']
  valid['adaptations']=[dict(source_url=u,implementation='主作業の入力から結果までを一画面で実装します。',improvement='迷わず次の操作に進める配置を仮説として検証します。') for u in urls]
  with patch.object(app,'ensure_competitive_brief',side_effect=app.AutoQAEnvironmentError('比較先の本文が未取得')),patch.object(app,'get_product_blueprint',return_value=None),patch.object(app,'ai_json',return_value=valid):
   result=app.ensure_product_blueprint(self.name,dict(app.DEFAULT),allow_unverified=True)
  self.assertTrue(result['development_only']);self.assertIn('本文が未取得',result['research_gap'])
  bundle=app.development_design_reference_bundle(self.name,'未取得')
  self.assertFalse(app.competitive_design_ready(bundle))
  self.assertTrue(app.validate_product_blueprint(result,app.get_product_spec(self.name),bundle))
 def test_missing_competitor_sources_are_retry_not_demand_failure(self):
  self.research_patch.stop()
  with patch.object(app,'read_research_reference',return_value=dict(status='取得不足',text='')):
   with self.assertRaises(app.AutoQAEnvironmentError):app.ensure_competitive_brief(self.name,dict(app.DEFAULT))

if __name__=='__main__':import unittest;unittest.main()
