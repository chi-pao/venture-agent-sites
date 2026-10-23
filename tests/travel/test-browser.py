from playwright.sync_api import sync_playwright
from pathlib import Path
import subprocess,json,tempfile
server=subprocess.Popen(['node','tests/travel/test-ui-server.mjs'],stdout=subprocess.PIPE,text=True)
try:
 url=server.stdout.readline().strip();assert url.startswith('http://127.0.0.1:'),url
 with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for width in (1280,390):
   context=browser.new_context(viewport={'width':width,'height':900});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.goto(url)
   page.locator('#query').fill('試験地点');page.locator('#searchButton').click();page.locator('#searchResults button').first.click()
   page.locator('#food').click();page.locator('#nearbyResults button').first.click();page.locator('#routes').click();page.wait_for_function('document.querySelector("#travelTime").textContent==="20分"')
   assert page.locator('#finish').inner_text()=='11:25';assert '未入力' in page.locator('#cost').inner_text()
   page.locator('#pace').select_option('slow');page.locator('#tripForm button').click();assert page.locator('#travelTime').inner_text()=='25分';assert page.locator('#finish').inner_text()=='11:30'
   page.reload();page.wait_for_function('document.querySelectorAll(".event").length===2');assert page.locator('#finish').inner_text()=='11:30'
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   page.locator('#itinerary').scroll_into_view_if_needed();page.screenshot(path=directory+'/'+str(width)+'.png')
   with page.expect_download() as dl:page.locator('#exportCsv').click()
   exported=Path(directory)/'plan.csv';dl.value.save_as(exported);assert '試験の食事B' in exported.read_text(encoding='utf-8-sig')
   with page.expect_download() as dl:page.locator('#backup').click()
   backup=Path(directory)/'plan.json';dl.value.save_as(backup)
   page.locator('#events input[type=number]').first.fill('30');page.locator('#events input[type=number]').first.press('Tab');assert page.locator('#finish').inner_text()=='11:15'
   page.locator('#restoreFile').set_input_files(str(backup));page.locator('#cancelRestore').click();assert page.locator('#finish').inner_text()=='11:15'
   page.locator('#restoreFile').set_input_files(str(backup));page.locator('#applyRestore').click();assert page.locator('#finish').inner_text()=='11:30'
   invalid=Path(directory)/'invalid.json';invalid.write_text('{"version":-1}');page.locator('#restoreFile').set_input_files(str(invalid));page.wait_for_function('document.querySelector("#message").textContent.includes("復元できません")');assert page.locator('#finish').inner_text()=='11:30'
   page.locator('#createShare').click();page.wait_for_function('!document.querySelector("#invites").hidden');edit=page.locator('#editInvite').input_value();view=page.locator('#viewInvite').input_value();assert '#trip=' in edit and '&key=' in edit
   other_context=browser.new_context();other=other_context.new_page();other.on('dialog',lambda d:d.accept());other.goto(edit);other.wait_for_function('document.querySelectorAll(".event").length===2');assert other.locator('#finish').inner_text()=='11:30'
   other.locator('#events input[type=number]').first.fill('60');other.locator('#events input[type=number]').first.press('Tab');other.locator('#saveShare').click();other.wait_for_function('document.querySelector("#message").textContent.includes("共有先へ変更を保存しました")')
   page.locator('#events input[type=number]').first.fill('30');page.locator('#events input[type=number]').first.press('Tab');page.locator('#saveShare').click();page.wait_for_function('document.querySelector("#message").textContent.includes("同行者が先に更新")');assert page.locator('#events input[type=number]').first.input_value()=='30'
   page.locator('#loadRemote').click();page.wait_for_function('document.querySelector("#message").textContent.includes("共有先の最新を取り込み")');assert page.locator('#events input[type=number]').first.input_value()=='60'
   viewer_context=browser.new_context();viewer=viewer_context.new_page();viewer.goto(view);viewer.wait_for_function('document.querySelector("#sharingState").textContent==="閲覧専用"');assert viewer.locator('#events input[type=number]').first.is_disabled();assert viewer.locator('#saveShare').is_hidden()
   assert not errors,errors;viewer_context.close();other_context.close();context.close()
  browser.close()
 print('PASS: desktop/mobile search-add-route, pace, reload, CSV, JSON restore/cancel/invalid, real SQLite sharing across browsers, version conflict preservation, read-only invite; provider fixtures only')
finally:
 server.terminate();server.wait(timeout=10)
