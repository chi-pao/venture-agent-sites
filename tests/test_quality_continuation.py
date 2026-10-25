from test_preview import app
import json
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch

def blueprint_fixture(name):
 spec=app.get_product_spec(name)
 return dict(policy=app.PRODUCT_BLUEPRINT_POLICY,scope_sha=app.product_scope_sha(name),competitive_checked=app.now(),
 user_scene='具体的な利用場面で家族の予定を分かりやすく整理する。',first_action='使いたい日付と対象者の条件を最初に入力する。',use_reason='未確認を区別しながら予定を比較して保存できる仮説。',visual_direction='対象者に合う配色と情報階層で入力と結果を区別する。',
 screen_sections=[dict(purpose='条件を分かりやすく入力する画面',action='日付と具体的な条件を入力する',result='入力した条件と妥当性が表示される') for _ in range(3)],
 core_flows=[dict(input='具体的な異なる予定条件を入力する',operation='条件を変更して結果を確認し保存する',expected_result='条件に応じた比較結果と保存記録を確認する',acceptance=list(range(len(spec['acceptance'])))) for _ in range(3)],
 adaptations=[dict(source_url=u,implementation='入力と結果を同じ画面で対応づける構成を実装する。',improvement='対象者の未確認項目と次の操作を分かりやすくする。') for u in ('https://nicody.jp/','https://wanderlog.com/')])

def implementation_plan_fixture(name):
 spec=app.get_product_spec(name);bp=blueprint_fixture(name)
 return dict(policy=app.IMPLEMENTATION_PLAN_POLICY,scope_sha=app.product_scope_sha(name),blueprint_checked=bp.get('checked'),
  architecture='入力フォーム、業務処理、集計結果、保存一覧を分離し、中心フローから順に作る。',
  data_flow='入力値を検証し、業務固有の計算後に結果を表示してからブラウザへ保存する。',
  offline_boundary='保存と計算はブラウザ内で動作し、経路や共有など外部機能は未接続と表示する。',
  features=[dict(acceptance_index=i,name='受入条件に対応する具体的な専用主機能操作'+str(i),user_action='具体値を入力して操作を実行し、画面の結果を見る',inputs='条件Aと条件Bの具体的な値を入力欄へ入力する',processing='入力条件に対応する業務固有ルールで結果を計算する',outputs='条件ごとに異なる結果と判断理由を表示する',persistence='保存後に再読込し同じ値と結果を再表示する',failure_behavior='不正値は保存せず入力欄の近くに修正方法を示す',prototype_mode='sample',prototype_behavior='サンプルデータを選び条件を変更して最後まで操作できる',connection_boundary='API接続後は外部から実データを取得する。未接続中は架空サンプルと明示する',test_cases=[dict(input='条件Aの具体値を入力して検証する',action='異なる条件Aを指定して計算ボタンを押す',expected='条件Aに対応する結果を表示する'),dict(input='条件Bの具体値を入力して検証する',action='異なる条件Bを指定して計算ボタンを押す',expected='条件Bと一致する処理結果を表示する')]) for i,_ in enumerate(spec['acceptance'])],
  screen_links=[dict(screen=s['purpose'],purpose=s['result'],next_action=s['action']) for s in bp['screen_sections']])

class ContinuationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
  app.DB=self.root/'test.db'; app.OUT=self.root/'out'; app.OUT.mkdir(); app.init()
  app.execute('UPDATE autonomous_control SET enabled=1')
  self.name='旅行テスト'; app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(self.name,app.now(),app.now()))
  self.spec=dict(audience='家族',requested_outcome='旅行の予定を比較保存する',differentiation='休憩を考慮',workflow=['入力','比較','保存'],must_have=['入力','計算','保存'],acceptance=['計算確認','保存確認','復元確認'],delivery_mode='browser_local',dependencies=[])
  app.store_product_spec(self.name,self.spec)
  self.research_patch=patch.object(app,'ensure_competitive_brief',return_value={});self.research_patch.start();self.addCleanup(self.research_patch.stop)
  self.blueprint_patch=patch.object(app,'ensure_product_blueprint',side_effect=lambda name,cfg,**kwargs:blueprint_fixture(name));self.blueprint_patch.start();self.addCleanup(self.blueprint_patch.stop)
  self.plan_patch=patch.object(app,'ensure_implementation_plan',side_effect=lambda name,cfg,blueprint=None:implementation_plan_fixture(name));self.plan_patch.start();self.addCleanup(self.plan_patch.stop)
  self.layout_patch=patch.object(app,'review_connected_layout',return_value=(True,'画面検査: 合格（API実動作・主機能の検証は別）'));self.layout_patch.start();self.addCleanup(self.layout_patch.stop)
 def tearDown(self): self.tmp.cleanup()
 def run_cycle(self,stage,attempts=4,connected=False):
  if connected: app.store_product_spec(self.name,dict(self.spec,delivery_mode='connected',dependencies=['経路API']))
  app.product_development_state(self.name,stage,'前回の問題',attempts)
  app.execute("UPDATE venture_product_development SET updated='2026-01-01T00:00:00+00:00'")
  page=self.root/'candidate.html';page.write_text('previous candidate')
  app.execute('INSERT INTO agent_assets(idea,kind,path,validation) VALUES(?,?,?,?)',(self.name,'品質改善候補HTML',str(page),'コード上のAI品質レビュー: 6項目の実装根拠あり' if stage=='のぼるさん確認待ち' else '不合格の理由'))
  with patch.object(app,'automated_product_qa',return_value=(True,'自動検証合格','のぼるさん確認待ち')),patch.object(app,'candidate_production_acceptance',return_value={'verified':True} if stage=='のぼるさん確認待ち' else None),patch.object(app,'build',return_value=('draft','検査合格',not connected)) as build,patch.object(app,'product_source',side_effect=AssertionError('must reuse candidate')),patch.object(app,'event'):
   app.quality_development_cycle(1,dict(app.DEFAULT))
  return build,app.query('SELECT * FROM venture_product_development')[0]
 def test_retry_after_three_uses_previous_candidate(self):
  build,row=self.run_cycle('修正上限・確認待ち')
  self.assertEqual(build.call_count,1);self.assertEqual(row['attempts'],5)
  self.assertEqual(build.call_args.kwargs['existing_page'],'previous candidate')
 def test_connected_continues_but_does_not_mark_complete(self):
  build,row=self.run_cycle('接続・実装待ち',connected=True)
  self.assertTrue(build.call_args.kwargs['allow_partial']);self.assertEqual(row['stage'],'画面改善中・接続未完了')
  self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def test_review_version_is_preserved(self):
  build,row=self.run_cycle('のぼるさん確認待ち')
  self.assertEqual(build.call_count,0);self.assertEqual(row['stage'],'のぼるさん確認待ち')
 def test_baseline_is_attached_without_removing_scope(self):
  spec=app.get_product_spec(self.name)
  self.assertEqual(spec['development_baseline'],app.PRODUCT_DEVELOPMENT_BASELINE)
  self.assertEqual(spec['must_have'],self.spec['must_have'])
 def test_travel_requirements_preserve_complete_shared_itinerary_scope(self):
  name='友人間旅行計画アプリ'
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  app.init_product_quality();spec=app.get_product_spec(name)
  self.assertEqual(spec['delivery_mode'],'connected')
  self.assertGreaterEqual(len(spec['acceptance']),7)
  self.assertIn('道中',spec['requested_outcome']);self.assertIn('食事',spec['requested_outcome']);self.assertIn('共同編集',spec['requested_outcome'])
  self.assertTrue(any('電車・バス' in x for x in spec['dependencies']))
  self.assertTrue(any('競合保護' in x for x in spec['acceptance']))
 def test_failed_candidate_switches_to_full_regeneration_instead_of_same_local_patch(self):
  failed='<!doctype html><html><body><h1>検査失敗した候補</h1></body></html>'
  repaired='<!doctype html><html><body><h1>完成条件から作り直した候補</h1></body></html>'
  spec=app.get_product_spec(self.name)
  with patch.object(app,'ensure_product_spec',return_value=spec),patch.object(app,'ai',side_effect=[failed,repaired]) as model,patch.object(app,'incremental_product_repair',side_effect=AssertionError('失敗後に同じ局所修正経路を使ってはいけません')) as local_repair,patch.object(app,'validate_html',return_value=[]),patch.object(app,'legacy_placeholder_reason',return_value=''),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',side_effect=[(False,'検査失敗'),(True,'再生成版の操作検査合格')]),patch.object(app,'review_generated_product',return_value=(True,'品質検査合格')),patch.object(app,'event'):
   page,detail,passed=app.build(1,self.name,dict(app.DEFAULT,max_revisions=3),'',allow_partial=False)
  self.assertTrue(passed);self.assertEqual(page,repaired);self.assertEqual(model.call_count,2);local_repair.assert_not_called()
  self.assertIn('検査失敗に対する自動回復',model.call_args_list[1].args[0])
  self.assertIn('別経路で完成条件からHTMLを作り直します',model.call_args_list[1].args[0])

 def test_partial_build_never_passes_release(self):
  app.store_product_spec(self.name,dict(self.spec,delivery_mode='connected',dependencies=['経路API']))
  with patch.object(app,'ensure_autoqa_environment'),patch.object(app,'ai',return_value='<!doctype html><html><body>接続未実装</body></html>') as model,patch.object(app,'validate_html',return_value=['未実装の痕跡']),patch.object(app,'browser_test',return_value=(True,'操作検査合格')),patch.object(app,'recent_failure_notes',return_value=''),patch.object(app,'event'):
   page,reason,passed=app.build(1,self.name,dict(app.DEFAULT),'',allow_partial=True)
  self.assertTrue(page);self.assertFalse(passed)
  self.assertIn('未実装の痕跡',reason)
  self.assertTrue(any('機能別の実装・テスト契約' in call.args[0] for call in model.call_args_list))
  self.assertTrue(any('API接続前の確認用試作' in call.args[0] and 'サンプルデータ' in call.args[0] for call in model.call_args_list))

 def test_builder_waits_for_feature_plan_instead_of_making_screen(self):
  with patch.object(app,'ensure_implementation_plan',side_effect=app.AutoQAPlanError('処理手順とテストが不足')),patch.object(app,'ai') as model,patch.object(app,'event'):
   page,reason,passed=app.build(1,self.name,dict(app.DEFAULT),'',allow_partial=True)
  self.assertEqual(page,'');self.assertFalse(passed)
  self.assertIn('機能設計待ち',reason)
  model.assert_not_called()
 def test_build_does_not_generate_before_research_and_blueprint_pass(self):
  with patch.object(app,'ensure_product_blueprint',side_effect=app.AutoQAPlanError('競合との同じ作業の比較が不十分です')),patch.object(app,'ai') as model,patch.object(app,'event'):
   page,reason,passed=app.build(1,self.name,dict(app.DEFAULT),'',allow_partial=True)
  self.assertEqual(page,'');self.assertFalse(passed)
  self.assertIn('比較・画面設計待ち',reason)
  model.assert_not_called()
 def test_blueprint_uses_deterministic_repair_after_one_invalid_model_response(self):
  self.blueprint_patch.stop()
  valid=blueprint_fixture(self.name)
  invalid=dict(valid,core_flows=[dict(valid['core_flows'][0],acceptance=[999])])
  urls=['https://nicody.jp/','https://wanderlog.com/']
  brief=dict(policy=app.COMPETITIVE_POLICY,
   sources=[dict(url=u,content_sha='a'*64) for u in urls],
   design_patterns=[dict(source_url=u,evidence_type='official_text',pattern='公式本文で確認した情報整理の説明を使います。',adapt='対象者の入力と結果を同じ画面に配置します。',improvement='対象者が比較結果を見失わないレイアウトにします。',acceptance='別の入力例を使い結果表示までを操作します。') for u in urls])
  with patch.object(app,'ensure_competitive_brief',return_value=brief),patch.object(app,'get_product_blueprint',return_value=None),patch.object(app,'ai',side_effect=[json.dumps(invalid,ensure_ascii=False),json.dumps(valid,ensure_ascii=False)]) as model:
   result=app.ensure_product_blueprint(self.name,dict(app.DEFAULT))
  self.assertEqual(model.call_count,1)
  self.assertEqual(result['design_method'],'requirements_compiler_fallback')
  self.assertTrue(app.validate_product_blueprint(result,app.get_product_spec(self.name),brief))
  self.assertGreaterEqual(len(result['core_flows']),3)

 def test_implementation_contract_covers_each_acceptance_with_distinct_cases(self):
  spec=app.get_product_spec(self.name);bp=blueprint_fixture(self.name);plan=implementation_plan_fixture(self.name)
  self.assertTrue(app.validate_implementation_plan(plan,spec,bp))
  missing=dict(plan,features=plan['features'][:-1])
  with self.assertRaisesRegex(app.AutoQAPlanError,'完成条件ごとの独立機能'):
   app.validate_implementation_plan(missing,spec,bp)
  weak=dict(plan,features=[dict(plan['features'][0],test_cases=[plan['features'][0]['test_cases'][0]]),*plan['features'][1:]])
  with self.assertRaisesRegex(app.AutoQAPlanError,'異なる入力を使う操作テスト'):
   app.validate_implementation_plan(weak,spec,bp)
  api_blocked=dict(plan,features=[dict(plan['features'][0],prototype_mode='requires_connection'),*plan['features'][1:]])
  with self.assertRaisesRegex(app.AutoQAPlanError,'ローカル動作または明示的なサンプル動作'):
   app.validate_implementation_plan(api_blocked,spec,bp)
  unlabeled=dict(plan,features=[dict(plan['features'][0],prototype_behavior='API接続が完了するまでは外部から実データを取得できません'),*plan['features'][1:]])
  with self.assertRaisesRegex(app.AutoQAPlanError,'サンプル・架空・デモ'):
   app.validate_implementation_plan(unlabeled,spec,bp)

 def test_implementation_plan_role_repairs_incomplete_coverage(self):
  self.plan_patch.stop()
  spec=app.get_product_spec(self.name);bp=blueprint_fixture(self.name);valid=implementation_plan_fixture(self.name)
  invalid=dict(valid,features=valid['features'][:-1])
  with patch.object(app,'ensure_product_blueprint',return_value=bp),patch.object(app,'get_implementation_plan',return_value=None),patch.object(app,'ai',side_effect=[json.dumps(invalid,ensure_ascii=False),json.dumps(valid,ensure_ascii=False)]) as model:
   result=app.ensure_implementation_plan(self.name,dict(app.DEFAULT),bp)
  self.assertEqual(model.call_count,2)
  self.assertEqual(len(result['features']),len(spec['acceptance']))

if __name__=='__main__':unittest.main()
