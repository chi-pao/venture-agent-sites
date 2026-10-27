"""Independent QA planning in bounded, resumable units, not renderer-derived tests."""
import ast
import decimal
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime as qa_datetime, date as qa_date

CHECKPOINT_QA_POLICY = '2026-10-26-single-scenario-4'


def qa_retry_models(cfg, failure):
    """Switch only failed units to a configured alternative; retain gates."""
    primary=str(cfg.get('model') or '')
    oracle=str(cfg.get('qa_oracle_model') or primary)
    alternate=str(cfg.get('qa_alternate_model') or cfg.get('code_model') or '')
    if not isinstance(failure,dict) or not failure.get('error') or not alternate:
        return primary,oracle
    # An environment transport problem is not model-quality evidence. Keep
    # its existing retry path instead of silently switching providers.
    detail=str(failure['error'])
    if re.search(r'HTTP\s*Error\s*(?:401|403|404)|ConnectionError',detail,re.I):return primary,oracle
    last=str(failure.get('model') or primary)
    last_oracle=str(failure.get('oracle_model') or oracle)
    model=alternate if alternate!=primary and last!=alternate else primary
    oracle_model=alternate if alternate!=oracle and last_oracle!=alternate else oracle
    return model,oracle_model


def qa_unit_schema(count,kind):
    step={'type':'object','properties':{
        'op':{'type':'string','enum':['fill','click','select','check','reload','wait','download_csv','download_json','restore_file','restore_invalid','cancel_restore']},
        'selector':{'type':'string','maxLength':180},'value':{'type':['string','integer','boolean']},
        'label':{'type':'string','maxLength':100},'nth':{'type':'integer','minimum':0,'maximum':30},
        'contains':{'type':'array','minItems':2,'maxItems':8,'items':{'type':'string','maxLength':100}}},
        'required':['op'],'additionalProperties':False}
    check={'type':'object','properties':{
        'op':{'type':'string','enum':['text_equals','text_contains','value_equals','count','invalid','visible']},
        'selector':{'type':'string','maxLength':180},'value':{'type':['string','integer','boolean']},
        'nth':{'type':'integer','minimum':0,'maximum':30}},'required':['op','selector'],'additionalProperties':False}
    required=['steps','checks','acceptance','rationale']+(['exact_check'] if kind in ('workflow','variant','feature') else [])+(['result_selector'] if kind=='workflow' else [])
    exact_check={'type':'object','properties':{'op':{'type':'string','enum':['text_equals']},'selector':{'type':'string','maxLength':180},'value':{'type':'string','minLength':1,'maxLength':250}},'required':['op','selector','value'],'additionalProperties':False}
    return {'type':'object','properties':{
        'steps':{'type':'array','minItems':1,'maxItems':24,'items':step},
        'checks':{'type':'array','minItems':2,'maxItems':8,'items':check},
        'acceptance':{'type':'array','items':{'type':'integer','minimum':0,'maximum':max(0,count-1)}},
        'exact_check':exact_check,'rationale':{'type':'string','maxLength':180},'result_selector':{'type':'string','maxLength':180},
        'blocked_features':{'type':'array','minItems':1,'maxItems':5,'items':{'type':'string','maxLength':160}}},
        'required':required,'additionalProperties':False}


def qa_roundtrip_schema(count):
    unit=qa_unit_schema(count,'roundtrip')
    props=unit['properties']
    return {'type':'object','properties':{
        'csv_selector':{'type':'string','minLength':1,'maxLength':180},
        'csv_contains':{'type':'array','minItems':2,'maxItems':8,'items':{'type':'string','minLength':1,'maxLength':100}},
        'json_selector':{'type':'string','minLength':1,'maxLength':180},
        'restore_selector':{'type':'string','minLength':1,'maxLength':180},
        'confirmation_mode':{'type':'string','enum':['native','inline']},'cancel_selector':{'type':'string','maxLength':180},
        'mutation_steps':props['steps'],'confirmation_steps':{'type':'array','maxItems':3,'items':props['steps']['items']},
        'checks':props['checks'],'acceptance':props['acceptance'],'rationale':props['rationale'],
        'blocked_features':props['blocked_features']},
        'required':['csv_selector','csv_contains','json_selector','restore_selector','mutation_steps','checks','acceptance','rationale'],
        'additionalProperties':False}


def compile_qa_roundtrip(value,count):
    if not isinstance(value,dict):raise AutoQAPlanError('復元検査の対象と変更操作をJSONで指定してください')
    if value.get('blocked_features'):raise AutoQAPlanError('実装不足: '+str(value['blocked_features']))
    for key in ('csv_selector','json_selector','restore_selector'):
        if not isinstance(value.get(key),str) or not value[key].strip():raise AutoQAPlanError('復元検査の実画面CSSが必要: '+key)
    mutation=value.get('mutation_steps')
    if not isinstance(mutation,list) or not 2<=len(mutation)<=14 or not {'fill','click'}<={x.get('op') for x in mutation if isinstance(x,dict)}:
        raise AutoQAPlanError('mutation_stepsに別の記録Cを入力・保存する操作が必要です')
    if any(not isinstance(x,dict) or x.get('op') not in ('fill','select','check','click','wait') for x in mutation):raise AutoQAPlanError('変更操作に出力や復元を混ぜないでください')
    confirm=value.get('confirmation_steps',[])
    if not isinstance(confirm,list) or len(confirm)>3 or any(not isinstance(x,dict) or x.get('op')!='click' for x in confirm):raise AutoQAPlanError('画面内の復元確定操作はclickだけを指定してください')
    mode=value.get('confirmation_mode','inline' if confirm else 'native')
    if mode not in ('native','inline'):raise AutoQAPlanError('復元確認方式はnativeまたはinlineです')
    if mode=='inline' and (not confirm or not isinstance(value.get('cancel_selector'),str) or not value['cancel_selector']):raise AutoQAPlanError('画面内復元にはcancel_selectorとconfirmation_stepsが必要です')
    restore=value['restore_selector']
    steps=[dict(op='download_csv',selector=value['csv_selector'],contains=value.get('csv_contains')),dict(op='download_json',selector=value['json_selector'])]+mutation
    # The harness handles real downloaded bytes, local storage snapshots and
    # native confirm dismissal. The model does not invent this protocol.
    if mode=='inline':
        steps += [dict(op='restore_file',selector=restore),dict(op='cancel_restore',selector=value['cancel_selector'],inline=True),dict(op='restore_file',selector=restore)]+confirm
    else:steps += [dict(op='cancel_restore',selector=restore),dict(op='restore_file',selector=restore),dict(op='restore_file',selector=restore)]
    return validate_qa_unit(dict(steps=steps,checks=value.get('checks'),acceptance=value.get('acceptance'),rationale=value.get('rationale')),'roundtrip',count)


def qa_invalid_schema(count):
    props=qa_unit_schema(count,'invalid')['properties']
    return {'type':'object','properties':{'restore_selector':{'type':'string','minLength':1,'maxLength':180},
        'invalid_steps':props['steps'],'checks':props['checks'],'acceptance':props['acceptance'],'rationale':props['rationale']},
        'required':['restore_selector','invalid_steps','checks','acceptance','rationale'],'additionalProperties':False}


def compile_qa_invalid(value,count):
    if not isinstance(value,dict) or not isinstance(value.get('restore_selector'),str) or not value['restore_selector']:raise AutoQAPlanError('不正ファイル検査のrestore_selectorが必要です')
    steps=value.get('invalid_steps')
    if not isinstance(steps,list) or any(not isinstance(x,dict) or x.get('op') not in ('fill','select','click','wait') for x in steps):raise AutoQAPlanError('invalid_stepsは実際の誤入力と送信操作だけを指定してください')
    return validate_qa_unit(dict(steps=[dict(op='restore_invalid',selector=value['restore_selector'])]+steps,
        checks=value.get('checks'),acceptance=value.get('acceptance'),rationale=value.get('rationale')),'invalid',count)


class _QAInventory(HTMLParser):
    def __init__(self):
        super().__init__();self.nodes=[];self.stack=[];self.labels={};self.label_for=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.stack.append((tag,a));node=None
        if tag=='label':self.label_for=a.get('for')
        if tag=='option':
            parent=next((v.get('id') for t,v in reversed(self.stack[:-1]) if t=='select'),None)
            select=next((n for n in reversed(self.nodes) if n['selector']=='#'+str(parent)),None)
            if select is not None:select.setdefault('options',[]).append(dict(value=a.get('value'),label=''))
        if tag in ('input','select','textarea','button') or a.get('id'):
            selector='#'+a['id'] if a.get('id') else ''
            if not selector:
                ancestor=next((v.get('id') for t,v in reversed(self.stack[:-1]) if v.get('id')),None)
                if ancestor:selector='#'+ancestor+' '+tag
            if selector:
                node=dict(tag=tag,selector=selector)
                form_id=a.get('form') or next((v.get('id') for t,v in reversed(self.stack[:-1]) if t=='form' and v.get('id')),None)
                if form_id:node['form']='#'+form_id
                for key in ('type','value','placeholder','min','max','required','name'):
                    if key in a:node[key]=a[key] if a[key] is not None else True
                self.nodes.append(node)
        # Track text owners separately. Void controls do not own following text.
        if tag in ('input','br','meta','link','img','hr'):self.stack.pop()
    def handle_endtag(self,tag):
        if tag=='label':self.label_for=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):
        if any(t in ('script','style','head','template','svg') for t,a in self.stack):return
        value=' '.join(data.split())
        if not value:return
        if self.label_for:self.labels[self.label_for]=(self.labels.get(self.label_for,'')+' '+value).strip()[:100]
        owner=next((a.get('id') for t,a in reversed(self.stack) if a.get('id')),None)
        if self.stack and self.stack[-1][0]=='button' and not self.stack[-1][1].get('id') and owner:
            button=next((n for n in reversed(self.nodes) if n['selector']=='#'+owner+' button'),None)
            if button:button['text']=(button.get('text','')+' '+value).strip()[:100]
        if owner:
            node=next((n for n in reversed(self.nodes) if n['selector']=='#'+owner),None)
            if node:
                node['text']=(node.get('text','')+' '+value).strip()[:100]
                if self.stack and self.stack[-1][0]=='option' and node.get('options'):
                    node['options'][-1]['label']=(node['options'][-1]['label']+' '+value).strip()[:100]


def compact_qa_inventory(page):
    parser=_QAInventory();parser.feed(page);parser.close()
    for node in parser.nodes:
        key=node['selector'].removeprefix('#')
        if key in parser.labels:node['label']=parser.labels[key]
    # Keep controls first and reserve space for concrete result/container IDs.
    controls=[n for n in parser.nodes if n['tag'] in ('input','select','textarea','button')]
    outputs=[n for n in parser.nodes if n not in controls]
    # Prefer inner nodes over a giant main/root that repeats the entire screen.
    outputs.sort(key=lambda n:(not bool(re.search(r'result|summary|total|count|message|rows|balance|actual|planned|capacity',n['selector'],re.I)),n['tag'] not in ('output','span','strong','p','tbody','div')))
    return dict(controls=controls[:32],outputs=outputs[:20])


def qa_resolve_unique_date_selector(value, inventory):
    """Repair a missing selector only when one unused date input is unambiguous."""
    if not isinstance(value, dict) or not isinstance(value.get('steps'), list):
        return value
    steps = [dict(step) if isinstance(step, dict) else step for step in value['steps']]
    used = {step.get('selector') for step in steps if isinstance(step, dict) and step.get('selector')}
    missing = [step for step in steps if isinstance(step, dict) and step.get('op') == 'fill'
               and not step.get('selector') and isinstance(step.get('value'), str)
               and re.fullmatch(r'\d{4}-\d{2}-\d{2}', step['value'])]
    candidates = [node['selector'] for node in inventory['controls']
                  if node.get('tag') == 'input' and node.get('type') == 'date'
                  and node.get('selector') and node['selector'] not in used]
    if len(missing) == 1 and len(candidates) == 1:
        missing[0]['selector'] = candidates[0]
    return dict(value, steps=steps)


def validate_qa_unit(value,kind,acceptance_count):
    if not isinstance(value,dict):raise AutoQAPlanError('検査1件のJSONオブジェクトが必要です')
    if value.get('blocked_features'):raise AutoQAPlanError('実装不足: '+' / '.join(map(str,value['blocked_features'])))
    value=dict(value)
    steps=value.get('steps');checks=value.get('checks');covers=value.get('acceptance')
    exact=value.pop('exact_check',None)
    if exact is not None:
        if not isinstance(exact,dict) or exact.get('op')!='text_equals':raise AutoQAPlanError('exact_check.opはtext_equalsにしてください')
        if isinstance(checks,list):
            checks=[exact]+[c for c in checks if c!=exact]
            value['checks']=checks
    if not isinstance(steps,list) or not 1<=len(steps)<=24 or not isinstance(checks,list) or not 2<=len(checks)<=8:
        raise AutoQAPlanError('検査1件には操作1〜24件と期待結果2〜8件が必要です')
    if not isinstance(covers,list) or any(type(i)is not int or not 0<=i<acceptance_count for i in covers):
        raise AutoQAPlanError('acceptanceは0始まり整数だけの配列（例:[0,1]）。条件オブジェクト・文字列は禁止。実際の値: '+json.dumps(covers,ensure_ascii=False)[:400])
    selector=lambda s:isinstance(s,str) and 1<=len(s)<=180 and not re.search(r'^(?:html|body|\*|xpath=)|>>|javascript:',s,re.I)
    allowed={'fill','click','select','check','reload','wait','download_json','download_csv','restore_file','restore_invalid','cancel_restore'}
    for index,step in enumerate(steps):
        if not isinstance(step,dict) or step.get('op') not in allowed:raise AutoQAPlanError('不正な検査操作')
        if step['op'] not in ('reload','wait') and not selector(step.get('selector')):
            raise AutoQAPlanError('操作対象が不正です。steps['+str(index)+']の'+str(step['op'])+'に実画面のselectorを同じオブジェクトで指定してください: '+json.dumps(step,ensure_ascii=False)[:300])
        if step['op']=='download_csv' and (not isinstance(step.get('contains'),list) or not 2<=len(step['contains'])<=8 or any(not isinstance(v,str) or not 1<=len(v)<=100 for v in step['contains'])):raise AutoQAPlanError('CSVの照合値が2件以上必要です')
        if len(str(step.get('value','')))>300:raise AutoQAPlanError('入力値が長すぎます')
        if step['op']=='wait' and (type(step.get('value'))is not int or not 100<=step['value']<=10000):raise AutoQAPlanError('待機時間が不正です')
        if 'nth' in step and (type(step['nth'])is not int or not 0<=step['nth']<=30):raise AutoQAPlanError('要素番号が不正です')
    for check in checks:
        if not isinstance(check,dict) or not selector(check.get('selector')) or check.get('op') not in ('text_equals','text_contains','value_equals','count','invalid','visible'):
            raise AutoQAPlanError('期待結果の形式が不正です')
        if check['op'] in ('text_equals','text_contains','value_equals') and (not isinstance(check.get('value'),str) or not 1<=len(check['value'])<=250):raise AutoQAPlanError('具体的な期待値が必要です')
        if check['op']=='count' and type(check.get('value'))is not int:raise AutoQAPlanError('件数の正解は整数が必要です')
    # Assertions on the very same element must not contradict each other.
    for i, left in enumerate(checks):
        for right in checks[i+1:]:
            if left.get('selector') != right.get('selector') or left.get('nth', 0) != right.get('nth', 0):continue
            if left['op'] == 'text_equals' and right['op'] == 'text_equals' and left['value'] != right['value']:
                raise AutoQAPlanError('同じ要素の完全一致の期待値が矛盾しています: '+left['selector'])
            if left['op'] == 'text_equals' and right['op'] == 'text_contains' and right['value'] not in left['value']:
                raise AutoQAPlanError('同じ要素の完全一致と部分一致の期待値が矛盾しています: '+left['selector'])
            if right['op'] == 'text_equals' and left['op'] == 'text_contains' and left['value'] not in right['value']:
                raise AutoQAPlanError('同じ要素の完全一致と部分一致の期待値が矛盾しています: '+left['selector'])
    ops={s['op'] for s in steps}
    if kind in ('workflow','variant','feature') and (not {'fill','click'}<=ops or not any(c['op']=='text_equals' for c in checks)):
        raise AutoQAPlanError('入力・実行・正解の完全一致が必要です')
    if kind=='workflow' and not selector(value.get('result_selector')):raise AutoQAPlanError('主結果の要素が必要です')
    if kind=='reload' and 'reload' not in ops:raise AutoQAPlanError('再読込操作が必要です')
    if kind=='roundtrip' and not {'download_json','download_csv','restore_file','cancel_restore','fill','click'}<=ops:raise AutoQAPlanError('出力・変更・復元・キャンセルを検査してください')
    if kind=='invalid' and not {'restore_invalid','fill','click'}<=ops:raise AutoQAPlanError('不正ファイルと誤入力を検査してください')
    return value


def qa_unsubmitted_forms(value, inventory):
    controls=inventory['controls']
    by_selector={n['selector']:n for n in controls}
    filled={by_selector[s['selector']]['form'] for s in value.get('steps',[]) if s.get('op') in ('fill','select') and s.get('selector') in by_selector and by_selector[s['selector']].get('form')}
    clicked={s.get('selector') for s in value.get('steps',[]) if s.get('op')=='click'}
    missing=[]
    for form in filled:
        buttons=[n['selector'] for n in controls if n.get('form')==form and n['tag']=='button' and n.get('type','submit')=='submit' and ' ' not in n['selector']]
        if buttons and not clicked.intersection(buttons):missing.append((form,buttons))
    return missing


def repair_qa_invalid_submission(raw, observation, inventory, cfg):
    """Repair only controls rejected by Chromium, preserving the oracle."""
    steps=raw.get('steps',[]) if isinstance(raw,dict) else []
    failed=observation.get('invalid_fields',[]) if isinstance(observation,dict) else []
    operation=observation.get('operation',{}) if isinstance(observation,dict) else {}
    if not failed or len(failed)>8 or operation.get('op')!='click' or steps!=observation.get('steps'):return None
    targets=[f.get('selector') for f in failed if isinstance(f,dict)]
    if len(targets)!=len(failed) or len(set(targets))!=len(targets):return None
    nodes={n['selector']:n for n in inventory['controls']}
    if any(t not in nodes or nodes[t].get('tag') not in ('input','select','textarea') for t in targets):return None
    clicks=[i for i,s in enumerate(steps) if s==operation]
    if len(clicks)!=1 or len(steps)+len(targets)>24:return None
    schema={'type':'object','properties':{'inputs':{'type':'array','minItems':len(targets),'maxItems':len(targets),'items':{'type':'object','properties':{'selector':{'type':'string','enum':targets},'value':{'type':'string','minLength':1,'maxLength':100}},'required':['selector','value'],'additionalProperties':False}}},'required':['inputs'],'additionalProperties':False}
    prompt=('独立QA。ブラウザが送信を拒否した必須項目だけを埋める。既存の操作・期待値は変更しない。'
        '入力済みの値と整合する具体値を決め、selectは提示されたoptionのvalueを使う。JSON {"inputs":[{"selector":"CSS","value":"値"}]}のみ返す。'
        '\n拒否された項目:'+json.dumps([nodes[t] for t in targets],ensure_ascii=False)
        +'\n既存操作:'+json.dumps(steps,ensure_ascii=False,separators=(',',':')))
    def validate(answer):
        items=answer.get('inputs') if isinstance(answer,dict) else None
        if not isinstance(items,list) or len(items)!=len(targets) or any(not isinstance(i,dict) for i in items) or {i.get('selector') for i in items}!=set(targets):raise AutoQAPlanError('拒否された項目それぞれに値が必要です')
        additions=[]
        for item in items:
            node=nodes[item['selector']];v=item.get('value')
            if not isinstance(v,str) or not v or len(v)>100:raise AutoQAPlanError('必須項目に有効な値が必要です')
            if node['tag']=='select':
                if v not in [o.get('value') for o in node.get('options',[]) if o.get('value')]:raise AutoQAPlanError('選択値は該当要素のoptionから指定してください')
                op='select'
            elif node.get('type') in ('file','checkbox','radio','button','submit'):raise AutoQAPlanError('自動で補えない必須項目です')
            else:op='fill'
            additions.append(dict(op=op,selector=item['selector'],value=v))
        i=clicks[0]
        return dict(raw,steps=steps[:i]+additions+steps[i:])
    return ai_json(prompt,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),450,schema=schema,max_attempts=2,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)


def validate_qa_inventory_actions(value,inventory,kind):
    nodes=inventory['controls']+inventory['outputs']
    for step in value.get('steps',[]):
        op=step['op'];selector=step.get('selector','')
        target=next((n for n in nodes if n['selector']==selector),None)
        if not target:continue  # Dynamic controls are checked by the real browser.
        tag=target['tag'];typ=target.get('type','')
        if op=='check' and not (tag=='input' and typ in ('checkbox','radio')):
            raise AutoQAPlanError('checkはcheckbox/radioだけです: '+selector+' は '+tag+'/'+typ+'。表示の照合はchecksへ記述してください')
        if op=='fill' and (tag not in ('input','textarea') or typ in ('file','checkbox','radio','button','submit')):
            raise AutoQAPlanError('実画面の要素に合わない操作: fill '+selector+' は '+tag+'/'+typ+'。選択欄にはselectを使ってください')
        if op=='fill' and typ=='number':
            raw=step.get('value')
            try:
                if isinstance(raw,bool) or raw is None or not decimal.Decimal(str(raw)).is_finite():raise ValueError()
            except (decimal.InvalidOperation,ValueError):
                raise AutoQAPlanError('数値入力欄 '+selector+' に時刻や文字列は入力できません。画面ラベルと要件の単位を確認し数値で入力してください: '+str(raw)[:80])
        if op=='select' and tag!='select':raise AutoQAPlanError('selectは選択欄だけです: '+selector)
        if op=='click' and typ=='file':raise AutoQAPlanError('ファイル入力へclickはできません。復元専用の検査を使用: '+selector)
        if kind in ('workflow','variant') and op in ('download_csv','download_json','restore_file','restore_invalid','cancel_restore'):
            raise AutoQAPlanError('中心作業の検査にバックアップ検査を混ぜないでください')
    missing=qa_unsubmitted_forms(value,inventory) if kind in ('workflow','variant','feature') else []
    if missing:raise AutoQAPlanError('入力したフォームが未送信です。必要な項目を入力し送信ボタンを操作してください: '+str(missing))
    return value


def qa_display_contracts_from_nodes(nodes):
    contracts={}
    for node in nodes:
        text=str(node.get('text','')).strip();selector=node.get('selector','')
        if not selector.startswith('#') or not text or len(text)>180:continue
        slots=[]
        def slot(match):
            key='{n'+str(len(slots))+'}';slots.append(key);return key
        template=re.sub(r'-?\d+(?:\.\d+)?',slot,text)
        if not 1<=len(slots)<=8:continue
        label=re.sub(r'-?\d+(?:\.\d+)?','数値',str(node.get('label','')))[:80]
        contracts[selector]=dict(template=template,slots=len(slots),label=label)
        if len(contracts)>=24:break
    return contracts


def capture_qa_display_contracts(page):
    nodes=page.evaluate("""() => [...document.querySelectorAll('[id]')].filter(e=>!['INPUT','SELECT','TEXTAREA','BUTTON','SCRIPT','STYLE'].includes(e.tagName)).map(e=>({selector:'#'+e.id,text:e.innerText||'',label:e.closest('section')?.querySelector('h2,h3')?.innerText||e.getAttribute('aria-label')||''})).filter(e=>e.text.length<=180)""")
    return qa_display_contracts_from_nodes(nodes)


def compile_qa_formatted_expectation(value,formats):
    if not isinstance(value,dict):return value
    exact=value.get('exact_check')
    if not isinstance(exact,dict) or 'expected_values' not in exact:return value
    contract=formats.get(exact.get('selector'))
    if not contract:raise AutoQAPlanError('表示書式の取得先にないselectorです')
    values=exact['expected_values']
    if not isinstance(values,list) or len(values)!=contract['slots'] or any(not isinstance(v,str) or not re.fullmatch(r'-?\d+(?:\.\d+)?',v) for v in values):
        raise AutoQAPlanError('expected_valuesには仕様から計算した数値文字列を表示順に'+str(contract['slots'])+'件指定してください')
    literals=exact.get('expected_literals')
    if not isinstance(literals,list) or len(literals)!=len(values)+1 or any(not isinstance(v,str) or len(v)>180 for v in literals):
        raise AutoQAPlanError('expected_literalsに数値の前後の期待文字列を全て指定してください。業務状態の文言も観測値を自動採用しません')
    text=literals[0]+''.join(v+literals[i+1] for i,v in enumerate(values))
    # Both numbers and surrounding business-state text come from independent
    # QA. The observed template is guidance only, never an automatic oracle.
    return dict(value,exact_check=dict(op='text_equals',selector=exact['selector'],value=text))


def qa_independent_date_facts(steps, reference_clock):
    # Inputs and the test environment, never observed product outputs.
    try: reference=qa_date.fromisoformat(reference_clock['date'])
    except (KeyError,TypeError,ValueError):return []
    facts=[]
    for step in steps:
        value=step.get('value') if isinstance(step,dict) else None
        if not isinstance(step,dict) or step.get('op')!='fill' or not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):continue
        try:entered=qa_date.fromisoformat(value)
        except ValueError:continue
        delta=(entered-reference).days
        facts.append(dict(selector=step.get('selector',''),input_date=value,reference_date=reference.isoformat(),days_from_reference=delta,relation='before' if delta<0 else 'after' if delta>0 else 'same'))
    return facts[:12]


def qa_action_timeline(prior, current):
    # Count attempted actions only. A click can edit, fail validation, or be
    # cancelled, so its count is never treated as a count of saved records.
    counts = {}
    for phase, steps in [('prior', [s for row in prior for s in row.get('steps', [])]), ('current', current)]:
        for step in steps:
            if not isinstance(step, dict) or step.get('op') != 'click':
                continue
            selector = step.get('selector')
            if not isinstance(selector, str) or not selector:
                continue
            item = counts.setdefault(selector, {'prior': 0, 'current': 0})
            item[phase] += 1
    return [{'selector': selector, **count} for selector, count in sorted(counts.items())][:24]


def qa_independent_input_history(prior, current):
    """Summarize specified field inputs, without claiming any were saved.

    This deliberately records operations rather than product results; a repeated
    click may edit, fail validation or delete a record. No business conclusion is
    derived from the number of inputs alone.
    """
    items=[]
    phases=[('prior', [s for row in prior for s in row.get('steps', [])]), ('current', current)]
    for phase, steps in phases:
        for step in steps:
            if not isinstance(step,dict) or step.get('op') not in ('fill','select','check'):continue
            selector=step.get('selector')
            if not isinstance(selector,str) or not selector:continue
            item={'phase':phase,'op':step['op'],'selector':selector}
            for k in ('value','label'):
                if k in step and isinstance(step[k],(str,int,bool)):item[k]=step[k]
            items.append(item)
    return items[:48]


def qa_validate_declared_calculations(value, spec, scenario_kind):
    """Verify explicit requirement-side formulas using supplied test inputs.

    The input values and formula come from the test and requirement contract,
    never from browser output. Missing/invalid data is an error rather than a
    pass. Products without explicit formula contracts receive no such claim.
    """
    contracts=spec.get('independent_calculations',[])
    if not isinstance(contracts,list):raise AutoQAPlanError('独立計算の仕様形式が不正です')
    steps=value.get('steps',[]) if isinstance(value,dict) else []
    checks=value.get('checks',[]) if isinstance(value,dict) else []
    for contract in contracts:
        if not isinstance(contract,dict):raise AutoQAPlanError('独立計算の仕様が不正です')
        kind=contract.get('scenario_kind')
        if not isinstance(kind,str) or not kind:raise AutoQAPlanError('独立計算の対象シナリオが未定義です')
        if kind!=scenario_kind:continue
        bindings=contract.get('bindings');expression=contract.get('expression');output=contract.get('output_selector');template=contract.get('expected_template')
        if not isinstance(bindings,dict) or not bindings or not isinstance(expression,str) or not expression or not isinstance(output,str) or not output or not isinstance(template,str) or template.count('{value}')!=1 or template.replace('{value}','').find('{')>=0 or '}' in template.replace('{value}',''):
            raise AutoQAPlanError('独立計算の入力・式・出力・表示形式が不足しています')
        if len(bindings)>12 or len(expression)>180:raise AutoQAPlanError('独立計算の定義が大きすぎます')
        values={}
        for variable, selector in bindings.items():
            if not isinstance(variable,str) or not variable.isidentifier() or not isinstance(selector,str) or not selector:raise AutoQAPlanError('独立計算の入力定義が不正です')
            matches=[step.get('value') for step in steps if isinstance(step,dict) and step.get('op')=='fill' and step.get('selector')==selector]
            if len(matches)!=1 or isinstance(matches[0],bool) or not re.fullmatch(r'-?\d{1,12}(?:\.\d{1,6})?',str(matches[0])):raise AutoQAPlanError('独立計算に一意な数値入力がありません: '+selector)
            values[variable]=decimal.Decimal(str(matches[0]))
        try:node=ast.parse(expression,mode='eval')
        except (ValueError,SyntaxError):raise AutoQAPlanError('独立計算式を解釈できません')
        if sum(1 for _ in ast.walk(node))>40:raise AutoQAPlanError('独立計算式が複雑すぎます')
        def evaluate(n):
            if isinstance(n,ast.Expression):return evaluate(n.body)
            if isinstance(n,ast.Name) and n.id in values:return values[n.id]
            if isinstance(n,ast.Constant) and type(n.value) is int and abs(n.value)<=1000000:return decimal.Decimal(n.value)
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):
                v=evaluate(n.operand);return -v if isinstance(n.op,ast.USub) else v
            if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                a,b=evaluate(n.left),evaluate(n.right)
                if isinstance(n.op,ast.Add):return a+b
                if isinstance(n.op,ast.Sub):return a-b
                if isinstance(n.op,ast.Mult):return a*b
                return a/b
            raise AutoQAPlanError('独立計算式は数値・入力名と四則演算だけを使用できます')
        try:
            with decimal.localcontext() as ctx:
                ctx.prec=28
                result=evaluate(node)
        except (decimal.DecimalException,OverflowError,ZeroDivisionError):raise AutoQAPlanError('独立計算を実行できません')
        if not result.is_finite() or abs(result)>decimal.Decimal('1e15'):raise AutoQAPlanError('独立計算の結果が範囲外です')
        if result!=result.to_integral_value():raise AutoQAPlanError('小数の丸め規則が未定義です')
        expected=template.replace('{value}',format(result.quantize(decimal.Decimal(1)),'f'))
        actual=[c.get('value') for c in checks if isinstance(c,dict) and c.get('op')=='text_equals' and c.get('selector')==output]
        if len(actual)!=1 or actual[0]!=expected:raise AutoQAPlanError('独立計算と検査期待値が一致しません: '+output+'（仕様に基づく計算: '+expected+'）')
    return value


def qa_independent_clock_differences(steps):
    """Arithmetic on entered local HH:MM values, not business duration.

    This does not assume overnight shifts, breaks, successful submissions or
    which pair represents work; the specification must determine those rules.
    """
    clocks=[]
    for step in steps:
        if not isinstance(step,dict) or step.get('op') != 'fill':continue
        value=step.get('value')
        if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):continue
        hours,minutes=map(int,value.split(':'))
        clocks.append((step.get('selector',''),value,hours*60+minutes))
        if len(clocks)>=6:break
    return [dict(start_selector=a[0],start=a[1],end_selector=b[0],end=b[1],signed_minutes=b[2]-a[2])
            for i,a in enumerate(clocks) for b in clocks[i+1:]]


def repair_qa_exact_oracle(name,raw,formats,spec,cfg,folder,key,error):
    exact=raw.get('exact_check') if isinstance(raw,dict) else None
    if not isinstance(exact,dict) or exact.get('selector') not in formats:return None
    contract=formats[exact['selector']]
    # Repair a single assertion without the many numeric/literal fields that
    # confused the real model. Inputs/actions and other checks are immutable.
    schema={'type':'object','properties':{'expected_text':{'type':'string','minLength':1,'maxLength':250},
        'basis':{'type':'string','minLength':12,'maxLength':300}},'required':['expected_text','basis'],'additionalProperties':False}
    inputs=[{k:s[k] for k in ('op','selector','value','label','nth') if k in s} for s in raw.get('steps',[])]
    prior=cfg.get('_qa_prior_scenarios',[]) if key=='base-variant' else []
    prior=[dict(kind=row.get('kind',''),steps=[{k:step[k] for k in ('op','selector','value','label','nth') if k in step} for step in row.get('steps',[]) if isinstance(step,dict)],
                checks=[{k:check[k] for k in ('op','selector','value','nth') if k in check} for check in row.get('checks',[]) if isinstance(check,dict)]) for row in prior if isinstance(row,dict)]
    relevant=[spec['acceptance'][i] for i in raw.get('acceptance',[]) if type(i)is int and 0<=i<len(spec['acceptance'])]
    if any(phrase in error for phrase in ('対象要素は割合から始まります','主結果は割合から始まります')) and re.match(r'^\s*\{n0\}\s*[%％]',contract.get('template','')):
        # After a real-model format failure, request the independent numeric
        # answers and independent surrounding text separately. The observed
        # display supplies slot count only, never values or literal text.
        count=contract.get('slots')
        if type(count) is not int or not 1<=count<=8:return None
        schema={'type':'object','properties':{'expected_values':{'type':'array','minItems':count,'maxItems':count,'items':{'type':'string','minLength':1,'maxLength':30}},'expected_literals':{'type':'array','minItems':count+1,'maxItems':count+1,'items':{'type':'string','maxLength':180}},'basis':{'type':'string','minLength':12,'maxLength':300}},'required':['expected_values','expected_literals','basis'],'additionalProperties':False}
        prompt=('独立QA。観測した数値・状態を正解に使わず、要件と入力から数値と文字列を計算。'
            '見出しや一覧は含めない。JSON {"expected_values":["数値"],"expected_literals":["数値の前","数値の間","最後"],"basis":"根拠"}。'
            '数値は'+str(count)+'個、文字列は'+str(count+1)+'個。結果の先頭は割合の数値、続いて%を含める。'
            '\n要件:'+json.dumps(relevant,ensure_ascii=False)
            +'\n先行検査の入力と独立した期待値（実測値ではない。次の操作まで状態を保持し、根拠を要件から再計算）:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
            +'\n今回の操作:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':'))
            +'\n書式の参考（数値は未記載、正解ではない）:'+str(contract.get('template','')))
        def validate_parts(answer):
            if not isinstance(answer,dict) or not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('独立した計算根拠が不足しています')
            candidate=dict(raw,exact_check=dict(selector=exact['selector'],expected_values=answer.get('expected_values'),expected_literals=answer.get('expected_literals')))
            result=compile_qa_formatted_expectation(candidate,formats)
            if not re.match(r'^\s*-?\d+(?:\.\d+)?\s*[%％]',result['exact_check']['value']):raise AutoQAPlanError('expected_values: 主結果は割合から始まります。見出しを混ぜないでください')
            return dict(result,oracle_basis=answer['basis'])
        oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
        return ai_json(prompt,oracle_cfg,450,schema=schema,max_attempts=2,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate_parts)
    prompt=('独立QA。入力と操作は変更しない。主結果の完全な期待表示だけを、仕様から独立に計算して返す。'
        'JSON {"expected_text":"単位や補足も含む完全な期待文字列","basis":"入力からの計算式・根拠"}。'
        '数値を省略した表示書式の{n0},{n1}等を、入力から計算した数値に置き換える。必要な単位や文言を省略しない。'
        '指定selectorの要素だけの表示を返し、周囲の見出しや一覧を含めない。書式は画面資料であり、業務状態の正解ではない。状態文言も要件から判断する。観測した数値は渡さない。'
        '\n対象者:'+str(spec['audience'])+'\n要求する結果:'+str(spec['requested_outcome'])[:350]
        +'\n検査基準日（ブラウザの現地日付。期限判定はこの日と比較）:'+json.dumps(cfg.get('_qa_reference_clock',{}),ensure_ascii=False)
        +'\n日付の独立計算（前後の事実のみ。業務上の期限超過は仕様と状態から判断）:'+json.dumps(qa_independent_date_facts([step for row in prior for step in row['steps']]+raw.get('steps',[]),cfg.get('_qa_reference_clock',{})),ensure_ascii=False)
        +'\n入力時刻の差分（当日内の符号付き分差のみ。夜間・休憩・業務時間は要件で判断）:'+json.dumps(qa_independent_clock_differences([step for row in prior for step in row['steps']]+raw.get('steps',[])),ensure_ascii=False)
        +'\n先行操作（保存内容は引き継がれる。初期状態と誤認しない）:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
        +'\n開始状態:'+('workflowは空のブラウザ保存から開始。操作で指定されていない人数や記録を作らない。' if key=='base-workflow' else ('先行のworkflowが成功した状態を引き継ぐ。操作回数から成功した記録数を決めない。' if key=='base-variant' else '独立ケースは空のブラウザ保存から開始。操作で指定されていない人数や記録を作らない。'))
        +'\n独立した入力履歴（入力操作のみ。保存成功・存在人数は意味しない）:'+json.dumps(qa_independent_input_history(prior,inputs),ensure_ascii=False,separators=(',',':'))
        +'\nクリックの時系列集計（操作回数のみ。登録成功・件数を保証しない。編集、削除、入力エラーも仕様に基づいて判断）:'+json.dumps(qa_action_timeline(prior,inputs),ensure_ascii=False,separators=(',',':'))
        +'\n関連要件:'+json.dumps(relevant,ensure_ascii=False)+'\n入力と操作:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':'))
        +'\n数値を除去した表示書式:'+json.dumps(contract,ensure_ascii=False))
    def validate(answer):
        write_framework_json(folder/(key+'-oracle-last-response.json'),answer)
        if not isinstance(answer,dict) or not isinstance(answer.get('expected_text'),str) or not 1<=len(answer['expected_text'])<=250 or re.search(r'\{n\d+\}',answer['expected_text']):
            raise AutoQAPlanError('主結果の単位・補足まで含む完全な期待文字列が必要です')
        # A percentage marker in the observed format is presentation data,
        # not the value or business verdict. A missing percentage cannot be a
        # complete exact assertion; reject it instead of retrying the same
        # malformed oracle against Chromium indefinitely.
        if re.search(r'\{n\d+\}\s*[%％]',contract.get('template','')) and not re.search(r'\d\s*[%％]',answer['expected_text']):
            raise AutoQAPlanError('expected_values: 表示書式には割合の数値と%があります。入力と要件から割合を計算して完全な期待文字列に含めてください')
        # The observation describes this selector's display boundaries only.
        # Do not copy its values or state into the oracle. A percentage-first
        # element cannot be checked using a surrounding heading or a list.
        if re.match(r'^\s*\{n0\}\s*[%％]',contract.get('template','')) and not re.match(r'^\s*-?\d+(?:\.\d+)?\s*[%％]',answer['expected_text']):
            raise AutoQAPlanError('expected_values: 対象要素は割合から始まります。見出しや一覧を混ぜず、割合から始まる完全な期待値を仕様から計算してください')
        if not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('主結果の独立した計算根拠が不足しています')
        return dict(raw,oracle_basis=answer['basis'],exact_check=dict(op='text_equals',selector=exact['selector'],value=answer['expected_text']))
    oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
    repaired=ai_json(prompt,oracle_cfg,450,schema=schema,
        max_attempts=2,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate)
    write_framework_json(folder/(key+'-oracle-repair.json'),dict(source_steps_sha=hashlib.sha256(json.dumps(dict(prior=prior,current=inputs),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),value=repaired))
    return repaired


def repair_qa_conflicting_checks(raw, spec, cfg, folder, key, scenarios, formats=None):
    """Replan expected values only; never infer them from product output."""
    exact = raw.get('exact_check') if isinstance(raw, dict) else None
    checks = raw.get('checks') if isinstance(raw, dict) else None
    if not isinstance(exact, dict) or not isinstance(checks, list):return None
    indexes = [i for i, c in enumerate(checks) if isinstance(c, dict)
               and c.get('selector') == exact.get('selector') and c.get('nth', 0) == exact.get('nth', 0) and c.get('op') in ('text_equals','text_contains')]
    if not indexes:return None
    contains_indexes = [i for i in indexes if checks[i]['op'] == 'text_contains']
    schema = {'type':'object','properties':{'expected_text':{'type':'string','minLength':1,'maxLength':250},
        'replacement_values':{'type':'array','minItems':len(contains_indexes),'maxItems':len(contains_indexes),
                              'items':{'type':'string','minLength':1,'maxLength':250}},
        'basis':{'type':'string','minLength':12,'maxLength':300}},
        'required':['expected_text','replacement_values','basis'],'additionalProperties':False}
    prior = [{'kind': s.get('kind'), 'steps': s.get('steps',[])} for s in scenarios] if key == 'base-variant' else []
    relevant = [spec['acceptance'][i] for i in raw.get('acceptance',[]) if type(i) is int and 0 <= i < len(spec['acceptance'])]
    prompts = [{'op':checks[i]['op'],'selector':checks[i]['selector']} for i in contains_indexes]
    prompt = ('独立QA。保存された操作と対象要素は変えず、矛盾した期待値すべてを仕様・入力から再計算する。'
              '実際の画面結果は正解に使わない。JSON {expected_text:完全一致の期待値,replacement_values:指定順の期待値配列,basis:根拠}。'
              '同じ要素の部分一致は完全一致に含まれる値とする。対象要素以外の見出しを含めない。'
              '\n要求結果:'+str(spec.get('requested_outcome',''))[:400]+'\n対象要件:'+json.dumps(relevant,ensure_ascii=False)
              +'\n先行操作:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
              +'\n今回の操作:'+json.dumps(raw.get('steps',[]),ensure_ascii=False,separators=(',',':'))
              +'\n開始状態:'+('先行検査の保存状態を引き継ぐ。未指定のデータを仮定しない。' if key=='base-variant' else '空のブラウザ保存から開始。未指定の人数やデータを仮定しない。')
              +'\n独立した入力履歴（入力操作のみ。保存成功や人数を意味しない）:'+json.dumps(qa_independent_input_history(prior,raw.get('steps',[])),ensure_ascii=False,separators=(',',':'))
              +'\n入力時刻の差分（当日内の符号付き分差。夜間・休憩・業務時間は要件で判断）:'+json.dumps(qa_independent_clock_differences([step for row in prior for step in row['steps']]+raw.get('steps',[])),ensure_ascii=False)
              +'\n基準日時:'+json.dumps(cfg.get('_qa_reference_clock',{}),ensure_ascii=False)
              +'\n数値を除去した表示形式（値は仕様から計算）:'+json.dumps((formats or {}).get(exact.get('selector'),{}),ensure_ascii=False)
              +'\n部分一致の検証対象:'+json.dumps(prompts,ensure_ascii=False))
    def validate(answer):
        write_framework_json(folder/(key+'-conflict-last-response.json'),answer)
        values=answer.get('replacement_values') if isinstance(answer,dict) else None
        expected=answer.get('expected_text') if isinstance(answer,dict) else None
        if not isinstance(expected,str) or not expected or not isinstance(values,list) or len(values)!=len(contains_indexes) or any(not isinstance(v,str) or not v for v in values):
            raise AutoQAPlanError('期待値全体の再計算結果が不正です')
        if not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('期待値の根拠が不足しています')
        replacement=[dict(c) for c in checks]
        for i in indexes:
            if replacement[i]['op']=='text_equals':replacement[i]['value']=expected
        for i, value in zip(contains_indexes,values):
            if value not in expected:raise AutoQAPlanError('部分一致の期待値が矛盾しています')
            replacement[i]['value']=value
        return dict(raw, checks=replacement, oracle_basis=answer['basis'],
                    exact_check=dict(op='text_equals',selector=exact['selector'],value=expected))
    oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
    result=ai_json(prompt,oracle_cfg,600,schema=schema,max_attempts=1,
                   request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate)
    write_framework_json(folder/(key+'-conflict-repair.json'),result)
    return result


def repair_qa_literal_selector(raw,fault,inventory,cfg,folder,key):
    # This path may relocate a check for an exact literal the QA author entered
    # (e.g. a registered person's name). It may not change that expected value,
    # its comparison operator, or any product input/action.
    checks=raw.get('checks',[]) if isinstance(raw,dict) else []
    inputs=[s.get('value',s.get('label')) for s in raw.get('steps',[]) if s.get('op') in ('fill','select')]
    if not isinstance(fault,dict) or fault not in checks or fault.get('op')!='text_contains' or fault.get('value') not in inputs:return None
    options=[n['selector'] for n in inventory['outputs'] if n['selector']!=fault['selector'] and n['tag'] not in ('main','section','body','html','form','style','script')]
    if not options:return None
    schema={'type':'object','properties':{'selector':{'type':'string','enum':options},'reason':{'type':'string','minLength':12,'maxLength':200}},'required':['selector','reason'],'additionalProperties':False}
    def validate(answer):
        write_framework_json(folder/(key+'-selector-last-response.json'),answer)
        if not isinstance(answer,dict) or answer.get('selector') not in options or not isinstance(answer.get('reason'),str) or len(answer['reason'])<12:raise AutoQAPlanError('入力した文字列の表示先CSSと根拠が必要です')
        changed=[dict(c,selector=answer['selector']) if c==fault else dict(c) for c in checks]
        return dict(raw,checks=changed,selector_repair_reason=answer['reason'])
    return ai_json('独立QA。入力した文字列を別の表示欄で照合して失敗した。入力・操作・期待文字列・比較演算は変更しない。実際に登録内容を表示する出力先CSSを1つだけ選びJSON {selector:CSS,reason:選択根拠}を返す。説明通知と登録一覧を混同しない。'
        +'\n問題の検査:'+json.dumps(fault,ensure_ascii=False)+'\n入力操作:'+json.dumps(raw.get('steps',[]),ensure_ascii=False,separators=(',',':'))[:1800]
        +'\n出力先候補:'+json.dumps([n for n in inventory['outputs'] if n['selector'] in options],ensure_ascii=False,separators=(',',':'))[:2200],
        dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),250,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)


def qa_variant_repeats_workflow(value, scenarios):
    # A repeat of every input and action is not an input-difference test.
    # Compare the actions themselves, not the displayed or expected result.
    if not isinstance(value, dict) or not scenarios:
        return False
    prior = next((s for s in scenarios if s.get('kind') == 'workflow'), None)
    if not prior:
        return False
    def relevant(steps):
        return [{k: step[k] for k in ('op', 'selector', 'value', 'label', 'nth') if k in step}
                for step in steps if isinstance(step, dict) and step.get('op') in ('fill', 'select', 'check', 'click')]
    current = relevant(value.get('steps', []))
    return bool(current) and current == relevant(prior.get('steps', []))


def checkpointed_independent_qa_plan(name,page,cfg,spec,quotes):
    import time as qa_time
    inventory=compact_qa_inventory(page)
    full_inventory=inventory
    signature=hashlib.sha256(json.dumps(dict(policy=CHECKPOINT_QA_POLICY,name=name,spec=spec,
        source=hashlib.sha256(page.encode()).hexdigest(),model=cfg['model'],url=cfg['url']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder=OUT/'knowledge'/'qa-plan-parts'/signature;folder.mkdir(parents=True,exist_ok=True)
    acceptance=spec['acceptance'];count=len(acceptance)
    handoff=cfg.get('_department_documents') or {}
    design_plan=handoff.get('implementation_plan') or {}
    features=design_plan.get('features',[]) if isinstance(design_plan,dict) else []
    feature_contracts={f['acceptance_index']:f for f in features if isinstance(f,dict) and type(f.get('acceptance_index')) is int and 0<=f['acceptance_index']<count}
    minimal_spec=dict(audience=spec['audience'],outcome=str(spec['requested_outcome'])[:500],
        acceptance_by_index={str(i):c for i,c in enumerate(acceptance)})
    # Never cut a JSON structure halfway, or let a long control list hide all
    # result selectors. Both sections retain a separate bounded budget.
    def fit(items,limit):
        result=[]
        for node in items:
            if len(json.dumps(result+[node],sort_keys=True,ensure_ascii=False,separators=(',',':')))>limit:break
            result.append(node)
        return result
    # Required controls must not disappear behind optional controls when the
    # bounded prompt is packed. Keep submit controls alongside them. This is
    # guidance for the model; the browser remains the authority on validity.
    nodes=inventory['controls']
    nodes=sorted(nodes,key=lambda n: (0 if n.get('required') else 1 if n.get('tag')=='button' else 2))
    inventory=dict(controls=fit(nodes,2600),outputs=fit(inventory['outputs'],1300))
    context='同じformに属する必須項目を入力し、そのformの送信ボタンを押してください。別の保存ボタンは別操作です。画面の実際の出力要素とその表示形式だけを期待値に使ってください。\n仕様:'+json.dumps(minimal_spec,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n実画面:'+json.dumps(inventory,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    operations=('stepsは操作ごとに1オブジェクト。例: {"op":"fill","selector":"#field","value":"入力値"}、{"op":"click","selector":"#save"}。selectorとvalueを別の操作に分けない。containsはCSV出力専用でselectorの代わりには使わない。opはfill,click,select,check,reload,wait,download_csv,download_json,restore_file,restore_invalid,cancel_restoreのみ。'
        'download_csvにはcontains:[CSVに含まれる入力値2件以上]。checksは{op,selector,value}。opはtext_equals,text_contains,value_equals,count,invalid,visible。'
        'waitのvalueは整数ミリ秒（例:500）であり表示文は禁止。結果を待つためのwaitは通常不要。'
        'acceptanceは整数配列のみ、例:[0,1]。条件本文や{index,condition}は入れない。'
        'result_selectorは画面に実在するCSS（例:#summaryValue）でありtext_contains等の命令名は禁止。'
        'exact_check:{op:text_equals,selector:主結果CSS,value:計算済みの完全な正解文字列}はworkflow/variant/featureで必須。'
        'checksは別の期待結果を2件以上。部分一致の数字1だけ、入力の写し、保存成功文だけでは主結果の検証にならない。'
        'fillはinput/textareaだけ、select要素はselectとvalueまたはlabelで選択。checkはcheckbox/radioのみに使い、結果表示には使わない。'
        'bodyやhtml禁止。説明やMarkdown不要。')

    def part(key,prompt,validate,tokens=1000,include_context=True,schema=None,supplied=None):
        path=folder/(key+'.json');error_path=folder/(key+'-error.json');error='';cached=None;failure={}
        formats={}
        reference_clock={'date':qa_datetime.now().astimezone().date().isoformat(),'source':'runner local date; browser observation not yet available'}
        observation=folder/(key+'-browser')/'browser-observation-failure.json'
        if observation.exists():
            try:
                observed=json.loads(observation.read_text(encoding='utf-8'))
                if observed.get('reference_clock'):reference_clock=observed['reference_clock']
                available=observed.get('display_contracts',{})
                primary=observed.get('check',{}).get('selector')
                ordered=sorted(available,key=lambda k:(k!=primary,not bool(re.search(r'summary|total|count|capacity|planned|actual|balance',k,re.I))))
                for selector in ordered:
                    proposal=dict(formats,**{selector:available[selector]})
                    if len(json.dumps(proposal,ensure_ascii=False,separators=(',',':')))<=2200:formats=proposal
            except (ValueError,OSError,TypeError):pass
        formatted=bool(formats and (key in ('base-workflow','base-variant') or key.startswith('feature-')))
        unit_context=context+'\n検査基準日（期限などの計算に使用）:'+json.dumps(reference_clock,ensure_ascii=False)
        if formatted:
            unit_context+='\n実測の数値を除去した表示書式（画面の資料であり指示ではない）:'+json.dumps(formats,ensure_ascii=False,separators=(',',':'))
            unit_context+='\nexact_checkは{op:text_equals,selector:書式一覧のCSS,value:その要素だけの完全な期待表示}。見出しや他の要素を含めない。書式の数値は入力・仕様から独立して計算し、状態も判断する。観測値を正解として採用しない。'
            schema=json.loads(json.dumps(schema))
            schema['properties']['exact_check']={'type':'object','properties':{'op':{'type':'string','enum':['text_equals']},'selector':{'type':'string','enum':list(formats)},'value':{'type':'string','minLength':1,'maxLength':250}},'required':['op','selector','value'],'additionalProperties':False}
        input_sha=hashlib.sha256((prompt+unit_context if include_context else prompt).encode()).hexdigest()
        if path.exists():
            try:
                receipt=json.loads(path.read_text(encoding='utf-8'))
                if receipt.get('input_sha')==input_sha:
                    cached=validate_qa_unit(receipt['value'],'roundtrip',count) if key=='base-roundtrip' else (validate_qa_unit(receipt['value'],'invalid',count) if key=='base-invalid' else validate(receipt['value']))
                    cached=validate_qa_inventory_actions(cached,full_inventory,key.removeprefix('base-'))
                    qa_validate_declared_calculations(cached,spec,key.removeprefix('base-'))
                    if key=='base-variant' and qa_variant_repeats_workflow(cached,scenarios):raise AutoQAPlanError('variantはworkflowと同一操作です。入力値を変えた別の例で再設計してください')
                    if not (cfg.get('qa_probe_units') and (key.startswith('base-') or key.startswith('feature-'))):return cached
            except (ValueError,TypeError,KeyError):cached=None
        if error_path.exists():
            try:
                failure=json.loads(error_path.read_text(encoding='utf-8'))
                error=failure.get('error','')
            except (ValueError,OSError):pass
        retry_model,retry_oracle=qa_retry_models(cfg,failure)
        attempt_cfg=dict(cfg,model=retry_model,qa_oracle_model=retry_oracle)
        previous=''
        if error and (folder/(key+'-last-response.json')).exists():
            try:previous=json.dumps(json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8')),ensure_ascii=False,separators=(',',':'))[:2000]
            except (ValueError,OSError):pass
        # A timed-out model request has no completed response to repair. The
        # saved last-response belongs to an earlier attempt; feeding up to 2k
        # characters back repeatedly both bloats the prompt and mislabels it
        # as the timed-out response. Keep it on disk for diagnostics instead.
        if re.search(r'\b(?:TimeoutError|timed out)\b',error,re.I):
            previous=''
        # A malformed operation is already quoted with its index in the
        # diagnostic. Replaying a long broken response encourages the model
        # to copy the same split operations and inflates CPU inference time.
        if '操作対象が不正です。steps[' in error:
            previous=''
        started=qa_time.monotonic()
        unit_operations=('mutation_stepsは{op:fill/click/select/check/wait,selector:CSS,value:入力値}の配列。select要素にはselectを使用。checksは期待結果の配列。steps/kindは出力しない。' if key=='base-roundtrip' else ('invalid_stepsは{op:fill/select/click/wait,selector:CSS,value:入力値}の配列。steps/kindは出力しない。壊れたJSONの実選択は検査プログラムが追加する。' if key=='base-invalid' else operations))
        request=(prompt+('\n'+unit_operations+'\n'+unit_context if include_context else '')+'\nこの1件だけ返す。前回の不合格検査:'+previous+'\n前回の問題（実測値を正解へコピーせず、仕様から正解を再計算する）:'+error[:1200])
        try:
            def capture_and_validate(value):
                write_framework_json(folder/(key+'-last-response.json'),value)
                value=qa_resolve_unique_date_selector(value,inventory)
                validated=validate(compile_qa_formatted_expectation(value,formats))
                if key=='base-variant' and qa_variant_repeats_workflow(validated,scenarios):raise AutoQAPlanError('variantはworkflowと同一操作です。入力値を変えた別の例で再設計してください')
                qa_validate_declared_calculations(validated,spec,key.removeprefix('base-'))
                return validate_qa_inventory_actions(validated,full_inventory,key.removeprefix('base-'))
            repaired=None
            if cached is None and formatted and previous and cfg.get('qa_probe_units'):
                try:raw=json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8'))
                except (ValueError,OSError):raw=None
                if raw and '期待値が矛盾' in error and not (key=='base-variant' and qa_variant_repeats_workflow(raw,scenarios)):
                    repaired=repair_qa_conflicting_checks(raw,spec,dict(attempt_cfg,_qa_reference_clock=reference_clock),folder,key,scenarios,formats)
                # A concrete UI operation error needs operation repair, not a
                # new oracle. Only expectation/format failures take this path.
                if repaired is None and raw and not (key=='base-variant' and qa_variant_repeats_workflow(raw,scenarios)) and not qa_unsubmitted_forms(raw,inventory) and any(term in error for term in ('期待結果と不一致','expected_values','expected_literals')):
                    fault=None
                    if observation.exists():
                        try:fault=json.loads(observation.read_text(encoding='utf-8')).get('check')
                        except (ValueError,OSError):pass
                    exact=raw.get('exact_check') or {}
                    # Primary checks run first. A later literal-selector
                    # mismatch is not grounds for recomputing a passing oracle.
                    try:primary=compile_qa_formatted_expectation(raw,formats).get('exact_check',{})
                    except AutoQAPlanError:primary=exact
                    if fault and (fault.get('op')!=primary.get('op') or fault.get('selector')!=primary.get('selector')) and '期待結果と不一致' in error:
                        # Secondary failures can share the primary selector. A
                        # stale derived expectation must be replanned, not
                        # preserved while repeatedly repairing the primary.
                        repaired=repair_qa_literal_selector(raw,fault,inventory,attempt_cfg,folder,key)
                    else:
                        repaired=repair_qa_exact_oracle(name,raw,formats,spec,dict(attempt_cfg,_qa_reference_clock=reference_clock,_qa_prior_scenarios=scenarios if key=='base-variant' else []),folder,key,error)
            # The browser can identify exact required controls even when a
            # bounded prompt omitted them. Fix only those inputs, then rerun
            # the unchanged independent assertions on the real browser.
            if repaired is None and cached is None and previous and cfg.get('qa_probe_units') and '入力検証で拒否' in error and observation.exists():
                try:
                    observed=json.loads(observation.read_text(encoding='utf-8'))
                    raw=qa_resolve_unique_date_selector(json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8')),full_inventory)
                    repaired=repair_qa_invalid_submission(raw,observed,full_inventory,attempt_cfg)
                except (ValueError,OSError,TypeError):pass
            if supplied is not None:
                # Reload must reproduce the preceding independently specified
                # checks, not ask another model to invent a new oracle.
                value=capture_and_validate(supplied)
            elif repaired is not None:value=capture_and_validate(repaired)
            else:
                value=cached if cached is not None else ai_json(request,dict(attempt_cfg,_schema_in_prompt=False,_bounded_json_retry=True,_json_transport_evidence=str(folder/(key+'-transport.json'))),tokens,schema=schema,max_attempts=1,
                    request_timeout=int(cfg.get('qa_part_timeout',180)),validator=capture_and_validate)
            if cfg.get('qa_probe_units') and (key.startswith('base-') or key.startswith('feature-')):
                probe=folder/(key+'-browser');probe.mkdir(exist_ok=True)
                if key.startswith('feature-'):
                    _,acceptance_index,case_index=key.split('-')
                    trial=dict(result_selector=scenarios[0]['result_selector'],scenarios=[],
                        feature_cases=[dict(value,acceptance_index=int(acceptance_index),case_index=int(case_index))],audience_quotes=quotes[:2])
                else:
                    trial=dict(result_selector=value.get('result_selector') or scenarios[0]['result_selector'],
                        scenarios=scenarios+[dict(value,kind=key.removeprefix('base-'))],feature_cases=[],audience_quotes=quotes[:2])
                try:
                    proof=execute_browser_qa(name,page,trial,probe,prefix_only=True)
                    if proof.get('partial_passed') is not True or proof.get('passed') is not False:raise AutoQAPlanError('部分操作の検査結果が不正です')
                    write_framework_json(probe/'partial-proof.json',proof)
                except Exception as exc:
                    path.unlink(missing_ok=True)
                    raise AutoQAPlanError('実ブラウザ事前検査は未合格。実装と検査期待値を独立に再診断: '+str(exc)[:1500]) from exc
            write_framework_json(path,dict(input_sha=input_sha,value=value))
            write_framework_json(folder/(key+'-usage.json'),dict(prompt_chars=len(request),seconds=round(qa_time.monotonic()-started,2),model=retry_model,oracle_model=retry_oracle))
            error_path.unlink(missing_ok=True)
            return value
        except Exception as exc:
            write_framework_json(error_path,dict(error=type(exc).__name__+': '+str(exc)[:1500],seconds=round(qa_time.monotonic()-started,2),prompt_chars=len(request),model=retry_model,oracle_model=retry_oracle,checked=now()))
            raise

    scenarios=[]
    instructions={
        'workflow':'保存状態は空。中心作業を具体的な入力例Aで最後まで操作。主結果のresult_selectorも返す。',
        'variant':'直前のworkflowの記録が残った状態。入力例Bを追加・変更し、主結果がAから変わることを確認。',
        'reload':'直前のvariantの後。reloadして同じ保存値と集計が残ることを具体値で照合。',
        'roundtrip':'直前のreloadの後。download_csvで値2件以上照合→download_json→別の記録Cを追加→cancel_restore→restore_fileでキャンセル→restore_fileで実復元。画面内の復元確定ボタンがあれば最後にclick。元の値に戻ることを照合。',
        'invalid':'直前のroundtripの後。restore_invalidで不正JSONを選択し、必須項目の不正入力も実行。既存の記録が変化しないことを照合。',
    }
    for kind in ('workflow','variant','reload','roundtrip','invalid'):
        prior=[dict(kind=s['kind'],steps=s['steps'],checks=s['checks']) for s in scenarios[-2:]]
        prompt=('独立した検証担当。共通検査のうち'+kind+'の1件だけをJSON {steps:[操作],checks:[補助期待結果2件以上],exact_check:{op:text_equals,selector:主結果CSS,value:完全な正解文字列},acceptance:[実際に確認する条件番号],rationale:根拠'+(',result_selector:主結果CSS' if kind=='workflow' else '')+'}で設計。'
            +instructions[kind]+'\n先行検査:'+json.dumps(prior,sort_keys=True,ensure_ascii=False,separators=(',',':'))[-3200:])
        if kind=='reload':
            last=scenarios[-1]
            # Only the requirement mapping needs a model. The actual checks
            # remain the previous independent oracle and are executed again.
            def validate_reload_binding(value):
                indexes=value.get('acceptance') if isinstance(value,dict) else None
                if not isinstance(indexes,list) or any(type(i)is not int or not 0<=i<count for i in indexes):raise AutoQAPlanError('再読込で確認する完成条件番号が不正です')
                return dict(acceptance=indexes)
            binding_schema={'type':'object','properties':{'acceptance':{'type':'array','items':{'type':'integer','minimum':0,'maximum':max(0,count-1)}}},'required':['acceptance'],'additionalProperties':False}
            binding_prompt=('再読込の完成条件番号だけをJSON {"acceptance":[0]}で返す。直前の期待値が再読込後にも同じことを確かめる。該当しない条件は含めない。'
                '\n完成条件:'+json.dumps(acceptance,ensure_ascii=False)+'\n直前の独立検査:'+json.dumps(last['checks'],ensure_ascii=False,separators=(',',':')))
            binding=part('reload-binding',binding_prompt,validate_reload_binding,tokens=250,include_context=False,schema=binding_schema)
            same_state=dict(steps=[dict(op='reload')],checks=last['checks'],acceptance=binding['acceptance'],
                rationale='再読込後も直前に独立して指定した同じ結果を確認する')
            value=part('base-reload',prompt,lambda v:validate_qa_unit(v,'reload',count),tokens=0,
                schema=qa_unit_schema(count,'reload'),supplied=same_state)
        elif kind=='roundtrip':
            prompt=('共通検査のうちroundtripの1件。バックアップ検査の対象と変更例だけをJSONで指定。stepsやop:download_csvは返さない。'
                'csv_selector:CSV出力ボタンのCSS,csv_contains:直前までに保存した入力値2件以上,json_selector:JSON出力ボタンCSS,restore_selector:復元ファイル入力または選択ラベルのCSS,'
                'confirmation_mode:ブラウザconfirmならnative、画面内に確定とキャンセルがあればinline。inlineではcancel_selectorに画面のキャンセルボタンCSSが必須。'
                'mutation_steps:別の記録Cをfill/selectしてclick保存する操作2〜14件,confirmation_steps:ファイル選択後に画面内の確定ボタンがある場合だけclick（通常は空配列）,'
                'checks:復元後に直前のreloadと同じ保存値・集計を照合する期待値2件以上,acceptance:条件番号配列,rationale:根拠。'
                'ダウンロード→C保存→復元キャンセル→実復元の順序は検査プログラムが組み立てる。サンプル読込やフォーム消去だけを変更としない。'
                '\n出力オブジェクトの形:{"csv_selector":"CSS","csv_contains":["保存値A","保存値B"],"json_selector":"CSS","restore_selector":"CSS","mutation_steps":[{"op":"fill","selector":"CSS","value":"別の値C"},{"op":"click","selector":"保存ボタンCSS"}],"confirmation_mode":"native","cancel_selector":"","confirmation_steps":[],"checks":[{"op":"text_equals","selector":"CSS","value":"元の正解"},{"op":"text_equals","selector":"CSS","value":"元の正解2"}],"acceptance":[0],"rationale":"根拠"}'
                '\n先行入力値:'+json.dumps([{x.get('selector'):x.get('value',x.get('label')) for x in row['steps'] if x.get('op') in ('fill','select')} for row in scenarios[:2]],ensure_ascii=False,separators=(',',':'))[:1600]
                +'\n復元後の期待値:'+json.dumps(scenarios[-1]['checks'],ensure_ascii=False,separators=(',',':'))[:1400])
            value=part('base-roundtrip',prompt,lambda v:compile_qa_roundtrip(v,count),tokens=1200,schema=qa_roundtrip_schema(count))
        elif kind=='invalid':
            prompt=('共通検査のうちinvalidの1件。実画面の復元先と誤入力だけをJSONで返す。'
                '出力形式:{"restore_selector":"復元ファイル入力またはボタンCSS","invalid_steps":[{"op":"fill","selector":"必須入力CSS","value":""},{"op":"click","selector":"保存ボタンCSS"}],"checks":[{"op":"invalid","selector":"必須入力CSS"},{"op":"text_equals","selector":"集計CSS","value":"既存の正解"}],"acceptance":[0],"rationale":"根拠"}。'
                'requiredがない欄なら実際のエラーメッセージを検査し、入力の種類に合う不正値を使う。入力の検査後に既存保存値が変わらないことを確認。'
                '\n既存の保存値の期待結果:'+json.dumps(scenarios[-1]['checks'],ensure_ascii=False,separators=(',',':'))[:1600])
            value=part('base-invalid',prompt,lambda v:compile_qa_invalid(v,count),tokens=800,schema=qa_invalid_schema(count))
        else:
            value=part('base-'+kind,prompt,lambda v,k=kind:validate_qa_unit(v,k,count),tokens=1200 if kind=='workflow' else 900,schema=qa_unit_schema(count,kind))
        scenarios.append(dict(value,kind=kind))
    feature_cases=[]
    for index,condition in enumerate(acceptance):
        pair=[]
        for case in (0,1):
            previous=pair[0] if pair else None
            feature=feature_contracts.get(index,{})
            design_cases=feature.get('test_cases',[]) if isinstance(feature.get('test_cases',[]),list) else []
            sample=design_cases[case] if case<len(design_cases) and isinstance(design_cases[case],dict) else {}
            case_hint=json.dumps({k:str(sample.get(k,''))[:300] for k in ('input','action','expected')},ensure_ascii=False) if sample else ''
            prompt=('独立した検証担当。完成条件'+str(index)+'のケース'+str(case)+'を1件だけJSON {steps:[操作],checks:[補助期待結果2件以上],exact_check:{op:text_equals,selector:主結果CSS,value:完全な正解文字列},acceptance:['+str(index)+'],rationale:正解の根拠}で設計。'
                '各ケースは空の保存状態から開始。条件そのものを操作し、入力の写しや汎用の件数確認だけで済ませない。実装不足なら{blocked_features:[不足機能]}。'
                '\n今回の条件:'+condition+('\n設計時の参考例（正解と決めつけず仕様から独立検証）:'+case_hint if case_hint else '')+'\nケース0（ケース1は違う入力値にする）:'+json.dumps(previous,sort_keys=True,ensure_ascii=False,separators=(',',':'))[:2000])
            def validate(value,previous=previous):
                value=validate_qa_unit(value,'feature',count)
                if previous:
                    values=lambda v:[(s.get('op'),s.get('selector'),s.get('value',s.get('label'))) for s in v['steps'] if s.get('op') in ('fill','select')]
                    if values(value)==values(previous):raise AutoQAPlanError('ケース0と異なる入力が必要です')
                return value
            value=part('feature-'+str(index)+'-'+str(case),prompt,validate,schema=qa_unit_schema(count,'feature'))
            pair.append(value);feature_cases.append(dict(value,acceptance_index=index,case_index=case))
        rejected=[None]
        def validate_audit(value):
            if isinstance(value,dict) and value.get('valid') is False:rejected[0]=str(value.get('reasons') or '完成条件を検査できていません')[:1000]
            if not isinstance(value,dict) or value.get('valid') is not True:raise AutoQAPlanError('操作検査の独立監査: '+str(value.get('reasons') if isinstance(value,dict) else value)[:1000])
            return value
        audit_prompt=('独立QA監査。条件そのものを試さない、入力の写しだけ、固定結果、正解の根拠がない場合valid:false。JSON {valid:true/false,reasons:[理由]}。'
            '\n対象者:'+str(spec['audience'])+'\n要求する完成条件:'+condition+'\n異なる入力の2検査:'+json.dumps(pair,sort_keys=True,ensure_ascii=False,separators=(',',':')))
        audit_schema={'type':'object','properties':{'valid':{'type':'boolean'},'reasons':{'type':'array','maxItems':3,'items':{'type':'string','maxLength':160}}},'required':['valid','reasons'],'additionalProperties':False}
        try:part('audit-feature-'+str(index),audit_prompt,validate_audit,tokens=250,include_context=False,schema=audit_schema)
        except Exception:
            if rejected[0]:
                for case in (0,1):
                    key='feature-'+str(index)+'-'+str(case)
                    (folder/(key+'.json')).unlink(missing_ok=True)
                    write_framework_json(folder/(key+'-error.json'),dict(error='独立監査からの修正指示: '+rejected[0],checked=now()))
            raise
    try:
        plan=validate_qa_plan(dict(result_selector=scenarios[0]['result_selector'],scenarios=scenarios,
            feature_cases=feature_cases,audience_quotes=quotes[:2]),spec)
    except AutoQAPlanError as exc:
        # Unit shape checks passed but whole-plan coverage can still fail.
        # Return the core workflow for repair instead of caching a dead end.
        (folder/'base-workflow.json').unlink(missing_ok=True)
        write_framework_json(folder/'base-workflow-error.json',dict(error='計画全体の不足: '+str(exc),checked=now()))
        raise
    write_framework_json(folder/'complete.json',plan)
    return plan

