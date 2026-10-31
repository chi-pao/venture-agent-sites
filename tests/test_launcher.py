"""Windows launcher: update, startup check and automatic recovery (runs on Linux and Windows CI)."""
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('launcher_under_test', ROOT / 'agent' / 'launcher.py')
launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)

GOOD_OLD = b"import streamlit as st\nst.write('previous version works')\n"
GOOD_NEW = b"import streamlit as st\nst.write('new version works')\n"
BROKEN_NEW = b"import streamlit as st\nraise RuntimeError('new version crashes on start')\n"
ENV_PROBE = (b"import os, streamlit as st\n"
             b"assert not any(k.startswith('VENTURE_') and k != 'VENTURE_DATA_HOME' for k in os.environ), 'secret leaked'\n"
             b"assert os.environ['VENTURE_DATA_HOME'] != os.environ['REAL_DATA_HOME'], 'used the real data folder'\n"
             b"st.write('isolated')\n")


def fetcher(content, version='9.9.9'):
    manifest = json.dumps({'version': version, 'sha256': hashlib.sha256(content).hexdigest(),
                           'source_url': 'https://raw.githubusercontent.com/chi-pao/venture-agent-sites/x/agent/app.py'}).encode()
    return lambda url, limit: manifest if url == launcher.MANIFEST else content


class LauncherRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / 'data'; self.code = self.data / 'code'; self.code.mkdir(parents=True)
        with closing(sqlite3.connect(self.data / 'venture_agent_integrated.db')) as db, db:
            db.execute('CREATE TABLE keep(v)'); db.execute("INSERT INTO keep VALUES('owner data')")
        (self.code / 'current.py').write_bytes(GOOD_OLD)

    def tearDown(self):
        self.tmp.cleanup()

    def current(self):
        return (self.code / 'current.py').read_bytes()

    def test_good_update_passes_real_startup_check_and_stays(self):
        launcher.install_update(self.data, self.code, fetch=fetcher(GOOD_NEW))
        self.assertTrue((self.code / 'pending_check.json').exists())
        self.assertEqual(launcher.verify_pending_update(self.data, self.code), 'Startup check passed')
        self.assertEqual(self.current(), GOOD_NEW)
        self.assertFalse((self.code / 'pending_check.json').exists())

    def test_broken_update_is_rolled_back_and_not_reinstalled(self):
        fetch = fetcher(BROKEN_NEW, version='broken-1')
        launcher.install_update(self.data, self.code, fetch=fetch)
        message = launcher.verify_pending_update(self.data, self.code)
        self.assertTrue(message.startswith('Rolled back'), message)
        self.assertIn('broken-1', message)
        self.assertEqual(self.current(), GOOD_OLD)
        failed = launcher.failed_updates(self.code)
        self.assertIn(hashlib.sha256(BROKEN_NEW).hexdigest(), failed)
        self.assertIn('crashes on start', failed[hashlib.sha256(BROKEN_NEW).hexdigest()]['reason'])
        self.assertIn('skipped', launcher.install_update(self.data, self.code, fetch=fetch))
        self.assertEqual(self.current(), GOOD_OLD)
        with closing(sqlite3.connect(self.data / 'venture_agent_integrated.db')) as db:
            self.assertEqual(db.execute('SELECT v FROM keep').fetchall(), [('owner data',)])

    def test_next_good_release_installs_after_a_failed_one(self):
        launcher.install_update(self.data, self.code, fetch=fetcher(BROKEN_NEW))
        launcher.verify_pending_update(self.data, self.code)
        self.assertIn('installed', launcher.install_update(self.data, self.code, fetch=fetcher(GOOD_NEW)))
        self.assertEqual(launcher.verify_pending_update(self.data, self.code), 'Startup check passed')
        self.assertEqual(self.current(), GOOD_NEW)

    def test_startup_check_gets_no_secrets_and_a_copy_of_the_data(self):
        with patch.dict(os.environ, {'VENTURE_GITHUB_TOKEN': 'secret', 'REAL_DATA_HOME': str(self.data)}):
            launcher.install_update(self.data, self.code, fetch=fetcher(ENV_PROBE))
            self.assertEqual(launcher.verify_pending_update(self.data, self.code), 'Startup check passed')

    def test_unverifiable_check_keeps_new_version_and_says_so(self):
        launcher.install_update(self.data, self.code, fetch=fetcher(GOOD_NEW))
        message = launcher.verify_pending_update(self.data, self.code, check=lambda d, c: ('unverified', 'timed out'))
        self.assertIn('unverified', message); self.assertEqual(self.current(), GOOD_NEW)

    def test_failed_first_install_without_previous_version_still_starts(self):
        (self.code / 'current.py').unlink()
        launcher.install_update(self.data, self.code, fetch=fetcher(BROKEN_NEW))
        (self.code / 'previous.py').unlink(missing_ok=True)
        message = launcher.verify_pending_update(self.data, self.code)
        self.assertIn('no previous version', message); self.assertEqual(self.current(), BROKEN_NEW)

    def test_main_recovers_when_new_version_exits_immediately(self):
        real_install = launcher.install_update
        def install(data_home, code_home, fetch=None):
            return real_install(data_home, code_home, fetch=fetcher(GOOD_NEW, version='early-exit'))
        calls = []
        def fake_call(command, **kwargs):
            calls.append(Path(command[4]).read_bytes()); return 1 if len(calls) == 1 else 0
        with patch.object(launcher, 'install_update', side_effect=install), \
             patch.object(launcher, 'smoke_check', return_value=('ok', '')), \
             patch.object(launcher.subprocess, 'call', side_effect=fake_call), \
             patch.object(sys, 'argv', ['launcher.py', '--data-home', str(self.data)]):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(calls, [GOOD_NEW, GOOD_OLD])
        self.assertEqual(self.current(), GOOD_OLD)
        self.assertIn(hashlib.sha256(GOOD_NEW).hexdigest(), launcher.failed_updates(self.code))

    def test_normal_stop_of_an_unchanged_version_never_rolls_back(self):
        with patch.object(launcher, 'install_update', return_value='Already up to date'), \
             patch.object(launcher.subprocess, 'call', return_value=1) as call, \
             patch.object(sys, 'argv', ['launcher.py', '--data-home', str(self.data)]):
            launcher.main()
        self.assertEqual(call.call_count, 1); self.assertEqual(self.current(), GOOD_OLD)


class RealAppStartupCheckTests(unittest.TestCase):
    def test_current_dashboard_passes_the_startup_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); code = data / 'code'; code.mkdir()
            (code / 'current.py').write_bytes((ROOT / 'agent' / 'venture_agent_integrated.py').read_bytes())
            status, detail = launcher.smoke_check(data, code)
            self.assertEqual(status, 'ok', detail)


if __name__ == '__main__':
    unittest.main()
