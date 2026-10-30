"""Evidence-driven style tokens; these tests do not establish product quality."""
import colorsys
import hashlib
import re
import tempfile
from pathlib import Path
from unittest import TestCase
from test_preview import app


class CompetitorDesignTokenTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def observation(self, idx, palette, radius=12, gap=16):
        views = {}
        for label, width in [('desktop', 1280), ('mobile', 390)]:
            path = self.root / f'{idx}-{label}.png'
            path.write_bytes(f'{idx}-{label}'.encode())
            views[label] = {'width':width, 'screenshot_path':str(path),
                'screenshot_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'metrics':{'viewportWidth':width, 'bodyTextLength':100, 'heading':'Title',
                           'palette':[{'color':palette, 'count':2}],
                           'cardRadiusPx':radius, 'contentGapPx':gap}}
        return {'source_url':f'https://example{idx}.com/', 'capture_status':'ok', 'views':views}

    def test_verified_screen_metrics_change_css_without_copying_hue_or_scripts(self):
        brief={'visual_observations':[self.observation(1,'rgb(230, 58, 71)',20,22),
                                      self.observation(2,'rgb(219, 70, 93)',16,18)]}
        tokens=app.competitor_design_tokens(brief)
        self.assertEqual(tokens['radius_px'],18);self.assertEqual(tokens['gap_px'],20)
        page='<html><head><style>:root{--accent:#3858a8}</style></head><body><button id="save">保存</button><script>const x=1;</script></body></html>'
        result=app.apply_competitor_design_tokens(page,tokens)
        self.assertIn('<button id="save">保存</button><script>const x=1;</script>',result)
        self.assertIn('venture-reference-tokens',result)
        color=re.findall(r'--accent:(#[0-9a-f]{6})',result)[-1]
        rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        old=[int('3858a8'[i:i+2],16)/255 for i in (0,2,4)]
        hue=lambda x:colorsys.rgb_to_hls(*x)[0]
        self.assertLess(abs(hue(rgb)-hue(old)),.01)
        def linear(c):return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4
        lum=sum(a*linear(c) for a,c in zip((.2126,.7152,.0722),rgb))
        self.assertGreaterEqual(1.05/(lum+.05),4.5)
        self.assertIn('色相を複製しない',app.design_tokens_prompt(tokens))

    def test_unverified_and_tampered_reference_never_applies(self):
        a=self.observation(1,'rgb(200, 50, 50)');b=self.observation(2,'rgb(50, 50, 200)')
        self.assertIsNone(app.competitor_design_tokens({'visual_observations':[a]}))
        Path(b['views']['desktop']['screenshot_path']).write_bytes(b'tampered')
        self.assertIsNone(app.competitor_design_tokens({'visual_observations':[a,b]}))
        self.assertEqual(app.apply_competitor_design_tokens('<html></html>',None),'<html></html>')

    def test_unverified_third_reference_does_not_pollute_verified_pair(self):
        a=self.observation(1,'rgb(200, 50, 50)',12,12);b=self.observation(2,'rgb(50, 50, 200)',12,12)
        bad=self.observation(3,'rgb(20, 240, 20)',45,45)
        Path(bad['views']['desktop']['screenshot_path']).write_bytes(b'tampered')
        tokens=app.competitor_design_tokens({'visual_observations':[a,b,bad]})
        self.assertEqual(tokens['radius_px'],12);self.assertEqual(tokens['gap_px'],12)
