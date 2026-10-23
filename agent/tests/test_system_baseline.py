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

if __name__=='__main__':unittest.main()
