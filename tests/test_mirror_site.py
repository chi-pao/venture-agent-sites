"""The site mirror must follow the same references the checker uses, and never leave the host."""
from functools import partial
import http.server
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('mirror_site', ROOT / 'tools' / 'mirror_site.py')
mirror_site = importlib.util.module_from_spec(spec); spec.loader.exec_module(mirror_site)

FILES = {
    'index.html': '<link rel="stylesheet" href="style.css"><script type="module" src="app.mjs"></script>'
                  '<a href="https://other.example/x.js">x</a><img src="/_sites/badge.svg">',
    'style.css': 'body{background:url("img/bg.png")}',
    'img/bg.png': 'PNG',
    'app.mjs': "import {a} from './engine.mjs';const w=new Worker(new URL('./model-worker.mjs?v=1',import.meta.url),{type:'module'});"
               "Promise.all([fetch('models/catalog.json'),fetch('towns.json')]);new URL('ocr-worker.min.js',location.href)",
    'engine.mjs': "export const a=1;import('./lazy.mjs')",
    'lazy.mjs': 'export default 1',
    'model-worker.mjs': "import {m} from './learning.mjs'",
    'learning.mjs': "export const m='models/manifest.json'",
    'models/catalog.json': json.dumps({'models': {'used_house': {'file': 'models/used_house.json', 'note': 'not a file'},
                                                  'condo': {'file': 'models/missing.json'}}}),
    'models/used_house.json': '{"trees": []}',
    'models/manifest.json': '{}',
    'towns.json': '[]',
    'ocr-worker.min.js': '//',
    '_sites/badge.svg': '<svg/>',
}


class MirrorSiteTests(unittest.TestCase):
    def test_follows_imports_workers_fetches_css_and_json_listings_on_one_host(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            for name, body in FILES.items():
                path = Path(src) / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(body)
            handler = partial(http.server.SimpleHTTPRequestHandler, directory=src)
            handler.log_message = lambda *a: None
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                saved, skipped = mirror_site.mirror(f'http://127.0.0.1:{server.server_port}/', out)
            finally:
                server.shutdown()
            names = {n for n, _, _ in saved}
            expected = set(FILES) - {'_sites/badge.svg'}
            self.assertEqual(names, expected)
            self.assertFalse((Path(out) / '_sites').exists())
            self.assertTrue(any('other.example' in u for u, _ in skipped))
            self.assertTrue(any(u.endswith('models/missing.json') and 'not found' in why for u, why in skipped), skipped)
            self.assertFalse(any('models/models/used_house.json' in u for u, _ in skipped), skipped)
            report = (Path(out) / 'MIRROR_REPORT.md').read_text(encoding='utf-8')
            self.assertIn('models/used_house.json', report)
            self.assertEqual((Path(out) / 'engine.mjs').read_text(), FILES['engine.mjs'])


if __name__ == '__main__':
    unittest.main()
