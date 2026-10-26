from test_preview import app
from unittest import TestCase
from unittest.mock import patch
import re
import tempfile
from pathlib import Path

class VisualRepairSpeedTests(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous_out=app.OUT;app.OUT=Path(self.tmp.name)
        self.context_patch=patch.object(app,'competitive_context',return_value={'brief':{}});self.context_patch.start()
    def tearDown(self):
        self.context_patch.stop();app.OUT=self.previous_out;self.tmp.cleanup()
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

    def test_noop_copy_across_multiple_nodes_is_ignored(self):
        source='<html><head><style>p{color:red}</style></head><body><h1>在宅ワーク時間・作業管理</h1><div>01 入力</div><div>02 整理</div></body></html>'
        got=app.apply_visual_product_edits(source,dict(css='h1{color:navy}',copy=[
            dict(old='在宅ワーク時間・作業管理',new='在宅ワーク時間と作業管理'),
            dict(old='01 入力 02 整理',new='01 入力 02 整理')]))
        self.assertIn('<h1>在宅ワーク時間と作業管理</h1>',got)
        self.assertIn('<div>01 入力</div><div>02 整理</div>',got)
    def test_copy_normalizes_display_whitespace_and_entities(self):
        source='<html><body><h1>予定 &amp; 実績を\n    一緒に管理</h1></body></html>'
        got=app.replace_visible_product_copy(source,'予定 & 実績を 一緒に管理','予定と実績をまとめて管理')
        self.assertIn('<h1>予定と実績をまとめて管理</h1>',got)
    def test_visual_css_cannot_hide_existing_actions(self):
        source='<html><head><style>.toolbar{display:flex}</style></head><body><div class="toolbar"><button id="save">保存する</button></div></body></html>'
        for css in ('.toolbar{display: none;gap:12px}', '.toolbar {visibility:hidden;margin:8px}'):
            with self.subTest(css=css):
                got=app.apply_visual_product_edits(source,dict(css=css,copy=[]))
                self.assertNotIn('display: none',got)
                self.assertNotIn('visibility:hidden',got)
                self.assertIn('<button id="save">保存する</button>',got)
    def test_removing_only_hiding_rule_is_not_an_improvement(self):
        for css in ('.toolbar{display:none}', '@media(max-width:640px){.toolbar{display:none}}'):
            with self.subTest(css=css),self.assertRaisesRegex(ValueError,'修正内容がありません'):
                app.apply_visual_product_edits(self.source,dict(css=css,copy=[]))

    def test_visual_request_keeps_existing_mobile_rules_and_latest_overrides(self):
        source='<html><head><style>.hero{color:red}'+'.padding{padding:20px}'*400+'@media(max-width:640px){.mobile-critical{display:grid}}</style><style>.last-override{color:navy}</style></head><body><h1>講師向け出欠管理サービス</h1></body></html>'
        captured={}
        def answer(prompt,cfg,tokens,**kw):
            captured['prompt']=prompt
            return dict(reason='既存のスマホ指定を保持',css='.hero{color:navy}',copy=[])
        with patch.object(app,'get_product_spec',return_value={}),patch.object(app,'ai_json',side_effect=answer):
            app.visual_product_repair('出欠管理',source,'mobileの改善',dict(app.DEFAULT))
        self.assertIn('.mobile-critical',captured['prompt'])
        self.assertIn('.last-override',captured['prompt'])
        self.assertLess(len(captured['prompt']),6000)

    def test_copy_references_disambiguate_duplicate_visible_text(self):
        source='<html><head><title>同じ見出し</title></head><body><h1>同じ見出し</h1><h2>同じ見出し</h2><script>const x="同じ見出し";</script></body></html>'
        refs=app.visual_copy_targets(source)
        self.assertEqual([x['text'] for x in refs],['同じ見出し','同じ見出し'])
        got=app.apply_visual_product_edits(source,dict(copy=[dict(ref=refs[1]['ref'],new='二番目の案内を改善')]))
        self.assertIn('<h1>同じ見出し</h1>',got)
        self.assertIn('<h2>二番目の案内を改善</h2>',got)
        self.assertIn('<script>const x="同じ見出し";</script>',got)
    def test_copy_reference_offsets_survive_entities_and_multiple_edits(self):
        source='<html><body><h1>A &amp; Bの管理</h1><p>入力から保存まで\n  簡単に進めます</p></body></html>'
        refs=app.visual_copy_targets(source)
        got=app.apply_visual_product_edits(source,dict(copy=[
            dict(ref=refs[0]['ref'],new='長さが違う最初の見出し'),
            dict(ref=refs[1]['ref'],new='保存までの案内も変更')]))
        self.assertIn('<h1>長さが違う最初の見出し</h1>',got)
        self.assertIn('<p>保存までの案内も変更</p>',got)
    def test_unknown_or_duplicate_copy_references_are_rejected(self):
        for edits in ([dict(ref='missing',new='不正な指定')],[dict(ref='text_0',new='一番目'),dict(ref='text_0',new='二番目')]):
            with self.subTest(edits=edits),self.assertRaises(ValueError):
                app.apply_visual_product_edits(self.source,dict(copy=edits))
