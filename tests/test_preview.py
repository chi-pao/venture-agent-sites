import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('preview_app',Path(__file__).parent.parent/'agent/venture_agent_integrated.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
        app.DB=self.root/'agent.db';app.OUT=self.root/'out';app.OUT.mkdir();app.init()
        self.name='比較ツール';self.page='<!doctype html><html lang="ja"><head><title>確認</title></head><body><button>計算</button><script>const original = 17;</script></body></html>'
        self.cfg=dict(app.DEFAULT,github_repo='owner/repo',public_base_url='https://review.example')

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_click_target_serves_real_html_without_download_and_blocks_file_access(self):
        preview=app.ensure_product_preview(self.name,self.page,{})
        with urllib.request.urlopen(preview['url']) as r:
            self.assertEqual(r.headers.get_content_type(),'text/html')
            self.assertIsNone(r.headers.get('Content-Disposition'))
            self.assertEqual(r.headers.get('Cache-Control'),'no-store')
            self.assertEqual(r.read().decode(),app.preview_document(self.page))
        base=preview['url'].split('/review/')[0]
        for path in ('/','/../agent.db','/review/not-a-real-key/index.html'):
            with self.assertRaises(HTTPError) as err:urllib.request.urlopen(base+path)
            self.assertEqual(err.exception.code,404)

    def test_each_version_has_stable_own_link_and_preserves_original_code(self):
        one=app.ensure_product_preview(self.name,self.page,{})
        same=app.ensure_product_preview(self.name,self.page,{})
        second=self.page.replace('original = 17','original = 23')
        two=app.ensure_product_preview(self.name,second,{})
        self.assertEqual(one['url'],same['url']);self.assertNotEqual(one['url'],two['url'])
        self.assertEqual(one['content_sha'],hashlib.sha256(self.page.encode()).hexdigest())
        for result,expected in ((one,self.page),(two,second)):
            with urllib.request.urlopen(result['url']) as r:body=r.read().decode()
            self.assertEqual(body,app.preview_document(expected));self.assertIn('noindex',body)

    def test_review_upload_only_writes_review_path_and_does_not_approve_or_post(self):
        local=app.ensure_product_preview(self.name,self.page,self.cfg)
        row=app.query('SELECT * FROM venture_product_previews')[0];requests=[]
        def network(req,**kw):
            requests.append(req)
            if req.get_method()=='GET':raise HTTPError(req.full_url,404,'missing',None,None)
            return io.BytesIO(b'{}')
        with patch.dict(os.environ,{'VENTURE_GITHUB_TOKEN':'fictional-test-token'}),patch.object(app.urllib.request,'urlopen',side_effect=network),patch.object(app,'verify_public_page',return_value=(True,'match')) as verify:
            app.upload_product_preview(self.name,self.page,self.cfg,row,row['config_key'])
        writes=[r for r in requests if r.get_method()=='PUT'];self.assertEqual(len(writes),1)
        self.assertIn('/contents/review-previews/',writes[0].full_url)
        self.assertNotIn('/contents/projects/',writes[0].full_url)
        import base64
        self.assertEqual(base64.b64decode(json.loads(writes[0].data)['content']).decode(),app.preview_document(self.page))
        verify.assert_called_once_with(row['web_url'],hashlib.sha256(app.preview_document(self.page).encode()).hexdigest())
        ready=app.ensure_product_preview(self.name,self.page,self.cfg)
        self.assertTrue(ready['web_ready']);self.assertEqual(ready['url'],row['web_url'])
        self.assertEqual(app.query('SELECT * FROM venture_product_reviews'),[])
        self.assertEqual(app.query('SELECT * FROM autonomous_checks'),[])
        self.assertEqual(app.query('SELECT * FROM venture_sns_campaigns'),[])
        self.assertFalse(app.product_quality_allowed(self.name))

    def test_uploaded_pending_preview_is_rechecked_without_another_commit(self):
        app.ensure_product_preview(self.name,self.page,self.cfg)
        app.execute('UPDATE venture_product_previews SET uploaded=1')
        row=app.query('SELECT * FROM venture_product_previews')[0]
        with patch.dict(os.environ,{'VENTURE_GITHUB_TOKEN':'fictional-test-token'}),patch.object(app.urllib.request,'urlopen') as network,patch.object(app,'verify_public_page',return_value=(False,'not yet')):
            app.upload_product_preview(self.name,self.page,self.cfg,row,row['config_key'])
        network.assert_not_called();self.assertEqual(app.query('SELECT ready FROM venture_product_previews')[0]['ready'],0)

    def test_wrong_source_digest_cannot_be_uploaded_under_another_version(self):
        app.ensure_product_preview(self.name,self.page,self.cfg)
        row=app.query('SELECT * FROM venture_product_previews')[0]
        with patch.dict(os.environ,{'VENTURE_GITHUB_TOKEN':'fictional-test-token'}),patch.object(app.urllib.request,'urlopen') as network:
            app.upload_product_preview(self.name,self.page+'changed',self.cfg,row,row['config_key'])
        network.assert_not_called()

    def test_existing_approval_gate_still_blocks_a_preview_from_releasing(self):
        app.ensure_product_preview(self.name,self.page,self.cfg)
        with patch.object(app.urllib.request,'urlopen') as network:
            url,detail=app.github_publish(self.name,self.page,dict(self.cfg,publish=True))
        self.assertEqual(url,'');self.assertIn('発信OK待ち',detail);network.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
