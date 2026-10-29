"""Actual-model capability experiment with fixed, independently specified answers.

This is a synthetic diagnostic, NOT generated-product or browser-quality proof.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

RULE='空の保存領域から開始する。新規入力後のsaveNewは記録を一件追加する。editAは最初の記録を編集画面に開くだけで保存件数は変わらない。saveEditは最初の記録を更新し、件数は増えない。'
CASES=[
 dict(name='create_one',steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#saveNew')],effects=['create'],origins=[1],count=1),
 dict(name='create_two',steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#saveNew'),dict(op='fill',selector='#name',value='B'),dict(op='click',selector='#saveNew')],effects=['create','create'],origins=[1,3],count=2),
 dict(name='edit_keeps_count',steps=[dict(op='fill',selector='#name',value='A'),dict(op='click',selector='#saveNew'),dict(op='click',selector='#editA'),dict(op='fill',selector='#name',value='A改'),dict(op='click',selector='#saveEdit')],effects=['create','none','update'],origins=[1,2,4],count=1),
]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--list-cases',action='store_true');args=parser.parse_args()
    if args.list_cases:
        print(json.dumps(CASES,ensure_ascii=False));return
    path=Path(__file__).resolve().parents[1]/'agent/venture_agent_integrated.py'
    spec=importlib.util.spec_from_file_location('capability_app',path);app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
    model=os.environ['PROBE_MODEL'];root=Path('reference-model-evidence');root.mkdir(exist_ok=True)
    app.DB=root/'probe.db';app.OUT=root/'outputs';app.OUT.mkdir(exist_ok=True);app.init()
    cfg=dict(app.DEFAULT,model=model,qa_oracle_model=model,url=os.environ.get('OLLAMA_HOST','http://127.0.0.1:11435'),qa_part_timeout=120,qa_oracle_timeout=120,ai_context=8192)
    result=dict(model=model,source_sha=hashlib.sha256(path.read_bytes()).hexdigest(),fixture_sha=hashlib.sha256(json.dumps(CASES,sort_keys=True).encode()).hexdigest(),kind='synthetic real-model capability; not product acceptance',cases=[])
    original=app.ai_json;calls=[]
    def recorded(prompt,config,tokens,**kw):
        start=time.monotonic();record=dict(model=config['model'],prompt=prompt,schema=kw.get('schema'),max_tokens=tokens)
        try:
            answer=original(prompt,config,tokens,**kw);record['answer']=answer;return answer
        except Exception as exc:
            record['error']=type(exc).__name__+': '+str(exc);raise
        finally:
            record['seconds']=round(time.monotonic()-start,2);calls.append(record)
            (root/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
    app.ai_json=recorded
    for case in CASES:
        directory=root/case['name'];directory.mkdir(exist_ok=True);row=dict(name=case['name'],passed=False,expected=case)
        try:
            raw=dict(steps=case['steps'],exact_check=dict(selector='#recordCount',value='untrusted'))
            answer=app.qa_reference_count_oracle(raw,{},dict(requested_outcome=RULE,must_have=[RULE],acceptance=[RULE]),cfg,directory,'base-workflow',[])
            if answer is None:raise AssertionError('Explicit record count was not mapped')
            trace=answer['reference_count']['trace'];row['actual']=answer
            if [e['effect'] for e in trace]!=case['effects'] or [e['step_index'] for e in trace]!=case['origins'] or answer['exact_check']['value']!=str(case['count']):raise AssertionError('Mapping differs from fixed independent fixture')
            row['passed']=True
        except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)
        result['cases'].append(row)
    wrong=dict(quantity='record_count',source_quote=RULE,events=[dict(step_index=1,effect='none',target=None)])
    row=dict(name='audit_must_reject_wrong_binding',passed=False)
    try:
        schema={'type':'object','properties':{'valid':{'type':'boolean'},'reason':{'type':'string'}},'required':['valid','reason'],'additionalProperties':False}
        answer=app.ai_json(app.qa_reference_mapping_audit_prompt('#recordCount',CASES[0]['steps'],wrong),dict(cfg,_schema_in_prompt=False),250,schema=schema,max_attempts=1,request_timeout=120)
        row.update(actual=answer,passed=isinstance(answer,dict) and answer.get('valid') is False)
    except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)
    result['cases'].append(row);result['passed']=all(r['passed'] for r in result['cases'])
    (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REFERENCE_MODEL_CAPABILITY',json.dumps(result,ensure_ascii=False),flush=True)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
