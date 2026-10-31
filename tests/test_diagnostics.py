"""Stage A of the Claude Code link: a diagnostics zip the owner can hand over, with no secrets or DB."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'agent' / 'venture_agent_integrated.py'
spec = importlib.util.spec_from_file_location('diagnostics_app', SOURCE)
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

SECRETS = ['ghp_' + 'A' * 36, 'sk_live_' + 'B' * 20, 'hook-secret-value', 'analytics-secret-token', 'Bearer ' + 'C' * 30]


class DiagnosticsExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.old = (app.DB, app.OUT, app.AGENT, app.BASE)
        app.BASE = root; app.DB = root / 'venture_agent_integrated.db'; app.OUT = root / 'out'; app.AGENT = root / 'agent'
        app.OUT.mkdir(); app.AGENT.mkdir(); app.init()
        cfg = dict(app.DEFAULT, stripe_api_key=SECRETS[1], marketing_webhook='https://hooks.example/' + SECRETS[2],
                   analytics_api_token=SECRETS[3], github_repo='owner/repo')
        app.execute('UPDATE autonomous_control SET config=?,last_error=? WHERE id=1', (json.dumps(cfg), 'HTTP 401 ' + SECRETS[4]))
        app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)', (app.now(), 'エラー', 'push failed with ' + SECRETS[0]))
        app.execute("INSERT INTO agent_settings(key,value) VALUES('bluesky_credentials_dpapi_v1','DPAPI1:c2VjcmV0')")
        run_id = 'a' * 32
        bench = app.OUT / 'shared' / 'model-benchmarks' / run_id / 'new-0123456789ab'
        bench.mkdir(parents=True)
        (bench / 'candidate.html').write_text('<html>failing page</html>', encoding='utf-8')
        (bench / 'failure-1280.png').write_bytes(b'\x89PNG fake')
        app.save_benchmark_state(dict(run_id=run_id, status='完了', results=[dict(model='m', passed=False,
                                 error='ValueError: 2件の登録・件数表示が不一致（一覧の行数: 4 / 件数表示: \'4\'）')]))
        (root / 'code').mkdir(); (root / 'code' / 'installed.json').write_text('{"version": "2026.11.01.1"}', encoding='utf-8')
        (app.AGENT / 'research.log').write_text('research ok\napiKey=' + 'D' * 20 + '\n', encoding='utf-8')

    def tearDown(self):
        app.DB, app.OUT, app.AGENT, app.BASE = self.old; self.tmp.cleanup()

    def test_zip_has_state_and_comparison_evidence_but_no_db_or_secrets(self):
        name, data = app.build_diagnostics()
        self.assertTrue(name.startswith('venture-diagnostics-') and name.endswith('.zip'))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            self.assertIn('summary.json', names)
            self.assertIn('model-benchmark/new-0123456789ab/candidate.html', names)
            self.assertIn('model-benchmark/new-0123456789ab/failure-1280.png', names)
            self.assertIn('launcher/installed.json', names); self.assertIn('logs/research.log', names)
            self.assertFalse(any(n.endswith('.db') for n in names))
            blob = b''.join(archive.read(n) for n in names)
            summary = json.loads(archive.read('summary.json'))
        for secret in SECRETS + ['D' * 20, 'DPAPI1', 'c2VjcmV0']:
            self.assertNotIn(secret.encode(), blob, secret)
        self.assertEqual(summary['autonomous_control']['config']['stripe_api_key'], '***')
        self.assertEqual(summary['autonomous_control']['config']['github_repo'], 'owner/repo')
        self.assertIn('一覧の行数: 4', summary['model_benchmark']['results'][0]['error'])
        self.assertEqual(summary['app_version'], app.APP_VERSION)

    def test_oversized_files_are_listed_not_packed(self):
        name, data = app.build_diagnostics(max_file_bytes=10)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn('skipped.txt', archive.namelist())
            self.assertIn('candidate.html', archive.read('skipped.txt').decode())


class DataHomeTests(unittest.TestCase):
    def test_running_the_managed_copy_directly_uses_the_existing_data_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); (home / 'code').mkdir()
            shutil.copy2(SOURCE, home / 'code' / 'current.py')
            with closing(sqlite3.connect(home / 'venture_agent_integrated.db')):
                pass
            env = {k: v for k, v in os.environ.items() if k != 'VENTURE_DATA_HOME'}
            result = subprocess.run([sys.executable, str(home / 'code' / 'current.py'), '--export-diagnostics'],
                                    cwd=str(home / 'code'), env=env, capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((home / 'code' / 'venture_agent_integrated.db').exists(), 'created a second, empty DB in code/')
            zips = list((home / 'diagnostics').glob('venture-diagnostics-*.zip'))
            self.assertEqual(len(zips), 1, result.stdout)


if __name__ == '__main__':
    unittest.main()
