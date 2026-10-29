"""Transport regression: malformed model output must remain diagnosable."""
import ast
import json
from pathlib import Path
import tempfile
import types
import unittest


class TransportEvidenceTests(unittest.TestCase):
    def test_raw_response_survives_json_parse_failure(self):
        source=(Path(__file__).resolve().parents[1]/'agent'/'venture_agent_integrated.py').read_text()
        tree=ast.parse(source)
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('local_ai_request','ai_json')]
        payload=dict(response='{"value":"1',done=True,done_reason='length',eval_count=120,prompt_eval_count=700)
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps(payload).encode()
        request=types.SimpleNamespace(Request=lambda *a,**k:None,urlopen=lambda *a,**k:Response())
        import urllib.error
        env=dict(json=json,Path=Path,urllib=types.SimpleNamespace(request=request,error=urllib.error),now=lambda:'recorded',AutoQAPlanError=ValueError,
                 write_framework_json=lambda p,v:Path(p).write_text(json.dumps(v)),qa_json=json.loads)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<transport>','exec'),env)
        env['ai']=env['local_ai_request']
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'primary-transport.json'
            with self.assertRaises(ValueError):env['ai_json']('one scalar',dict(model='fixed-model',url='http://unused',_json_transport_evidence=str(path),_bounded_json_retry=True),120,schema=dict(type='object'),max_attempts=1)
            history=json.loads(Path(str(path)+'.generation.json').read_text())
            self.assertEqual(history[-1]['response'],payload['response'])
            self.assertEqual(history[-1]['done_reason'],'length')
            self.assertEqual(history[-1]['num_predict'],120)
