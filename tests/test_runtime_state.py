import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('runtime_state_app',Path(__file__).parent.parent/'agent/venture_agent_integrated.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.old=(app.DB,app.OUT,app.LOCK,app.STOP)
        app.DB=root/'agent.db';app.OUT=root/'out';app.OUT.mkdir()
        app.LOCK=root/'worker.lock';app.STOP=root/'stop.flag'
        app.init()

    def tearDown(self):
        app.DB,app.OUT,app.LOCK,app.STOP=self.old;self.tmp.cleanup()

    def test_db_context_commits_and_closes_connection(self):
        with app.db() as c:
            c.execute("INSERT INTO agent_settings(key,value) VALUES('k','v')")
        with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        self.assertEqual(app.query("SELECT value FROM agent_settings WHERE key='k'"),[{'value':'v'}])

    def test_db_context_rolls_back_on_error_and_closes(self):
        with self.assertRaises(RuntimeError):
            with app.db() as c:
                c.execute("INSERT INTO agent_settings(key,value) VALUES('x','y')")
                raise RuntimeError('boom')
        with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        self.assertEqual(app.query("SELECT value FROM agent_settings WHERE key='x'"),[])

    def test_stale_on_flag_after_restart_becomes_off_without_restarting_work(self):
        app.execute('UPDATE autonomous_control SET enabled=1 WHERE id=1')
        with patch.object(app.threading,'Thread') as thread:
            self.assertTrue(app.reconcile_worker_state())
            thread.assert_not_called()
        s=app.state();self.assertEqual(s['enabled'],0);self.assertEqual(s['last_error'],app.WORKER_INTERRUPTED)
        self.assertFalse(app.reconcile_worker_state())

    def test_stale_lock_from_dead_process_is_also_reconciled(self):
        app.execute('UPDATE autonomous_control SET enabled=1 WHERE id=1')
        app.LOCK.write_text(json.dumps({'pid':999999999,'started':app.now()}),encoding='utf-8')
        self.assertTrue(app.reconcile_worker_state());self.assertEqual(app.state()['enabled'],0)

    def test_live_worker_is_left_running(self):
        app.execute('UPDATE autonomous_control SET enabled=1 WHERE id=1')
        app.LOCK.write_text(json.dumps({'pid':os.getpid(),'started':app.now()}),encoding='utf-8')
        self.assertFalse(app.reconcile_worker_state());self.assertEqual(app.state()['enabled'],1)

    def test_stopped_state_is_untouched(self):
        app.execute("UPDATE autonomous_control SET enabled=0,last_error='前のエラー' WHERE id=1")
        self.assertFalse(app.reconcile_worker_state());self.assertEqual(app.state()['last_error'],'前のエラー')


if __name__=='__main__':
    unittest.main()
