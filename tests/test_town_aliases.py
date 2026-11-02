"""Town names on the checker must be matched to the district names in the transaction data."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('build_town_aliases', ROOT / 'tools' / 'build_town_aliases.py')
aliases = importlib.util.module_from_spec(spec); spec.loader.exec_module(aliases)


class TownAliasTests(unittest.TestCase):
    def districts(self, *names):
        return {aliases.key(n): n for n in sorted(names, key=len)}

    def test_writing_differences_are_matched(self):
        d = self.districts('大字際波', '月寒東２条', '彌富通', '門田町大字飯寺', '字標津', '北２４条東')
        self.assertEqual(aliases.match('際波', d), '大字際波')
        self.assertEqual(aliases.match('月寒東二条', d), '月寒東２条')
        self.assertEqual(aliases.match('弥富通', d), '彌富通')
        self.assertEqual(aliases.match('門田町飯寺', d), '門田町大字飯寺')
        self.assertEqual(aliases.match('標津', d), '字標津')
        self.assertEqual(aliases.match('北二十四条東', d), '北２４条東')

    def test_a_picked_town_falls_back_to_the_coarser_recorded_area(self):
        d = self.districts('大久保町', '大久保町茜', '八街')
        self.assertEqual(aliases.match('大久保町八木', d), '大久保町')
        self.assertEqual(aliases.match('大久保町茜', d), '大久保町茜')
        self.assertEqual(aliases.match('八街ほ', d), '八街')

    def test_unrelated_or_one_letter_names_are_not_matched(self):
        d = self.districts('本', '宮地町')
        self.assertIsNone(aliases.match('本郷', d))
        self.assertIsNone(aliases.match('西宮', d))

    def test_kanji_numbers(self):
        self.assertEqual(aliases.kanji_number('二十四'), '24')
        self.assertEqual(aliases.kanji_number('十'), '10')
        self.assertEqual(aliases.kanji_number('百五'), '105')


if __name__ == '__main__':
    unittest.main()
