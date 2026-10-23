"""Exercise real Chromium comparison gates with fixture model output, not actual Ollama scores."""
import os,tempfile,importlib.util
from pathlib import Path
from unittest.mock import patch
GOOD=r'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ひとり仕事の記録</title><style>*{box-sizing:border-box}body{font:16px sans-serif;margin:20px}main{max-width:740px;margin:auto}label{display:block;margin-top:12px}input,button{font:16px sans-serif;min-height:44px;padding:10px;width:100%;margin:6px 0}table{width:100%;table-layout:fixed}td,th{overflow-wrap:anywhere;padding:8px;border-bottom:1px solid #ccc}</style></head><body><main><h1>ひとり仕事の記録</h1><p>個人で働く人が、今日の作業と期限を記録します。入力、追加、CSV保存の順に使えます。</p><form id="form"><label for="taskName">タスク名</label><input id="taskName" required><label for="priority">優先度</label><input id="priority" type="number" min="1" max="5" required><label for="dueDate">期限</label><input id="dueDate" type="date" required><button id="addTask">追加</button></form><p>登録件数 <span id="taskCount">0</span></p><table><thead><tr><th>タスク名</th><th>優先度</th><th>期限</th></tr></thead><tbody id="tasks"></tbody></table><button id="downloadCsv">CSVダウンロード</button></main><script>let tasks=JSON.parse(localStorage.getItem('benchmark_records')||'[]');function render(){const body=document.getElementById('tasks');body.replaceChildren();for(const task of tasks){const row=document.createElement('tr');for(const value of [task.name,task.priority,task.date]){const cell=document.createElement('td');cell.textContent=value;row.append(cell)}body.append(row)}document.getElementById('taskCount').textContent=tasks.length}document.getElementById('form').onsubmit=function(event){event.preventDefault();const name=document.getElementById('taskName').value.trim(),priority=document.getElementById('priority').value,date=document.getElementById('dueDate').value;if(!name||!date||Number(priority)<1||Number(priority)>5)return;tasks.push({name,priority,date});localStorage.setItem('benchmark_records',JSON.stringify(tasks));render()};document.getElementById('downloadCsv').onclick=function(){const content='\ufeffタスク名,優先度,期限\n'+tasks.map(x=>[x.name,x.priority,x.date].join(',')).join('\n')+'\n';const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([content.replaceAll('\\n','\n').replace('\\ufeff','\ufeff')],{type:'text/csv;charset=utf-8'}));link.download='tasks.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)};render();</script></body></html>'''
# Build a valid JS literal with actual JS newline escapes (the fixture remains readable above).
GOOD=GOOD.replace("'\\\\ufeff", "'\\ufeff").replace('\\\\n','\\n')
with tempfile.TemporaryDirectory() as root:
 os.environ['VENTURE_DATA_HOME']=root
 source=Path(os.environ.get('VENTURE_TEST_SOURCE') or Path(__file__).resolve().parents[1]/'venture_agent_integrated.py')
 spec=importlib.util.spec_from_file_location('benchmark_browser_check',source);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app);app.init()
 old='qwen2.5:7b';candidate='qwen2.5-coder:7b';installed={old:'old-fixture-digest',candidate:'candidate-fixture-digest'}
 bad=(Path(__file__).parent/'fixtures'/'legacy_project_stub.html').read_text()
 report=dict(policy=app.MODEL_BENCHMARK_POLICY,task_signature=app.benchmark_task_signature(),run_id='real-browser-fixtures',baseline=old,candidate=candidate,general_model=old,installed=installed,status='実行中',results=[])
 with patch.object(app,'ensure_autoqa_environment'),patch.object(app,'local_ai_request',side_effect=lambda prompt,cfg,tokens:GOOD if cfg['model']==candidate else bad),patch.object(app,'benchmark_model_digests',return_value=installed):
  app.model_benchmark_worker(app.config(),report,'test-browser-owner')
  saved=app.benchmark_state()
  assert saved['status']=='完了',saved
  assert app.benchmark_candidate_wins(saved),[(r['model'],r.get('error')) for r in saved['results']]
  assert 'code_model' not in app.config()
  assert app.query('SELECT * FROM venture_product_reviews')==[]
  app.adopt_benchmark_candidate(app.config());assert app.coding_config(app.config())['model']==candidate and app.config()['model']==old
  app.restore_previous_code_model();assert app.coding_config(app.config())['model']==old
 print('PASS: four fixture-model outputs tested in Chromium; full candidate checks, explicit scoped adoption, rollback and no product approval')
