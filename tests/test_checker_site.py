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
                    page.close()
                browser.close()
        finally:
            server.shutdown()
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
