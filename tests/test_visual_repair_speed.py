from test_preview import app
from unittest import TestCase
from unittest.mock import patch
import re
import tempfile
from pathlib import Path

class VisualRepairSpeedTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous_out=app.OUT;app.OUT=Path(self.tmp.name)
    def tearDown(self):
        app.OUT=self.previous_out;self.tmp.cleanup()
    source='<!doctype html><html><head><style>.hero{color:red}</style></head><body><header><h1>講師向け出欠管理サービス</h1></header><button id="save">保存する</button><script>const keep="SCRIPT_MUST_STAY";function save(){localStorage.setItem("x","y")}</script></body></html>'
    def test_visual_edits_keep_javascript_and_ids(self):
        got=app.apply_visual_product_edits(self.source,dict(css='.hero{color:navy}',copy=[dict(old='講師向け出欠管理サービス',new='個人講師の出欠を一括管理')]))
        self.assertEqual(re.findall(r'<script>.*?</script>',got),re.findall(r'<script>.*?</script>',self.source))
        self.assertIn('id="save"',got)
        self.assertIn('color:navy',got)
        self.assertIn('個人講師の出欠を一括管理',got)
    def test_visual_edits_cannot_modify_scripts_or_inject_markup(self):
        for proposal in [dict(css='</style><script>bad()</script>'),dict(css='@import "https://example.com/x";'),dict(copy=[dict(old='SCRIPT_MUST_STAY',new='changedScript')]),dict(css='',copy=[])]:
            with self.subTest(proposal=proposal),self.assertRaises(ValueError):
                app.apply_visual_product_edits(self.source,proposal)
    def test_visual_request_contains_css_but_no_script_and_has_separate_budget(self):
        captured={}
        def answer(prompt,cfg,tokens,**kw):
            captured.update(prompt=prompt,tokens=tokens,options=kw)
            return dict(reason='既存の見出しの配色を改善',css='.hero{color:navy}',copy=[])
        with patch.object(app,'get_product_spec',return_value={}),patch.object(app,'ai_json',side_effect=answer):
            page,reason=app.visual_product_repair('出欠管理',self.source,'画像判定: designの改善',dict(app.DEFAULT))
        self.assertIn('.hero{color:red}',captured['prompt'])
        self.assertIn('実在するCSS指定先:[".hero"]',captured['prompt'])
        self.assertNotIn('SCRIPT_MUST_STAY',captured['prompt'])
        self.assertEqual(captured['tokens'],900)
        self.assertLess(len(captured['prompt']),6000)
        self.assertEqual(captured['options']['request_timeout'],300)
        self.assertEqual(captured['options']['max_attempts'],1)
        self.assertIn('color:navy',page)

    def test_duplicate_internal_copy_does_not_block_rendered_copy_edit(self):
        text='講師向け出欠管理サービス'
        source='<html><head><title>'+text+'</title></head><body><h1>'+text+'</h1><script>const name="'+text+'";</script></body></html>'
        got=app.replace_visible_product_copy(source,text,'個人講師の出欠を一括管理')
        self.assertIn('<title>'+text+'</title>',got)
        self.assertIn('<script>const name="'+text+'";</script>',got)
        self.assertIn('<h1>個人講師の出欠を一括管理</h1>',got)
    def test_valid_saved_proposal_skips_repeat_inference(self):
        proposal=dict(reason='配色の改善案を保存',css='.hero{color:navy}',copy=[])
        with patch.object(app,'get_product_spec',return_value={}),patch.object(app,'ai_json',return_value=proposal) as model:
            first=app.visual_product_repair('出欠管理',self.source,'designの改善',dict(app.DEFAULT))
            second=app.visual_product_repair('出欠管理',self.source,'designの改善',dict(app.DEFAULT))
        self.assertEqual(first,second)
        self.assertEqual(model.call_count,1)
