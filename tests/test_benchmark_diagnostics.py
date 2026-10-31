"""Model comparison browser check: real Chromium on the page shapes local models actually produce.

"ValueError: 2件の登録・件数表示が不一致" used to cover five different causes with no observed
values, and a correct page that rendered a moment later was failed by the checker itself.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('benchmark_diagnostics_app', ROOT / 'agent' / 'venture_agent_integrated.py')
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

GOOD = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>ひとり仕事の記録</title><style>*{box-sizing:border-box}body{font:16px sans-serif;margin:20px}main{max-width:740px;margin:auto}'
    'label{display:block;margin-top:12px}input,button{font:16px sans-serif;min-height:44px;padding:10px;width:100%;margin:6px 0}'
    'table{width:100%;table-layout:fixed}td,th{overflow-wrap:anywhere;padding:8px;border-bottom:1px solid #ccc}</style></head>'
    '<body><main><h1>ひとり仕事の記録</h1><p>個人で働く人が、今日の作業と期限を記録します。入力、追加、CSV保存の順に使えます。</p>'
    '<form id="form"><label for="taskName">タスク名</label><input id="taskName" required><label for="priority">優先度</label>'
    '<input id="priority" type="number" min="1" max="5" required><label for="dueDate">期限</label><input id="dueDate" type="date" required>'
    '<button id="addTask">追加</button></form><p>登録件数 <span id="taskCount">0</span></p><table><thead><tr><th>タスク名</th><th>優先度</th>'
    '<th>期限</th></tr></thead><tbody id="tasks"></tbody></table><button id="downloadCsv">CSVダウンロード</button></main><script>'
    "let tasks=JSON.parse(localStorage.getItem('benchmark_records')||'[]');"
    "function render(){const body=document.getElementById('tasks');body.replaceChildren();for(const task of tasks){const row=document.createElement('tr');"
    "for(const value of [task.name,task.priority,task.date]){const cell=document.createElement('td');cell.textContent=value;row.append(cell)}body.append(row)}"
    "document.getElementById('taskCount').textContent=tasks.length}"
    "document.getElementById('form').onsubmit=function(event){event.preventDefault();const name=document.getElementById('taskName').value.trim(),"
    "priority=document.getElementById('priority').value,date=document.getElementById('dueDate').value;"
    "if(!name||!date||Number(priority)<1||Number(priority)>5)return;tasks.push({name,priority,date});"
    "localStorage.setItem('benchmark_records',JSON.stringify(tasks));render()};"
    "document.getElementById('downloadCsv').onclick=function(){const content='\\ufeffタスク名,優先度,期限\\n'+tasks.map(x=>[x.name,x.priority,x.date].join(',')).join('\\n')+'\\n';"
    "const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));"
    "link.download='tasks.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)};render();</script></body></html>"
)


class BenchmarkPageDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_page(self, name, html):
        return app.execute_model_benchmark_page(html, Path(self.tmp.name) / name)

    def assertFailsWith(self, result, *parts):
        self.assertFalse(result['passed'], result)
        for part in parts:
            self.assertIn(part, result.get('error', ''))
        self.assertTrue(Path(result['failure_screenshot']).is_file(), result)
        self.assertNotIn(result['failure_screenshot'], result['screenshots'])

    def test_spec_page_passes_on_pc_and_mobile(self):
        result = self.run_page('good', GOOD)
        self.assertTrue(result['passed'], result.get('error'))
        self.assertEqual(len(result['checks']), 12)
        self.assertNotIn('failure_screenshot', result)

    def test_correct_page_that_renders_a_moment_later_is_not_failed(self):
        page = GOOD.replace("JSON.stringify(tasks));render()}", "JSON.stringify(tasks));setTimeout(render,300)}")
        self.assertNotEqual(page, GOOD)
        result = self.run_page('async', page)
        self.assertTrue(result['passed'], result.get('error'))

    def test_count_with_unit_is_still_a_spec_failure_and_says_what_was_shown(self):
        page = GOOD.replace("textContent=tasks.length}", "textContent=tasks.length+'件'}")
        self.assertFailsWith(self.run_page('unit', page), '件数表示', "'2件'", '一覧の行数: 2')

    def test_header_row_inside_tbody_reports_three_rows(self):
        page = GOOD.replace("body.replaceChildren();", "body.replaceChildren();body.insertAdjacentHTML('beforeend','<tr><th>タスク名</th></tr>');")
        self.assertFailsWith(self.run_page('header', page), '一覧の行数: 3')

    def test_double_registration_bug_reports_four_rows(self):
        page = GOOD.replace("render();</script>", "document.getElementById('addTask').addEventListener('click',()=>{const n=document.getElementById('taskName').value.trim();"
                            "if(n){tasks.push({name:n,priority:document.getElementById('priority').value,date:document.getElementById('dueDate').value});render();}});render();</script>")
        self.assertFailsWith(self.run_page('double', page), '一覧の行数: 4')

    def test_javascript_error_during_registration_is_reported(self):
        page = GOOD.replace("tasks.push({name,priority,date});", "tasks.push({name,priority,date});undefinedFunction();")
        self.assertFailsWith(self.run_page('jserror', page), 'JavaScriptエラー', 'undefinedFunction')

    def test_unprevented_form_submit_still_fails(self):
        result = self.run_page('submit', GOOD.replace('event.preventDefault();', ''))
        self.assertFalse(result['passed'])
        self.assertTrue(Path(result['failure_screenshot']).is_file())

    def test_reset_after_add_still_passes(self):
        result = self.run_page('reset', GOOD.replace("render()};", "render();this.reset()};"))
        self.assertTrue(result['passed'], result.get('error'))


if __name__ == '__main__':
    unittest.main()
