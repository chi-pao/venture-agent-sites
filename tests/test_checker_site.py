"""The copied お買い得物件チェッカー (checker-site/) must still appraise in a real browser.

Runs the page from a local server, blocks every other host (ads, analytics, model-update
manifest) so the result depends only on the files in the repository, fills the built-in
example and checks that a reference price, a verdict and the price gap appear without
JavaScript errors. Also checks that every model file matches the size and sha256 that
models/catalog.json declares.
"""
import functools
import hashlib
import http.server
import json
from pathlib import Path
import re
import threading
import unittest

SITE = Path(__file__).resolve().parent.parent / 'checker-site'


@unittest.skipUnless((SITE / 'index.html').exists(), 'checker-site/ not mirrored yet')
class CheckerSiteTests(unittest.TestCase):
    def test_model_files_match_the_catalog(self):
        catalog = json.loads((SITE / 'models' / 'catalog.json').read_text(encoding='utf-8'))
        components = [c for group in ('models', 'previousModels') for m in catalog.get(group, {}).values() for c in m['components']]
        self.assertTrue(components)
        for component in components:
            data = (SITE / component['path']).read_bytes()
            self.assertEqual(len(data), int(component['bytes']), component['path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), component['sha256'], component['path'])
            if 'splitsPath' in component:
                splits = (SITE / component['splitsPath']).read_bytes()
                self.assertEqual(len(splits), int(component['splitsBytes']), component['splitsPath'])
                self.assertEqual(hashlib.sha256(splits).hexdigest(), component['splitsSha256'], component['splitsPath'])
        # Cloudflare Pages refuses files over 25 MiB; the catalog is loaded on every visit.
        for path in SITE.rglob('*'):
            if path.is_file():
                self.assertLess(path.stat().st_size, 25 * 1024 * 1024, path.name)
        self.assertLess((SITE / 'models' / 'catalog.json').stat().st_size, 3_000_000)

    def test_no_reference_to_the_old_host_remains(self):
        for path in SITE.rglob('*'):
            if path.suffix in ('.html', '.mjs', '.js', '.json', '.webmanifest', '.css'):
                text = path.read_text(encoding='utf-8', errors='replace')
                self.assertNotIn('rightharp65.chatgpt.site', text, path.name)
                self.assertNotIn('/cdn-cgi/', text, path.name)

    def test_picked_town_reaches_the_model_under_its_learned_name(self):
        # 「際波」 is listed for 宇部市; the transactions (and the model) call it 「大字際波」.
        aliases = json.loads((SITE / 'town-aliases.json').read_text(encoding='utf-8'))
        self.assertEqual(aliases['35202']['際波'], '大字際波')
        from playwright.sync_api import sync_playwright
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
        handler.log_message = lambda *a: None
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) else route.abort())
                page.goto(origin + '/')
                page.wait_for_function("document.querySelector('#prefecture').options.length > 40")
                page.check('input[name=type][value=used_house]')
                page.select_option('#prefecture', '山口県')
                page.select_option('#city', '35202')
                page.fill('#district', '際波')
                page.eval_on_selector('#price', "e => { e.value = '1780万円'; e.dispatchEvent(new Event('input', {bubbles: true})); }")
                page.select_option('#year', '2000')
                page.fill('#landArea', '238.02')
                page.fill('#buildingArea', '171.9')
                page.click('#estimate')
                page.wait_for_function("/\\d/.test((document.querySelector('#estimated-price')||{}).textContent||'')", timeout=90000)
                self.assertTrue(page.eval_on_selector('#unknown-categories', 'e => e.hidden'), page.inner_text('#unknown-categories'))
                self.assertIn('宇部市際波', page.inner_text('#result-location'))
                browser.close()
        finally:
            server.shutdown()

    def test_result_offers_follow_the_buy_or_sell_choice(self):
        import json as _json
        offers = _json.loads((SITE / 'offers.json').read_text(encoding='utf-8'))['offers']
        for o in offers:
            if o['enabled']:
                self.assertTrue(o['href'].startswith('https://'), o['id'])
        from playwright.sync_api import sync_playwright
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
        handler.log_message = lambda *a: None
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) else route.abort())
                page.goto(origin + '/')
                page.click('#example')
                page.click('#estimate')
                page.wait_for_function("/\\d/.test((document.querySelector('#estimated-price')||{}).textContent||'')", timeout=90000)
                page.wait_for_function("document.querySelector('#offers-result .ad-label')", timeout=10000)
                self.assertIn('火災保険', page.inner_text('#offers-result'))
                self.assertIn('広告・PR', page.inner_text('#offers-result'))
                hrefs = page.eval_on_selector_all('#offers-result a', 'as => as.map(a => a.rel)')
                self.assertTrue(hrefs and all('sponsored' in r for r in hrefs))
                page.check('input[name=intent][value=sell]')
                page.wait_for_function("document.querySelector('#offers-result').hidden")
                browser.close()
        finally:
            server.shutdown()

    def test_example_appraisal_runs_in_chromium(self):
        from playwright.sync_api import sync_playwright
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
        handler.log_message = lambda *a: None
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        origin = f'http://127.0.0.1:{server.server_port}'
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                for width, height in ((1280, 900), (390, 844)):
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) else route.abort())
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(origin + '/', wait_until='load')
                    page.click('#example')
                    page.click('#estimate')
                    page.wait_for_function(
                        "/\\d/.test((document.querySelector('#estimated-price')||{}).textContent||'')", timeout=90000)
                    estimate = page.inner_text('#estimated-price')
                    result = page.inner_text('#result')
                    self.assertRegex(estimate, r'^\s*[\d,]+\s*$')
                    self.assertTrue(page.inner_text('#result-badge').strip())
                    self.assertIn('販売価格', result)
                    self.assertRegex(result, r'査定価格との差\s*[+−-][\d,]+万円')
                    self.assertIn('広告・PR', result)
                    prefs = page.eval_on_selector_all('#prefecture option', 'os => os.map(o => o.textContent).filter(t => /[都道府県]$/.test(t))')
                    self.assertEqual((len(prefs), prefs[0], prefs[-1]), (47, '北海道', '沖縄県'))
                    # Entered in tsubo, the area reaches the result in square metres with a long fraction.
                    page.select_option('#areaUnit', '坪')
                    page.fill('#area', '21.2')
                    page.click('#estimate')
                    page.wait_for_function("/坪|㎡/.test(document.querySelector('#result-location').textContent) && !document.querySelector('#estimate').disabled", timeout=90000)
                    location = page.inner_text('#result-location')
                    self.assertRegex(location, r'専有 [\d,]+(\.\d{1,2})?㎡', location)
                    page.close()
                browser.close()
        finally:
            server.shutdown()
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
