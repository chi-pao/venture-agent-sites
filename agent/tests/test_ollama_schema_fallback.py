"""Regression tests for Ollama JSON-Schema incompatibility recovery."""
import io
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import test_system_baseline as baseline

app = baseline.app


class OllamaSchemaFallbackTests(unittest.TestCase):
    def setUp(self):
        baseline.FrameworkTests.setUp(self)

    def tearDown(self):
        baseline.FrameworkTests.tearDown(self)

    def test_http_400_retries_json_mode_and_still_validates_contract(self):
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        formats = []

        def fake_ai(prompt, cfg, tokens):
            formats.append(cfg.get("_json_response"))
            if len(formats) == 1:
                raise HTTPError(
                    "http://localhost:11434/api/generate", 400, "Bad Request",
                    None, io.BytesIO(b"JSON schema format unsupported"),
                )
            return '{"ok":true}'

        def validate(value):
            if value.get("ok") is not True:
                raise ValueError("ok must be true")
            return value

        with patch.object(app, "ai", side_effect=fake_ai):
            result = app.ai_json(
                "Return one JSON object", dict(app.DEFAULT), tokens=100,
                schema=schema, validator=validate,
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(formats, [schema, "json"])

    def test_other_http_errors_keep_server_diagnostic(self):
        def fake_ai(prompt, cfg, tokens):
            raise HTTPError(
                "http://localhost:11434/api/generate", 503, "Unavailable",
                None, io.BytesIO(b"model is loading"),
            )

        with patch.object(app, "ai", side_effect=fake_ai):
            with self.assertRaisesRegex(app.AutoQAPlanError, "503.*model is loading"):
                app.ai_json("Return JSON", dict(app.DEFAULT), tokens=100, validator=lambda value: value)


if __name__ == "__main__":
    unittest.main()
