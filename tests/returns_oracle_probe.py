"""Independent count experiment against a saved real-generated page, not an acceptance gate."""
import hashlib
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(os.environ['VENTURE_LIVE_DATA_HOME']).resolve()
files=sorted(root.glob('outputs/sectors/**/02_builds/**/*.html'))
required=('id="return_item"','id="order_number"','id="saveRecord"','id="recordCount"')
pages=[p for p in files if all(x in p.read_text(encoding='utf-8') for x in required)]
if not pages:
    raise RuntimeError('保存された返品管理の実生成HTMLが見つかりません')
page_file=pages[-1]
proof={'source':str(page_file),'source_sha256':hashlib.sha256(page_file.read_bytes()).hexdigest(),'cases':[],'passed':False}
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            for width in (1280,390):
                context=browser.new_context(viewport={'width':width,'height':900},accept_downloads=True)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(page_file.as_uri(),wait_until='load');page.evaluate('localStorage.clear()');page.reload()
                # This independent oracle is limited to this explicit scenario:
                # save two distinct records, then reload; no application code is used to calculate the count.
                for i in (1,2):
                    page.locator('#return_item').fill(f'独立検証商品{i}')
                    page.locator('#order_number').fill(f'ORDER-{i:03d}')
                    page.locator('#response_deadline').fill('2035-12-31')
                    page.locator('#return_status').select_option('返送待ち')
                    page.locator('#refund_amount').fill(str(i*1000))
                    page.locator('#saveRecord').click()
                    actual=page.locator('#recordCount').inner_text().strip()
                    proof['cases'].append({'width':width,'operation':f'登録{i}件','expected':str(i),'actual':actual})
                    if actual!=str(i):raise AssertionError(f'{width}px 登録{i}件: expected={i} actual={actual}')
                page.reload();actual=page.locator('#recordCount').inner_text().strip()
                proof['cases'].append({'width':width,'operation':'再読込','expected':'2','actual':actual})
                if actual!='2':raise AssertionError(f'{width}px 再読込: expected=2 actual={actual}')
                page.screenshot(path=str(root/f'independent-count-{width}.png'),full_page=True)
                if errors:raise AssertionError('JavaScript: '+str(errors[:3]))
                context.close()
            proof['passed']=True
        finally:browser.close()
finally:
    (root/'independent-count-probe.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False))
