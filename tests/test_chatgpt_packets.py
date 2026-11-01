"""ChatGPT dispatch: only approved, rule-abiding tasks become instruction sheets."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('chatgpt_packets', ROOT / 'tools' / 'chatgpt_packets.py')
packets = importlib.util.module_from_spec(spec); spec.loader.exec_module(packets)

URL = packets.utm('https://okaidokucyekka.streamlit.app', 'x', 'checker-launch')
GOOD = {'id': 'C-0001', 'kind': 'sns_post_draft', 'title': '相場の目安を紹介', 'status': '承認済み',
        'payload': {'business': 'お買い得物件チェッカー', 'channel': 'X', 'angle': '購入前に相場と比べる',
                    'facts': ['国の不動産取引データと比べた参考価格の目安を表示します'], 'url': URL, 'max_chars': 140}}


class ChatGPTPacketTests(unittest.TestCase):
    def task(self, **changes):
        task = copy.deepcopy(GOOD)
        for key, value in changes.items():
            if key in task:
                task[key] = value
            else:
                task['payload'][key] = value
        return task

    def test_good_task_passes_and_utm_is_added(self):
        self.assertEqual(packets.check_task(GOOD), [])
        self.assertIn('utm_source=x', URL); self.assertIn('utm_medium=social', URL); self.assertIn('utm_campaign=checker-launch', URL)

    def test_each_rule_rejects_its_bad_case(self):
        cases = {
            'facts': self.task(facts=[]),
            '事実（facts）にない数字': self.task(angle='利用者1万人突破'),
            'utm_source': self.task(url='https://okaidokucyekka.streamlit.app'),
            'https': self.task(url='http://example.com/?utm_source=x&utm_medium=social&utm_campaign=a'),
            'pr_label': self.task(affiliate=True),
            'channel': self.task(channel='Facebook'),
            'max_chars': self.task(max_chars=500),
            '認証情報': self.task(facts=['token sk-' + 'a' * 20]),
            'kind': self.task(kind='real_post'),
            'status': self.task(status='自動投稿'),
            'id': self.task(id='x'),
        }
        for expected, task in cases.items():
            with self.subTest(expected=expected):
                errors = packets.check_task(task)
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_number_that_is_in_the_facts_is_allowed(self):
        task = self.task(angle='2件の物件を比べる', facts=['2件の物件を並べて比べられます'])
        self.assertEqual(packets.check_task(task), [])

    def test_duplicate_ids_are_reported(self):
        problems = packets.check_queue({'version': 1, 'tasks': [GOOD, copy.deepcopy(GOOD)]})
        self.assertIn('id が重複しています', problems['C-0001'])

    def test_only_approved_tasks_become_sheets_with_rules_facts_and_reply_form(self):
        pending = self.task(id='C-0002', status='承認待ち')
        image = {'id': 'C-0003', 'kind': 'image_asset', 'title': '画像', 'status': '承認済み',
                 'payload': {'business': 'お買い得物件チェッカー', 'prompt': '中古住宅のシンプルなイラスト', 'headline': '相場と比べて、確認する。'}}
        with tempfile.TemporaryDirectory() as tmp:
            written = packets.render_outbox({'version': 1, 'tasks': [GOOD, pending, image]}, tmp)
            names = sorted(p.name for p in written)
            self.assertEqual(names, ['C-0001.md', 'C-0003.md'])
            sheet = (Path(tmp) / 'C-0001.md').read_text(encoding='utf-8')
        for part in ('依頼ID: `C-0001`', '使ってよい事実', GOOD['payload']['facts'][0], URL, '返却の形式', '数字', 'PR'):
            self.assertIn(part, sheet)

    def test_cli_check_fails_on_a_bad_queue_and_renders_a_good_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / 'queue.json'
            queue.write_text(json.dumps({'version': 1, 'tasks': [self.task(facts=[])]}, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(packets.main(['--check', '--queue', str(queue)]), 1)
            queue.write_text(json.dumps({'version': 1, 'tasks': [GOOD]}, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(packets.main(['--render', '--queue', str(queue), '--outbox', str(Path(tmp) / 'out')]), 0)
            self.assertTrue((Path(tmp) / 'out' / 'C-0001.md').is_file())

    def test_repository_queue_is_valid(self):
        if packets.QUEUE.exists():
            self.assertEqual(packets.check_queue(packets.load()), {})


if __name__ == '__main__':
    unittest.main()
