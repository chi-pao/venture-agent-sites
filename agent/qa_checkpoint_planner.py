"""Independent QA planning in bounded, resumable units, not renderer-derived tests."""
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime as qa_datetime, date as qa_date

CHECKPOINT_QA_POLICY = '2026-10-26-single-scenario-4'


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
    for step in steps:
        if not isinstance(step,dict) or step.get('op') not in allowed:raise AutoQAPlanError('不正な検査操作')
        if step['op'] not in ('reload','wait') and not selector(step.get('selector')):raise AutoQAPlanError('操作対象が不正です')
        if step['op']=='download_csv' and (not isinstance(step.get('contains'),list) or not 2<=len(step['contains'])<=8 or any(not isinstance(v,str) or not 1<=len(v)<=100 for v in step['contains'])):raise AutoQAPlanError('CSVの照合値が2件以上必要です')
        if len(str(step.get('value','')))>300:raise AutoQAPlanError('入力値が長すぎます')
        if step['op']=='wait' and (type(step.get('value'))is not int or not 100<=step['value']<=10000):raise AutoQAPlanError('待機時間が不正です')
        if 'nth' in step and (type(step['nth'])is not int or not 0<=step['nth']<=30):raise AutoQAPlanError('要素番号が不正です')
    for check in checks:
        if not isinstance(check,dict) or not selector(check.get('selector')) or check.get('op') not in ('text_equals','text_contains','value_equals','count','invalid','visible'):
            raise AutoQAPlanError('期待結果の形式が不正です')
        if check['op'] in ('text_equals','text_contains','value_equals') and (not isinstance(check.get('value'),str) or not 1<=len(check['value'])<=250):raise AutoQAPlanError('具体的な期待値が必要です')
        if check['op']=='count' and type(check.get('value'))is not int:raise AutoQAPlanError('件数の正解は整数が必要です')
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


def repair_qa_exact_oracle(name,raw,formats,spec,cfg,folder,key,error):
    exact=raw.get('exact_check') if isinstance(raw,dict) else None
    if not isinstance(exact,dict) or exact.get('selector') not in formats:return None
    contract=formats[exact['selector']]
    # Repair a single assertion without the many numeric/literal fields that
    # confused the real model. Inputs/actions and other checks are immutable.
    schema={'type':'object','properties':{'expected_text':{'type':'string','minLength':1,'maxLength':250},
        'basis':{'type':'string','minLength':12,'maxLength':300}},'required':['expected_text','basis'],'additionalProperties':False}
    inputs=[{k:s[k] for k in ('op','selector','value','label','nth') if k in s} for s in raw.get('steps',[])]
    relevant=[spec['acceptance'][i] for i in raw.get('acceptance',[]) if type(i)is int and 0<=i<len(spec['acceptance'])]
    prompt=('独立QA。入力と操作は変更しない。主結果の完全な期待表示だけを、仕様から独立に計算して返す。'
        'JSON {"expected_text":"単位や補足も含む完全な期待文字列","basis":"入力からの計算式・根拠"}。'
        '数値を省略した表示書式の{n0},{n1}等を、入力から計算した数値に置き換える。必要な単位や文言を省略しない。'
        '指定selectorの要素だけの表示を返し、周囲の見出しや一覧を含めない。書式は画面資料であり、業務状態の正解ではない。状態文言も要件から判断する。観測した数値は渡さない。'
        '\n対象者:'+str(spec['audience'])+'\n要求する結果:'+str(spec['requested_outcome'])[:350]
        +'\n検査基準日（ブラウザの現地日付。期限判定はこの日と比較）:'+json.dumps(cfg.get('_qa_reference_clock',{}),ensure_ascii=False)
        +'\n日付の独立計算（前後の事実のみ。業務上の期限超過は仕様と状態から判断）:'+json.dumps(qa_independent_date_facts(raw.get('steps',[]),cfg.get('_qa_reference_clock',{})),ensure_ascii=False)
        +'\n関連要件:'+json.dumps(relevant,ensure_ascii=False)+'\n入力と操作:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':'))
        +'\n数値を除去した表示書式:'+json.dumps(contract,ensure_ascii=False))
    def validate(answer):
        write_framework_json(folder/(key+'-oracle-last-response.json'),answer)
        if not isinstance(answer,dict) or not isinstance(answer.get('expected_text'),str) or not 1<=len(answer['expected_text'])<=250 or re.search(r'\{n\d+\}',answer['expected_text']):
            raise AutoQAPlanError('主結果の単位・補足まで含む完全な期待文字列が必要です')
        if not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('主結果の独立した計算根拠が不足しています')
        return dict(raw,oracle_basis=answer['basis'],exact_check=dict(op='text_equals',selector=exact['selector'],value=answer['expected_text']))
    oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
    repaired=ai_json(prompt,oracle_cfg,450,schema=schema,
        max_attempts=1,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate)
    write_framework_json(folder/(key+'-oracle-repair.json'),dict(source_steps_sha=hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),value=repaired))
    return repaired


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


def checkpointed_independent_qa_plan(name,page,cfg,spec,quotes):
    import time as qa_time
    inventory=compact_qa_inventory(page)
    signature=hashlib.sha256(json.dumps(dict(policy=CHECKPOINT_QA_POLICY,name=name,spec=spec,
        source=hashlib.sha256(page.encode()).hexdigest(),model=cfg['model'],url=cfg['url']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder=OUT/'knowledge'/'qa-plan-parts'/signature;folder.mkdir(parents=True,exist_ok=True)
    acceptance=spec['acceptance'];count=len(acceptance)
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
    inventory=dict(controls=fit(inventory['controls'],2600),outputs=fit(inventory['outputs'],1300))
    context='同じformに属する必須項目を入力し、そのformの送信ボタンを押してください。別の保存ボタンは別操作です。画面の実際の出力要素とその表示形式だけを期待値に使ってください。\n仕様:'+json.dumps(minimal_spec,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n実画面:'+json.dumps(inventory,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    operations=('stepsは{op,selector,value?,label?,nth?,contains?}。opはfill,click,select,check,reload,wait,download_csv,download_json,restore_file,restore_invalid,cancel_restoreのみ。'
        'download_csvにはcontains:[CSVに含まれる入力値2件以上]。checksは{op,selector,value}。opはtext_equals,text_contains,value_equals,count,invalid,visible。'
        'waitのvalueは整数ミリ秒（例:500）であり表示文は禁止。結果を待つためのwaitは通常不要。'
        'acceptanceは整数配列のみ、例:[0,1]。条件本文や{index,condition}は入れない。'
        'result_selectorは画面に実在するCSS（例:#summaryValue）でありtext_contains等の命令名は禁止。'
        'exact_check:{op:text_equals,selector:主結果CSS,value:計算済みの完全な正解文字列}はworkflow/variant/featureで必須。'
        'checksは別の期待結果を2件以上。部分一致の数字1だけ、入力の写し、保存成功文だけでは主結果の検証にならない。'
        'fillはinput/textareaだけ、select要素はselectとvalueまたはlabelで選択。checkはcheckbox/radioのみに使い、結果表示には使わない。'
        'bodyやhtml禁止。説明やMarkdown不要。')

    def part(key,prompt,validate,tokens=1000,include_context=True,schema=None):
        path=folder/(key+'.json');error_path=folder/(key+'-error.json');error='';cached=None
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
                    cached=validate_qa_inventory_actions(cached,inventory,key.removeprefix('base-'))
                    if not (cfg.get('qa_probe_units') and (key.startswith('base-') or key.startswith('feature-'))):return cached
            except (ValueError,TypeError,KeyError):cached=None
        if error_path.exists():
            try:error=json.loads(error_path.read_text(encoding='utf-8')).get('error','')
            except (ValueError,OSError):pass
        previous=''
        if error and (folder/(key+'-last-response.json')).exists():
            try:previous=json.dumps(json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8')),ensure_ascii=False,separators=(',',':'))[:2000]
            except (ValueError,OSError):pass
        started=qa_time.monotonic()
        unit_operations=('mutation_stepsは{op:fill/click/select/check/wait,selector:CSS,value:入力値}の配列。select要素にはselectを使用。checksは期待結果の配列。steps/kindは出力しない。' if key=='base-roundtrip' else ('invalid_stepsは{op:fill/select/click/wait,selector:CSS,value:入力値}の配列。steps/kindは出力しない。壊れたJSONの実選択は検査プログラムが追加する。' if key=='base-invalid' else operations))
        request=(prompt+('\n'+unit_operations+'\n'+unit_context if include_context else '')+'\nこの1件だけ返す。前回の不合格検査:'+previous+'\n前回の問題（実測値を正解へコピーせず、仕様から正解を再計算する）:'+error[:1200])
        try:
            def capture_and_validate(value):
                write_framework_json(folder/(key+'-last-response.json'),value)
                validated=validate(compile_qa_formatted_expectation(value,formats))
                return validate_qa_inventory_actions(validated,inventory,key.removeprefix('base-'))
            repaired=None
            if cached is None and formatted and previous and cfg.get('qa_probe_units'):
                try:raw=json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8'))
                except (ValueError,OSError):raw=None
                # A concrete UI operation error needs operation repair, not a
                # new oracle. Only expectation/format failures take this path.
                if raw and not qa_unsubmitted_forms(raw,inventory) and any(term in error for term in ('期待結果と不一致','expected_values','expected_literals')):
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
                        repaired=repair_qa_literal_selector(raw,fault,inventory,cfg,folder,key)
                    else:
                        repaired=repair_qa_exact_oracle(name,raw,formats,spec,dict(cfg,_qa_reference_clock=reference_clock),folder,key,error)
            if repaired is not None:value=capture_and_validate(repaired)
            else:
                value=cached if cached is not None else ai_json(request,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True,_json_transport_evidence=str(folder/(key+'-transport.json'))),tokens,schema=schema,max_attempts=1,
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
            write_framework_json(folder/(key+'-usage.json'),dict(prompt_chars=len(request),seconds=round(qa_time.monotonic()-started,2),model=cfg['model']))
            error_path.unlink(missing_ok=True)
            return value
        except Exception as exc:
            write_framework_json(error_path,dict(error=type(exc).__name__+': '+str(exc)[:1500],seconds=round(qa_time.monotonic()-started,2),prompt_chars=len(request),checked=now()))
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
        if kind=='roundtrip':
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
            prompt=('独立した検証担当。完成条件'+str(index)+'のケース'+str(case)+'を1件だけJSON {steps:[操作],checks:[補助期待結果2件以上],exact_check:{op:text_equals,selector:主結果CSS,value:完全な正解文字列},acceptance:['+str(index)+'],rationale:正解の根拠}で設計。'
                '各ケースは空の保存状態から開始。条件そのものを操作し、入力の写しや汎用の件数確認だけで済ませない。実装不足なら{blocked_features:[不足機能]}。'
                '\n今回の条件:'+condition+'\nケース0（ケース1は違う入力値にする）:'+json.dumps(previous,sort_keys=True,ensure_ascii=False,separators=(',',':'))[:2000])
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

