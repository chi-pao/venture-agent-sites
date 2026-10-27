"""Deterministic capture-policy checks; live web screenshots require browser CI."""
from unittest import TestCase
from test_preview import app


class CapturePolicyTests(TestCase):
    def test_only_same_origin_xhr_and_fetch_are_allowed(self):
        self.assertTrue(app.competitor_request_allowed('https://www.example.com/api','example.com','fetch'))
        self.assertTrue(app.competitor_request_allowed('https://example.com/api','example.com','xhr'))
        self.assertFalse(app.competitor_request_allowed('https://other.com/api','example.com','fetch'))
        self.assertFalse(app.competitor_request_allowed('http://127.0.0.1:8000/','example.com','document',True))
        self.assertFalse(app.competitor_request_allowed('https://other.com/','example.com','document',True))
        self.assertFalse(app.competitor_request_allowed('https://example.com/','example.com','websocket'))
        self.assertTrue(app.competitor_request_allowed('https://cdn.other.com/style.css','example.com','stylesheet'))

    def test_rejects_challenge_wrong_host_and_viewport(self):
        metrics={'bodyTextLength':120,'heading':'Application','viewportWidth':390,'bodyTextSample':'Product content'}
        self.assertEqual(app.competitor_capture_error(metrics,390,'https://www.example.com/','example.com'),'')
        self.assertTrue(app.competitor_capture_error(metrics,1280,'https://example.com/','example.com'))
        self.assertTrue(app.competitor_capture_error(metrics,390,'https://other.com/','example.com'))
        self.assertIn('ボット',app.competitor_capture_error(dict(metrics,heading='Verify you are human'),390,'https://example.com/','example.com'))
        self.assertTrue(app.competitor_capture_error(dict(metrics,bodyTextLength=20),390,'https://example.com/','example.com'))
