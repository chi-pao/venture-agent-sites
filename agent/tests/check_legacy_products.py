"""Real-browser regression checks for supplied broken examples, not finished products."""
from pathlib import Path
import importlib.util,os,re
from playwright.sync_api import sync_playwright
source=Path(os.environ.get('VENTURE_TEST_SOURCE') or Path(__file__).resolve().parents[1]/'venture_agent_integrated.py')
spec=importlib.util.spec_from_file_location('legacy_browser_check',source);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
fixtures=Path(__file__).parent/'fixtures'
customer=fixtures/'legacy_customer_stub.html';project=fixtures/'legacy_project_stub.html'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);context=browser.new_context(accept_downloads=True)
 context.route('**/*',lambda r:r.continue_() if r.request.url.startswith('file://') else r.abort())
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(customer.as_uri())
 for value,expected in [('12','結果: 24'),('87','結果: 174'),('文書作成 初級','結果: NaN')]:
  page.locator('#inputValue').fill(value);page.locator('button').click();assert page.locator('#result').inner_text()==expected
 page.locator('#inputValue').fill('特定の入力値');page.locator('button').click();assert any('constant' in x for x in errors),errors
 page.goto(project.as_uri());assert any('Unexpected token' in x for x in errors),errors
 browser.close()
passed,details=app.browser_test(customer.read_text());assert not passed and 'NaN' in details,details
passed,details=app.browser_test(project.read_text());assert not passed and 'JavaScript' in details,details
# Correct the known syntax error only in memory, to demonstrate the CSV runtime error.
repaired=re.sub(r'\n\s*<p>タスク名: \$\{taskName\}</p>[\s\S]*?\n\s*`;','',project.read_text(),count=1)
assert repaired!=project.read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(project.as_uri());errors.clear();page.set_content(repaired)
 page.locator('#taskName').fill('検証用の作業');page.locator('#priority').fill('3');page.locator('#dueDate').fill('2026-10-31');page.locator('button[type=submit]').click()
 assert '検証用の作業' in page.locator('#result').inner_text()
 page.locator('#downloadCsv').click();assert any('constant' in x for x in errors),errors
 browser.close()
# An in-memory control example must pass valid-form smoke inputs (priority 1..5 and required date).
control=repaired.replace('const csvContent =','let csvContent =')
passed,details=app.browser_test(control);assert passed,details
print('PASS: both supplied failures reproduced; customer NaN classified; project script/CSV errors found; valid bounded-number/date form passes smoke check')
