"""Replay one bounded count scenario against a saved page and real models.

The fixture is independently specified; passing is not whole-product acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import time
from test_preview import app


def main():
    root=Path(os.environ['VENTURE_LIVE_DATA_HOME']).resolve()
    evidence=root/'saved-count-model';evidence.mkdir(parents=True,exist_ok=True)
    app.DB=evidence/'probe.db';app.OUT=evidence/'outputs';app.OUT.mkdir(exist_ok=True);app.init()
    cfg=dict(app.DEFAULT,model='qwen2.5-coder:7b',qa_mapping_model='qwen2.5:7b',
             qa_oracle_model='qwen2.5:14b',qa_part_timeout=180,qa_oracle_timeout=300,
             ai_context=8192,url=os.environ.get('OLLAMA_HOST','http://127.0.0.1:11435'))
    rule='保存領域は空から開始する。返品商品、注文番号、対応期限、対応状況、返金額を入力して登録ボタンsaveRecordを押すと返品記録を1件追加する。recordCountは保存した全返品記録の件数。別の注文番号で同じ操作を繰り返すと別の記録を追加する。'
    steps=[]
    for i in (1,2):
        steps.extend([dict(op='fill',selector='#return_item',value=f'独立検証商品{i}'),
                      dict(op='fill',selector='#order_number',value=f'ORDER-{i:03d}'),
                      dict(op='fill',selector='#response_deadline',value='2035-12-31'),
                      dict(op='fill',selector='#return_status',value='返送待ち'),
                      dict(op='fill',selector='#refund_amount',value=str(i*1000)),
                      dict(op='click',selector='#saveRecord')])
    required=('id="return_item"','id="order_number"','id="saveRecord"','id="recordCount"')
    pages=[p for p in sorted(root.glob('outputs/sectors/**/02_builds/**/*.html')) if all(x in p.read_text(encoding='utf-8') for x in required)]
    if not pages:raise RuntimeError('Saved real returns page is required')
    page=pages[-1];source=page.read_text(encoding='utf-8')
    intended_steps=steps
    steps=app.qa_normalize_select_inputs(dict(steps=steps),app.compact_qa_inventory(source))['steps']
    if [s['op'] for s in steps if s.get('selector')=='#return_status']!=['select','select']:raise AssertionError('Native select normalization failed on real saved page')
    fixture=dict(steps=steps,spec=dict(requested_outcome=rule,must_have=[rule]),expected_count=2)
    proof=dict(kind='saved real page and real model count diagnostic; not product acceptance',
               fixture=fixture,fixture_sha256=hashlib.sha256(json.dumps(fixture,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
               source_sha256=hashlib.sha256(page.read_bytes()).hexdigest(),intended_steps=intended_steps,models={k:cfg[k] for k in ('model','qa_mapping_model','qa_oracle_model')},passed=False)
    original=app.ai_json;calls=[]
    def recorded(prompt,config,tokens,**kw):
        start=time.monotonic();row=dict(model=config['model'],prompt=prompt,schema=kw.get('schema'))
        validator=kw.get('validator')
        if validator:
            def capture(value):
                row['raw_answer']=value
                return validator(value)
            kw['validator']=capture
        try:
            answer=original(prompt,config,tokens,**kw);row['answer']=answer;return answer
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc);raise
        finally:
            row['seconds']=round(time.monotonic()-start,2);calls.append(row)
            (evidence/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
    app.ai_json=recorded
    try:
        answer=app.qa_reference_count_oracle(dict(steps=steps,exact_check=dict(selector='#recordCount',value='untrusted')),
                    {},fixture['spec'],cfg,evidence,'two-records',[])
        proof['model_result']=answer
        if answer is None or answer['exact_check']['value']!='2':raise AssertionError('Reference mapping differs from fixed two-record fixture')
        if [x['effect'] for x in answer['reference_count']['trace']]!=['create','create']:raise AssertionError('Both saves must create records')
        if any(c['model']=='qwen2.5-coder:7b' for c in calls):raise AssertionError('Semantic role leaked to coding planner')
        # Exercise the new native-control grammar with a real model, then
        # execute its returned operations against the unchanged saved HTML.
        inventory=app.compact_qa_inventory(source)
        step_schema=app.qa_bound_step_schema(app.qa_unit_schema(1,'workflow')['properties']['steps']['items'],inventory,'workflow')
        native_schema=dict(type='object',properties=dict(steps=dict(type='array',minItems=6,maxItems=6,items=step_schema)),required=['steps'],additionalProperties=False)
        intended=steps[:6]
        expected_inputs={s['selector']:(s['op'],s.get('value')) for s in intended if s['op']!='click'}
        def validate_native(value):
            actual=value.get('steps',[]) if isinstance(value,dict) else []
            inputs={s.get('selector'):(s.get('op'),s.get('value')) for s in actual if isinstance(s,dict) and s.get('op')!='click'}
            clicks=[(s.get('op'),s.get('selector')) for s in actual if isinstance(s,dict) and s.get('op')=='click']
            if len(actual)!=6 or any(s.get('nth',0)!=0 for s in actual) or inputs!=expected_inputs or clicks!=[('click','#saveRecord')] or actual[-1].get('op')!='click':
                raise AssertionError('Model changed the fixed input values or failed to submit the required form')
            app.validate_qa_inventory_actions(value,inventory,'workflow')
            return value
        native=app.ai_json('実画面の型に沿って、指定した1件だけを入力し最後に保存する。JSON {steps:[操作]}。選択欄にはselect、日付や数値入力にはfill。入力値を変更しない。\n指定入力と保存操作:'+json.dumps(intended,ensure_ascii=False),
                    dict(cfg,model=cfg['qa_oracle_model'],_schema_in_prompt=False,_bounded_json_retry=True),500,schema=native_schema,max_attempts=1,request_timeout=300,validator=validate_native)
        proof['native_schema_plan']=native
        proof['native_schema_browser']=[]
        bound_primary=None
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            try:
                for width in (1280,390):
                    context=browser.new_context(viewport=dict(width=width,height=900));tab=context.new_page()
                    tab.goto(page.as_uri(),wait_until='load');tab.evaluate('localStorage.clear()');tab.reload()
                    for operation in native['steps']:
                        control=tab.locator(operation['selector'])
                        if operation['op']=='fill':control.fill(operation['value'])
                        elif operation['op']=='select':control.select_option(operation['value'])
                        else:control.click()
                    if bound_primary is None:
                        contract=app.capture_qa_display_contracts(tab).get('#summaryValue')
                        if not contract or contract.get('slots')!=2:raise AssertionError('Saved returns summary must expose its count and overdue count')
                        formats={'#summaryValue':contract}
                        year=tab.evaluate('new Date().getFullYear()')
                        if year>=2035:raise AssertionError('The fixed future-deadline fixture must be refreshed')
                        component_context='空の保存領域から指定の返品記録1件を保存した。集計は全保存件数と期限超過件数。期限2035-12-31、状態は返送待ち。現在の実行年:'+str(year)+'。対象CSSは#summaryValue。'
                        def component(name,prompt,schema,check,dependency):
                            return app.ai_json(prompt,dict(cfg,model=cfg['qa_oracle_model'],_schema_in_prompt=True,_bounded_json_retry=True,
                                _json_transport_evidence=str(evidence/(name+'-transport.json'))),180 if 'audit' in name else 100 if 'projection' in name else 120,schema=schema,max_attempts=1,request_timeout=300,validator=check)
                        summary_rule=rule+' summaryValueは全保存記録件数と、対応期限が今日より前の期限超過件数を表示する。'
                        aggregate_cfg=dict(cfg,_qa_reference_clock=dict(date=tab.evaluate('new Date().toISOString().slice(0,10)')))
                        bound=app.qa_reference_primary_expectation(dict(result_selector='#summaryValue',steps=native['steps']),formats,
                            dict(requested_outcome=summary_rule,must_have=[summary_rule]),aggregate_cfg,inventory,evidence,'one-record-summary',component)
                        if bound['exact_check']['value']!='1件 / 超過0件':raise AssertionError('Primary oracle differs from fixed one-record future-deadline result')
                        proof['bound_primary_model']=bound;bound_primary=bound['exact_check']['value']
                    for state in ('saved','reloaded'):
                        if state=='reloaded':tab.reload()
                        actual=tab.locator('#recordCount').inner_text().strip()
                        summary=tab.locator('#summaryValue').inner_text().strip()
                        proof['native_schema_browser'].append(dict(width=width,state=state,expected='1',actual=actual,expected_summary=bound_primary,actual_summary=summary))
                        if actual!='1':raise AssertionError('Native model operations failed independent one-record count')
                        if summary!=bound_primary:raise AssertionError('Bound primary oracle failed actual saved-page summary comparison')
                    tab.screenshot(path=str(evidence/f'native-model-{width}.png'),full_page=True);context.close()
            finally:browser.close()
        # This existing independent Chromium probe uses precisely the same inputs.
        # Its expected values are fixed, never copied from the model or app.
        runpy.run_path(str(Path(__file__).with_name('returns_oracle_probe.py')),run_name='__main__')
        browser=json.loads((root/'independent-count-probe.json').read_text(encoding='utf-8'))
        proof['browser']=browser
        if not browser['passed']:raise AssertionError('Saved real page failed independent Chromium probe')
        proof['passed']=True
    except Exception as exc:
        proof['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        app.ai_json=original
        (evidence/'result.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print('SAVED_COUNT_MODEL_RESULT',json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
