"""A pasted A8.net code becomes an offer only when it is genuinely A8.net's code."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('add_offer', ROOT / 'tools' / 'add_offer.py')
add = importlib.util.module_from_spec(spec); spec.loader.exec_module(add)
OFFERS = json.loads((ROOT / 'checker-site' / 'offers.json').read_text(encoding='utf-8'))

TEXT = ('<a href="https://px.a8.net/svt/ejp?a8mat=ABC+123+4X+ZZZ" rel="nofollow">空き家・中古戸建ての無料買取査定</a>\n'
        '<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=ABC+123+4X+ZZZ" alt="">')
BANNER = ('<a href="https://px.a8.net/svt/ejp?a8mat=ABC+123+4X+YYY" rel="nofollow"><img border="0" width="300" height="250" alt="" '
          'src="https://www24.a8.net/svt/bgt?aid=1&wid=001&eno=01&mid=s1&mc=1"></a>\n'
          '<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=ABC+123+4X+YYY" alt="">')


class AddOfferTests(unittest.TestCase):
    def offers(self):
        return copy.deepcopy(OFFERS)

    def test_text_link_switches_the_slot_on_and_keeps_its_audience(self):
        o = self.offers()
        e = add.apply(o, 'sell-rakuuru-house', TEXT)
        self.assertTrue(e['enabled'])
        self.assertEqual(e['href'], 'https://px.a8.net/svt/ejp?a8mat=ABC+123+4X+ZZZ')
        self.assertEqual(e['text'], '空き家・中古戸建ての無料買取査定')
        self.assertEqual(e['intent'], ['sell'])
        self.assertEqual(e['types'], ['used_house'])

    def test_banner_code(self):
        e = add.apply(self.offers(), 'loan-mogecheck', BANNER)
        self.assertEqual((e['kind'], e['width'], e['height']), ('banner', 300, 250))
        self.assertTrue(e['img'].startswith('https://www24.a8.net/'))

    def test_prefectures_are_checked(self):
        e = add.apply(self.offers(), 'sell-nomucom', TEXT, prefectures=['東京都', '大阪府'])
        self.assertEqual(e['prefectures'], ['東京都', '大阪府'])
        with self.assertRaises(ValueError):
            add.apply(self.offers(), 'sell-nomucom', TEXT, prefectures=['東京'])

    def test_non_a8_or_mismatched_codes_are_refused(self):
        for code in [TEXT.replace('px.a8.net', 'evil.example'),
                     TEXT.replace('www10.a8.net/0.gif?a8mat=ABC+123+4X+ZZZ', 'www10.a8.net/0.gif?a8mat=OTHER'),
                     TEXT.split('\n')[0],
                     TEXT.replace('https://www10.a8.net', 'https://tracker.example'),
                     TEXT + '<a href="https://px.a8.net/svt/ejp?a8mat=SECOND">x</a>']:
            with self.assertRaises(ValueError, msg=code[:60]):
                add.apply(self.offers(), 'sell-rakuuru-house', code)
        with self.assertRaises(ValueError):
            add.apply(self.offers(), 'no-such-slot', TEXT)

    def test_every_enabled_offer_is_an_a8_link_with_its_pixel(self):
        for o in OFFERS['offers']:
            if o['enabled']:
                self.assertTrue(o['href'].startswith('https://px.a8.net/svt/ejp?a8mat='), o['id'])
                self.assertIn('.a8.net/0.gif?a8mat=', o.get('pixel', ''), o['id'])


if __name__ == '__main__':
    unittest.main()
