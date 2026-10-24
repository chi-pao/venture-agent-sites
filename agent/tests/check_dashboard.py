import os,tempfile,importlib.util,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
with tempfile.TemporaryDirectory() as directory:
 os.environ['VENTURE_DATA_HOME']=directory
 source=Path(os.environ.get('VENTURE_TEST_SOURCE') or Path(__file__).resolve().parents[1]/'venture_agent_integrated.py')
 spec=importlib.util.spec_from_file_location('quick_preview_setup',source);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app);app.init()
 for name in ['試作A','試作B']:
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  page=Path(directory)/(name+'.html');page.write_text('<!doctype html><html lang="ja"><head><title>'+name+'</title></head><body><h1>'+name+'の最新保存画面</h1><input id="name"><button>テスト</button></body></html>')
  app.execute('INSERT INTO agent_assets(idea,kind,path,validation,created) VALUES(?,?,?,?,?)',(name,'品質改善候補HTML',str(page),'未検証',app.now()))
  app.product_development_state(name,'修正中','画面を改善中',1)
 for name in ['友人間旅行計画アプリ','検索連携試作','中止試作']:
  app.execute('INSERT INTO autonomous_ideas(name,attempts,created,updated) VALUES(?,1,?,?)',(name,app.now(),app.now()))
  app.store_product_spec(name,dict(audience='旅行者',requested_outcome='検索して旅程を保存する',differentiation='休憩を入れる',workflow=['検索','計画','保存'],must_have=['検索','計画','保存'],acceptance=['検索結果','計画結果','保存結果'],delivery_mode='connected',dependencies=['場所検索API','共同編集サーバー']))
 app.set_owner_decision('中止試作','中止','検証後に追加開発を止める判断')
 app.record_connection_followup('検索連携試作','実データで動作確認済み','次は実際の利用者に操作してもらい反応を確認する','テスト用の接続確認記録。実際の検索と保存の結果を確認したものとする')
 with patch.object(urllib.request,'urlopen',side_effect=urllib.error.URLError('offline UI fixture')):
  at=AppTest.from_file(str(source),default_timeout=40).run()
  assert not at.exception,[x.message for x in at.exception]
  assert any('2026.10.24.11' in x.value for x in at.caption)
  assert not at.tabs
  api=next(x.value for x in at.dataframe if '対象アプリ' in x.value.columns)
  assert set(api['対象アプリ'])=={'友人間旅行計画アプリ','検索連携試作'},api
  assert not any(x.label=='実行履歴と成果物' for x in at.tabs)
  archived=next(x.value for x in at.dataframe if '再開に必要なこと' in x.value.columns)
  assert archived.iloc[0]['アプリ']=='中止試作'
  assert '追加開発を止める判断' in archived.iloc[0]['理由']
  assert not any(x.label=='Ollamaモデル' for x in at.text_input)
  columns=list(at.dataframe[0].value.columns)
  assert all(x in columns for x in ['アプリ','作っているもの','今の状況','継続判断','問題点','次の改善']),columns
  chooser=next(x for x in at.selectbox if x.key=='quick_app_preview_name')
  chooser.set_value('試作A').run();assert not at.exception,[x.message for x in at.exception]
  links=[x for x in at.get('link_button') if x.proto.label=='このアプリの今のページを開く'];assert len(links)==1
  url=links[0].proto.url;assert url.startswith('http://127.0.0.1:')
  next(x for x in at.checkbox if x.key=='show_advanced_dashboard').check().run()
  assert not at.exception,[x.message for x in at.exception]
  assert len(at.tabs)==8,len(at.tabs)
  next(x for x in at.checkbox if x.key=='show_advanced_settings').check().run()
  assert not at.exception,[x.message for x in at.exception]
  assert any(x.label=='Ollamaモデル' for x in at.text_input)
 with urllib.request.urlopen(url,timeout=5) as response:markup=response.read().decode()
 assert '試作Aの最新保存画面' in markup
 assert not app.query('SELECT * FROM venture_product_reviews')
 print('PASS: simple dashboard, stopped reasons, all API statuses, advanced controls, actual saved-page link, no release approval')
