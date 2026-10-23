import importlib.util,os
from pathlib import Path
source=Path(os.environ.get('VENTURE_TEST_SOURCE') or Path(__file__).resolve().parents[1]/'venture_agent_integrated.py')
spec=importlib.util.spec_from_file_location('system_under_test',source)
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import tempfile,unittest,json

class FrameworkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=(app.DB,app.OUT)
  app.DB=self.root/'db';app.OUT=self.root/'out';app.OUT.mkdir();app.init()
 def tearDown(self):app.DB,app.OUT=self.old;self.tmp.cleanup()
 def add(self,name):
  item=dict(target_customer='小規模な利用者',customer_pain='整理に時間がかかる',differentiation='未確認を分けて比較できる',acquisition_plan='対象者のSNSで紹介',monetization='保存と追加機能に課金する仮説',helpfulness_score=4,differentiation_score=3,monetization_score=3)
  app.execute('INSERT INTO autonomous_ideas(name,attempts,rationale,phase,updated) VALUES(?,1,?,?,?)',(name,json.dumps(item,ensure_ascii=False),'育成中',app.now()))
  spec=dict(audience='小規模な利用者',requested_outcome='比較して保存する',differentiation='未確認を分ける',workflow=['入力','比較','保存'],must_have=['入力','比較','保存'],acceptance=['入力確認','比較確認','保存確認'],delivery_mode='browser_local',dependencies=[])
  app.store_product_spec(name,spec);return app.project_registry(name)
 def test_connection_needs_are_visible_and_stop_is_filtered(self):
  self.add('友人間旅行計画アプリ');app.init_product_quality()
  rows=app.connection_followup_rows();self.assertEqual(len(rows),1)
  self.assertTrue(rows[0]['travel']);self.assertIn('確認',rows[0]['status'])
  app.set_owner_decision('友人間旅行計画アプリ','中止','ユーザーが開発を中止する判断です')
  self.assertEqual(app.connection_followup_rows(),[])
 def test_connection_note_does_not_grant_quality_and_scope_change_requires_recheck(self):
  name='友人間旅行計画アプリ';self.add(name);app.init_product_quality()
  with self.assertRaises(ValueError):app.record_connection_followup(name,'実データで動作確認済み','実際の共有と検索を操作して確認します','設定した')
  app.record_connection_followup(name,'設定済み・実動作未確認','東京駅の検索と別端末での共同編集を実際に確認する','キーとD1の設定を保存しました。実検索はまだです。')
  self.assertEqual(app.connection_followup_rows()[0]['status'],'設定済み・実動作未確認')
  self.assertEqual(app.query("SELECT * FROM agent_settings WHERE key LIKE 'production_acceptance:%'"),[])
  app.request_product_changes(name,'道中の立寄り候補をもっと探しやすく改善してください')
  row=app.connection_followup_rows()[0];self.assertFalse(row['current']);self.assertNotEqual(row['status'],'実データで動作確認済み');self.assertIn('保存',row['evidence'])
 def test_unselected_generic_api_is_developer_work_not_user_wait(self):
  name='外部連携サービス';self.add(name);spec=app.get_product_spec(name)
  app.store_product_spec(name,dict(spec,delivery_mode='connected',dependencies=['外部検索API']))
  row=app.connection_followup_rows()[0]
  self.assertEqual(row['status'],'調査・実装中（開発側）');self.assertIn('まだユーザーの設定作業待ちではありません',row['next_action'])
 def test_specific_sector_and_user_override_survive_restart(self):
  row=self.add('家族旅行計画アプリ');self.assertEqual(row['sector'],'travel_lifestyle')
  app.set_project_sector(row['idea'],'family_health');app.init()
  after=app.project_registry(row['idea']);self.assertEqual(after['sector'],'family_health');self.assertEqual(row['project_id'],after['project_id'])
  with self.assertRaises(ValueError):app.set_project_sector(row['idea'],'../../outside')
 def test_old_assets_and_new_sector_outputs_remain_accessible(self):
  row=self.add('授業管理');old=app.OUT/'projects'/row['project_id']/'old.html';old.parent.mkdir(parents=True);old.write_text('old')
  app.execute('INSERT INTO agent_assets(idea,kind,path) VALUES(?,?,?)',(row['idea'],'試作品HTML',str(old)))
  new=app.save(1,row['idea'],'品質改善候補HTML','<html>new</html>','html')
  self.assertTrue(new.is_relative_to(app.OUT/'sectors'/'education'/'projects'/row['project_id']))
  self.assertEqual(old.read_text(),'old');self.assertEqual(app.query('SELECT path FROM agent_assets ORDER BY id')[0]['path'],str(old))
 def test_unchanged_evaluation_reused_new_feedback_immediately_invalidates(self):
  self.add('CSV照合');cfg=dict(app.DEFAULT)
  with patch.object(app,'evaluate_value',wraps=app.evaluate_value) as evaluate:
   first,hit=app.cached_value_review('CSV照合',cfg);self.assertFalse(hit)
   second,hit=app.cached_value_review('CSV照合',cfg);self.assertTrue(hit);self.assertEqual(first,second);self.assertEqual(evaluate.call_count,1)
   app.record_value_feedback('CSV照合',dict(sample_count=5,useful_users=4,source='検証用の利用者テスト',notes='架空の検証データ'))
   third,hit=app.cached_value_review('CSV照合',cfg);self.assertFalse(hit);self.assertEqual(evaluate.call_count,2);self.assertEqual(third['facts']['samples'],5)
 def test_day_and_requirements_changes_invalidate(self):
  self.add('会計業務');clock=datetime(2026,10,23,tzinfo=timezone.utc)
  with patch.object(app,'policy_clock',return_value=clock):app.cached_value_review('会計業務',app.DEFAULT)
  with patch.object(app,'policy_clock',return_value=clock+timedelta(days=1)):
   _,hit=app.cached_value_review('会計業務',app.DEFAULT);self.assertFalse(hit)
   app.request_product_changes('会計業務','入力をスマホで選択しやすくしてください')
   _,hit=app.cached_value_review('会計業務',app.DEFAULT);self.assertFalse(hit)
 def test_sector_knowledge_never_presents_other_sector_facts(self):
  for name,evidence in [('授業の管理','EDUCATION_ONLY'),('会計の管理','ACCOUNTING_ONLY')]:
   self.add(name)
   app.execute('INSERT INTO venture_value_learning VALUES(?,?,?,?,?,?,?,?)',(name,'時間短縮','key',.8,1,'育成継続',evidence,app.now()))
  context=app.value_learning_context('授業の管理');self.assertIn('EDUCATION_ONLY',context);self.assertNotIn('ACCOUNTING_ONLY',context)
  app.sync_framework_indexes();data=json.loads((app.OUT/'knowledge'/'education'/'measured-index.json').read_text())
  self.assertEqual([x['idea'] for x in data['examples']],['授業の管理'])
 def test_organization_preserves_scope_requests_and_quality_floor(self):
  self.add('授業管理');app.request_product_changes('授業管理','見た目・対象者・使い勝手を高めてください');scope=app.product_scope_sha('授業管理')
  app.set_project_sector('授業管理','other')
  self.assertEqual(scope,app.product_scope_sha('授業管理'));self.assertEqual(len(app.get_product_spec('授業管理')['user_change_requests']),1)
  prompt=app.quality_requirements_text('授業管理');self.assertIn('機能や品質条件を削らない',prompt);self.assertIn('スマホ',prompt)
 def test_no_measurements_no_learning_and_repeat_evidence_not_recounted(self):
  self.add('授業管理');result,_=app.cached_value_review('授業管理',app.DEFAULT);self.assertEqual(app.query('SELECT * FROM venture_value_learning'),[])
  app.record_value_feedback('授業管理',dict(sample_count=5,useful_users=4,source='検証用データ'))
  result,_=app.cached_value_review('授業管理',app.DEFAULT)
  app.execute("UPDATE venture_value_learning SET updated='unchanged-marker'")
  app.learn_from_value(result)
  self.assertEqual(app.query('SELECT updated FROM venture_value_learning')[0]['updated'],'unchanged-marker')



class DesignEvidenceTests(FrameworkTests):
 def fixture(self):
  urls=['https://nicody.jp/','https://wanderlog.com/']
  text='公式資料から取得した機能と利用方法の説明がここにあります。'
  sources={u:dict(text=text,content_sha='a'*64) for u in urls}
  patterns=[dict(source_url=u,source_quote=text,evidence_type='official_text',pattern='入力と結果をひとつにまとめた作業画面の構成です。',adapt='対象者の必要な項目に絞った入力画面を実装します。',improvement='対象者が迷う確認箇所を一つにそろえる改善をします。',acceptance='異なる入力で結果を比較し誤入力から戻れるか確認。') for u in urls]
  return sources,patterns
 def test_fabricated_or_repeated_design_evidence_is_rejected(self):
  sources,patterns=self.fixture()
  app.validate_competitive_design(dict(design_patterns=patterns),sources)
  patterns[0]['source_quote']='この説明は公式資料には存在しない作り話です。'
  with self.assertRaises(app.AutoQAPlanError):app.validate_competitive_design(dict(design_patterns=patterns),sources)
  sources,patterns=self.fixture();patterns[1]['source_url']=patterns[0]['source_url']
  with self.assertRaises(app.AutoQAPlanError):app.validate_competitive_design(dict(design_patterns=patterns),sources)
 def test_text_source_cannot_be_labelled_real_app_test(self):
  sources,patterns=self.fixture();patterns[0]['evidence_type']='tested_in_real_app'
  with self.assertRaises(app.AutoQAPlanError):app.validate_competitive_design(dict(design_patterns=patterns),sources)
 def test_work_time_uses_task_references_before_general_tools(self):
  self.add('在宅ワーク管理アプリ')
  urls=app.competitive_reference_candidates('在宅ワーク管理アプリ')
  self.assertIn('clockify.me',urls[0]);self.assertIn('toggl.com',urls[1])



class BlueprintTests(FrameworkTests):
 def fixture(self,name):
  spec=app.get_product_spec(name);urls=['https://nicody.jp/','https://wanderlog.com/']
  item=dict(user_scene='具体的な利用場面で予定と結果を一画面で整理したい人。',first_action='使いたい日付と対象者の条件を最初に入力する。',use_reason='未確認を区別しながら予定を比較して保存できる仮説。',visual_direction='対象者に合う配色と情報階層で入力と結果を区別する。',screen_sections=[dict(purpose='条件を分かりやすく入力する画面',action='日付と具体的な条件を入力する',result='入力した条件と妥当性が表示される') for _ in range(3)],core_flows=[dict(input='具体的な異なる予定条件を入力する',operation='条件を変更して結果を確認し保存する',expected_result='条件に応じた比較結果と保存記録を確認する',acceptance=[i]) for i in range(len(spec['acceptance']))],adaptations=[dict(source_url=u,implementation='入力と結果を同じ画面で対応づける構成を実装する。',improvement='対象者の未確認項目と次の操作を分かりやすくする。') for u in urls])
  brief=dict(policy=app.COMPETITIVE_POLICY,scope_sha=app.product_scope_sha(name),checked=app.now(),sources=[dict(url=u,content_sha='a'*64) for u in urls],design_patterns=[dict(source_url=u,evidence_type='official_text',pattern='入力と結果を一画面でそろえるための設計です。',adapt='利用者に合う項目をまとめた画面を実装します。',improvement='不要な入力を減らして結果を見やすく設計します。',acceptance='異なる条件を入力して結果が変化することを確認。') for u in urls])
  return item,brief
 def test_blueprint_covers_all_features_and_real_comparison_sources(self):
  name='用途テスト';self.add(name);item,brief=self.fixture(name)
  app.validate_product_blueprint(item,app.get_product_spec(name),brief)
  item['core_flows'][-1]['acceptance']=[0]
  with self.assertRaises(app.AutoQAPlanError):app.validate_product_blueprint(item,app.get_product_spec(name),brief)
  item,brief=self.fixture(name);item['adaptations'][0]['source_url']='https://invented.example/'
  with self.assertRaises(app.AutoQAPlanError):app.validate_product_blueprint(item,app.get_product_spec(name),brief)
 def test_blueprint_is_cached_and_invalidated_by_new_user_scope(self):
  name='用途テスト';self.add(name);item,brief=self.fixture(name)
  with patch.object(app,'ensure_competitive_brief',return_value=brief),patch.object(app,'ai',return_value=json.dumps(item)) as model:
   app.ensure_product_blueprint(name,dict(app.DEFAULT));app.ensure_product_blueprint(name,dict(app.DEFAULT))
   self.assertEqual(model.call_count,1)
  self.assertTrue(app.get_product_blueprint(name));self.assertIn('design_blueprint',json.loads(app.quality_requirements_text(name)))
  app.request_product_changes(name,'もっと利用者に合う新しい集計機能を追加してください')
  self.assertIsNone(app.get_product_blueprint(name))
 def test_connected_draft_with_bad_visuals_is_repaired_and_never_final_ready(self):
  app.execute('UPDATE autonomous_control SET enabled=1')
  name='用途テスト';self.add(name);spec=app.get_product_spec(name);app.store_product_spec(name,dict(spec,delivery_mode='connected',dependencies=['検索API']))
  source='<html><body>'+('existing-function;'*100)+'</body></html>'
  with patch.object(app,'ensure_product_blueprint',return_value={}),patch.object(app,'incremental_product_repair',side_effect=lambda *a,**k:(a[2].replace('existing-function;','improved-function;',1), '部分修正')) as repair,patch.object(app,'validate_html',return_value=[]),patch.object(app,'ensure_autoqa_environment'),patch.object(app,'browser_test',return_value=(True,'簡易検査合格')),patch.object(app,'review_connected_layout',side_effect=[(False,'画面検査: 要改善 / スマホで主操作が見えない'),(True,'画面検査: 合格（API実動作・主機能の検証は別）')]) as visual,patch.object(app,'event'):
   page,detail,ready=app.build(1,name,dict(app.DEFAULT,max_revisions=2),'画面の改善',existing_page=source,allow_partial=True)
  self.assertEqual(repair.call_count,2);self.assertEqual(visual.call_count,2);self.assertFalse(ready);self.assertIn('画面検査: 合格',detail)
  self.assertIsNone(app.candidate_production_acceptance(name));self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
 def test_connected_screen_fix_resumes_after_three_minutes(self):
  app.execute('UPDATE autonomous_control SET enabled=1')
  name='用途テスト';self.add(name);spec=app.get_product_spec(name);app.store_product_spec(name,dict(spec,delivery_mode='connected',dependencies=['検索API']))
  app.product_development_state(name,'画面改善中・接続未完了','画面に使い方が見えない',4)
  app.execute('UPDATE venture_product_development SET updated=?',((app.policy_clock()-app.timedelta(seconds=181)).isoformat(),))
  with patch.object(app,'build',return_value=('draft','画面の不足を修正中',False)) as build,patch.object(app,'product_source',return_value=''),patch.object(app,'event'):
   app.quality_development_cycle(1,dict(app.DEFAULT))
  self.assertEqual(build.call_count,1)
 def test_decision_material_uses_hypotheses_without_inventing_revenue(self):
  name='用途テスト';self.add(name);item,brief=self.fixture(name)
  material=app.owner_decision_material(name,dict(blueprint=item,competitive_brief=brief,content_sha='a'*64,scope_sha=app.product_scope_sha(name)))
  self.assertIn('未検証',material['validation']);self.assertIn('仮説',material['monetization_hypothesis']);self.assertNotIn('revenue',material)



class QuickPreviewTests(FrameworkTests):
 def asset(self,name,kind,text='<!doctype html><html><body>test page</body></html>'):
  path=self.root/(name+str(len(app.query('SELECT id FROM agent_assets')))+'.html');path.write_text(text)
  app.execute('INSERT INTO agent_assets(idea,kind,path,validation,created) VALUES(?,?,?,?,?)',(name,kind,str(path),'未検証',app.now()))
  return path
 def test_newest_page_includes_unverified_drafts_without_granting_approval(self):
  self.add('試作A');old=self.asset('試作A','品質改善候補HTML');new=self.asset('試作A','改善候補HTML')
  self.add('試作B');self.asset('試作B','試作品HTML')
  pages=app.latest_saved_app_pages();self.assertEqual(len(pages),2)
  self.assertEqual(next(p['path'] for p in pages if p['idea']=='試作A'),str(new))
  self.assertFalse(app.candidate_production_acceptance('試作A'));self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
  new.unlink();self.assertEqual(next(p['path'] for p in app.latest_saved_app_pages() if p['idea']=='試作A'),str(old))
 def test_stopped_pages_hidden_and_explicit_resume_restores_preview(self):
  name='休止試作';self.add(name);self.asset(name,'品質改善候補HTML')
  app.set_owner_decision(name,'中止','利用者の判断で制作を停止します')
  self.assertEqual(app.latest_saved_app_pages(),[])
  app.set_owner_decision(name,'継続','対象者を絞って再び制作を進めます')
  self.assertEqual(len(app.latest_saved_app_pages()),1)

if __name__=='__main__':unittest.main()
