"""Check that layout failures identify the overflowing page element in Chromium."""
import os, tempfile, importlib.util
from pathlib import Path
from playwright.sync_api import sync_playwright

source=Path(os.environ.get('VENTURE_TEST_SOURCE') or Path(__file__).resolve().parents[1]/'venture_agent_integrated.py')
spec=importlib.util.spec_from_file_location('layout_diagnostics_check',source)
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    try:
        page=browser.new_page(viewport={'width':1280,'height':900})
        page.set_content('<main><h1>検査</h1><div id="fixed-wide" style="width:1500px">横にはみ出す要素</div></main>')
        result=page.evaluate(app.QA_LAYOUT_SCRIPT)
        assert result['overflow'] is True,result
        assert any(node['id']=='fixed-wide' and node['right']>1280 for node in result['overflowNodes']),result['overflowNodes']
        assert result['overflowNodes'][0]['width']>0
    finally:
        browser.close()
print('PASS: Chromium layout failure reports the exact overflowing element, its width and position')
