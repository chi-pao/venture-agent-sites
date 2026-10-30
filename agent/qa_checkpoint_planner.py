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


def qa_save_failure_diagnosis(folder,key,page,spec,prior,trial,error,models,current_response=False):
    """Freeze a failed attempt without treating an observed result as truth."""
    folder=Path(folder)
    kind=('inference_timeout' if re.search(r'timed out|TimeoutError',error,re.I) else
          'test_input_rejected' if '入力検証で拒否' in error else
          'assertion_mismatch_unresolved' if '期待結果と不一致' in error else
          'test_definition_rejected' if any(t in error for t in ('expected_values','expected_literals','期待値が矛盾','期待値全体')) else 'unclassified')
    snapshot=dict(case=key,spec=spec,prior_scenarios=prior,replay_plan=trial,
                  source_sha=hashlib.sha256(page.encode()).hexdigest(),error=error,models=models)
    attempt=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    directory=folder/'failure-diagnoses'/key/attempt;directory.mkdir(parents=True,exist_ok=True)
    source=folder/'diagnostic-source.html'
    if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest()!=snapshot['source_sha']:
        source.write_text(page,encoding='utf-8')
    write_framework_json(directory/'replay.json',snapshot)
    evidence=[]
    candidates=[folder/(key+'-browser')/'browser-observation-failure.json'] if trial is not None else []
    if current_response:candidates.append(folder/(key+'-last-response.json'))
    for path in candidates:
        if path.exists():
            target=directory/path.name;target.write_bytes(path.read_bytes())
            evidence.append(dict(path=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    diagnosis=dict(attempt=attempt,kind=kind,cause_confirmed=False,
        conclusion='ブラウザの結果と検査期待値の不一致だけでは製品側・検査側のどちらが誤りか未確定',
        replay_available=trial is not None,source=str(source),source_sha=snapshot['source_sha'],
        replay=str(directory/'replay.json'),evidence=evidence,
        next_action=('同じ入力と仕様で独立参照計算を行い、期待値と実装を別々に照合' if kind=='assertion_mismatch_unresolved' else
                     'モデル応答時間と要求サイズを調べ、成功済み検査を保持して失敗単位を修正'))
    write_framework_json(directory/'diagnosis.json',diagnosis)
    write_framework_json(folder/(key+'-diagnosis.json'),diagnosis)
    return diagnosis


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
    # Coding ability is not evidence of independent business-oracle quality.
    # Keep the dedicated oracle unless an oracle-specific alternate is set.
    alternate_oracle=str(cfg.get('qa_alternate_oracle_model') or '')
    oracle_model=alternate_oracle if alternate_oracle and alternate_oracle!=oracle and last_oracle!=alternate_oracle else oracle
    return model,oracle_model


def qa_failure_memory(previous, detail):
    """Count identical failed checkpoints without discarding passing siblings."""
    signature=hashlib.sha256(detail.encode()).hexdigest()
    repeats=previous.get('repeats',0) if previous.get('signature')==signature else 0
    if type(repeats)is not int or repeats<0:repeats=0
    return dict(signature=signature,repeats=repeats+1)


def qa_independent_failure_hint(error):
    # Actual UI values remain in evidence files, never become an oracle hint.
    if '期待結果と不一致' in error:
        return '既存の期待値が実ブラウザ検査を通過しません。実測結果は正解の資料に使わず、仕様と入力から独立して再計算してください。'
    return error[:1200]


def qa_retry_timeout(cfg, failure):
    """Bound extra inference time to the unit that actually timed out."""
    base=int(cfg.get('qa_part_timeout',180))
    if not isinstance(failure,dict) or not re.search(r'\b(?:TimeoutError|timed out)\b',str(failure.get('error','')),re.I):return base
    streak=failure.get('timeout_streak',1)
    if type(streak)is not int or streak<1:streak=1
    ceiling=max(base,int(cfg.get('qa_part_timeout_ceiling',360)))
    return min(ceiling,base+(base//2)*min(streak,2))


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


def qa_declared_backup_targets(cfg,inventory):
    """A versioned file protocol, never a model guess about confirmation UI."""
    if cfg.get('qa_backup_component_contract')!='native-record-backup-v1':return None
    if cfg.get('qa_component_contract')!='native-record-create-v1':return None
    nodes={n['selector']:n for n in inventory.get('controls',[])}
    if any(nodes.get(css,{}).get('tag')!='button' for css in ('#downloadCsv','#downloadJson')):return None
    if nodes.get('#restoreFile',{}).get('type')!='file':return None
    return dict(csv_selector='#downloadCsv',json_selector='#downloadJson',restore_selector='#restoreFile',confirmation_mode='native',confirmation_steps=[],cancel_selector='')


def qa_validate_backup_targets(value,inventory):
    if not isinstance(value,dict):raise AutoQAPlanError('復元先の指定が必要です')
    nodes={n['selector']:n for n in inventory.get('controls',[])}
    for key in ('csv_selector','json_selector'):
        if nodes.get(value.get(key),{}).get('tag')!='button':raise AutoQAPlanError('実在する出力ボタンが必要: '+key)
    if nodes.get(value.get('restore_selector'),{}).get('type')!='file':raise AutoQAPlanError('実在する復元file入力が必要です')
    mode=value.get('confirmation_mode');steps=value.get('confirmation_steps')
    if mode not in ('native','inline') or not isinstance(steps,list):raise AutoQAPlanError('復元確認方式が未確定です')
    if mode=='native' and steps:raise AutoQAPlanError('ブラウザconfirmに画面内の確定clickを追加できません')
    if mode=='inline':
        if nodes.get(value.get('cancel_selector'),{}).get('tag')!='button' or not steps:raise AutoQAPlanError('画面内復元には実在する取消ボタンと確定操作が必要です')
        if any(s.get('op')!='click' or nodes.get(s.get('selector'),{}).get('tag')!='button' for s in steps):raise AutoQAPlanError('画面にない復元確定ボタンを推測できません')
    return value


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
        super().__init__();self.nodes=[];self.stack=[];self.labels={};self.label_for=None;self.wrapped_label=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.stack.append((tag,a));node=None
        if tag=='label':
            self.label_for=a.get('for')
            self.wrapped_label=dict(start=len(self.nodes),text='') if not self.label_for else None
        if tag=='option':
            parent=next((v.get('id') for t,v in reversed(self.stack[:-1]) if t=='select'),None)
            select=next((n for n in reversed(self.nodes) if n['selector']=='#'+str(parent)),None)
            if select is not None:select.setdefault('options',[]).append(dict(value=a.get('value'),label='',selected='selected' in a))
        if tag in ('input','select','textarea','button') or a.get('id'):
            selector='#'+a['id'] if a.get('id') else ''
            if not selector:
                ancestor=next((v.get('id') for t,v in reversed(self.stack[:-1]) if v.get('id')),None)
                if ancestor:selector='#'+ancestor+' '+tag
            if selector:
                node=dict(tag=tag,selector=selector)
                if tag not in ('input','select','textarea','button'):
                    node['ancestor_selectors']=['#'+v['id'] for t,v in self.stack[:-1] if v.get('id')]
                form_id=a.get('form') or next((v.get('id') for t,v in reversed(self.stack[:-1]) if t=='form' and v.get('id')),None)
                if form_id:node['form']='#'+form_id
                for key in ('type','value','placeholder','min','max','required','name','disabled','readonly','role','pattern','maxlength','minlength'):
                    if key in a:node[key]=a[key] if a[key] is not None else True
                self.nodes.append(node)
        # Track text owners separately. Void controls do not own following text.
        if tag in ('input','br','meta','link','img','hr'):self.stack.pop()
    def handle_endtag(self,tag):
        if tag=='label':
            if self.wrapped_label:
                for node in self.nodes[self.wrapped_label['start']:]:
                    if node['tag'] in ('input','select','textarea') and node['selector'].startswith('#') and ' ' not in node['selector']:
                        self.labels[node['selector'][1:]]=self.wrapped_label['text'].strip()[:100]
            self.label_for=None;self.wrapped_label=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):
        if any(t in ('script','style','head','template','svg') for t,a in self.stack):return
        value=' '.join(data.split())
        if not value:return
        if self.wrapped_label is not None and not any(t in ('select','option','textarea','button') for t,a in self.stack):
            self.wrapped_label['text']+=' '+value
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
    output_labels=qa_output_labels_from_html(page)
    for node in outputs:
        if node['selector'] in output_labels:node['label']=output_labels[node['selector']]
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


def qa_submission_index(steps,observation):
    operation=observation.get('operation',{})
    explicit=observation.get('operation_index')
    if explicit is not None:
        return explicit if type(explicit)is int and 0<=explicit<len(steps) and steps[explicit]==operation else None
    indexes=[i for i,step in enumerate(steps) if step==operation]
    return indexes[0] if len(indexes)==1 else None


def repair_qa_required_selects(raw,observation,inventory,cfg):
    """One missing native choice per bounded model call; no invented options."""
    targets=[x.get('selector') for x in observation.get('invalid_fields',[])]
    nodes={n['selector']:n for n in inventory.get('controls',[])}
    if not targets or any(nodes.get(t,{}).get('tag')!='select' for t in targets):return None
    steps=raw.get('steps',[]);operation=observation.get('operation',{})
    index=qa_submission_index(steps,observation)
    if operation.get('op')!='click' or steps!=observation.get('steps') or index is None or len(steps)+len(targets)>24:return None
    additions=[]
    for target in targets:
        node=nodes[target];options=[o for o in node.get('options',[]) if o.get('value')]
        values=list(dict.fromkeys(o['value'] for o in options))
        if not values:return None
        context=dict(control=node,steps=steps,operation_index=index,spec=cfg.get('_qa_spec',{}),model=cfg.get('qa_mapping_model') or cfg.get('qa_oracle_model') or cfg['model'])
        digest=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        directory=cfg.get('_qa_input_repair_directory');path=None
        if directory:
            directory=Path(directory)/'required-selects';directory.mkdir(parents=True,exist_ok=True);path=directory/(digest+'.json')
        def validate(answer):
            if not isinstance(answer,dict) or answer.get('value') not in values:raise AutoQAPlanError('必須選択欄には提示された実在のvalueが必要です')
            return answer
        answer=None
        if path and path.exists():
            try:answer=validate(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError,TypeError,KeyError):pass
        if answer is None:
            schema={'type':'object','properties':{'value':{'type':'string','enum':values}},'required':['value'],'additionalProperties':False}
            prompt=('独立QA。今回の必須選択欄1個だけを、元仕様と入力済みの例に整合するoptionで補完する。既存の操作・期待値は変えない。JSON {value:optionのvalue}。'
                +'\n選択欄:'+json.dumps(node,ensure_ascii=False)+'\n元仕様:'+json.dumps(context['spec'],ensure_ascii=False)[:1800]
                +'\n入力済みの操作:'+json.dumps(steps[:index],ensure_ascii=False,separators=(',',':'))[:1800])
            answer=ai_json(prompt,dict(cfg,model=context['model'],_schema_in_prompt=False,_bounded_json_retry=True),100,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)
            if path:write_framework_json(path,answer)
        additions.append(dict(op='select',selector=target,value=answer['value']))
    i=index
    return dict(raw,steps=steps[:i]+additions+steps[i:])


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
    index=qa_submission_index(steps,observation)
    if index is None or len(steps)+len(targets)>24:return None
    selected=repair_qa_required_selects(raw,observation,inventory,cfg)
    if selected is not None:return selected
    schema={'type':'object','properties':{'inputs':{'type':'array','minItems':len(targets),'maxItems':len(targets),'items':{'type':'object','properties':{'selector':{'type':'string','enum':targets},'value':{'type':'string','minLength':1,'maxLength':100}},'required':['selector','value'],'additionalProperties':False}}},'required':['inputs'],'additionalProperties':False}
    prompt=('独立QA。'+('実画面のHTMLに基づく事前検査で不足した' if observation.get('source')=='static_preflight' else 'ブラウザが送信を拒否した')+'必須項目だけを埋める。既存の操作・期待値は変更しない。'
        '入力済みの値と整合する具体値を決め、selectは提示されたoptionのvalueを使う。JSON {"inputs":[{"selector":"CSS","value":"値"}]}のみ返す。'
        '\n元仕様:'+json.dumps(cfg.get('_qa_spec',{}),ensure_ascii=False)[:2500]
        +'\n不足・拒否された項目:'+json.dumps([nodes[t] for t in targets],ensure_ascii=False)
        +'\n補完する保存操作の位置:'+str(index)+'\nその保存より前の操作:'+json.dumps(steps[:index],ensure_ascii=False,separators=(',',':')))
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
        i=index
        return dict(raw,steps=steps[:i]+additions+steps[i:])
    return ai_json(prompt,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),450,schema=schema,max_attempts=2,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)


def qa_missing_initial_required_inputs(value,inventory):
    """Check known required fields before the first explicit form submit.

    Later/dynamic form state remains the real browser's responsibility.
    No values are fabricated to make a test pass.
    """
    controls=inventory.get('controls',[]);known={n['selector']:n for n in controls}
    values={n['selector']:n.get('value','') for n in controls if n.get('tag')=='input'}
    for n in controls:
        if n.get('tag')=='select' and n.get('options'):
            option=next((o for o in n['options'] if o.get('selected')),n['options'][0])
            values[n['selector']]=option.get('value') if option.get('value') is not None else option.get('label','')
    for step in value.get('steps',[]):
        selector=step.get('selector');node=known.get(selector,{})
        if step.get('op') in ('fill','select'):
            values[selector]=step.get('value',step.get('label',''))
        if step.get('op')=='click' and node.get('form') and (node.get('type')=='submit' or node.get('tag')=='button' and not node.get('type')):
            required=[n for n in controls if n.get('form')==node['form'] and 'required' in n and 'disabled' not in n and 'readonly' not in n and n.get('tag') in ('input','select') and n.get('type') not in ('checkbox','radio','file','hidden')]
            return [n['selector'] for n in required if values.get(n['selector']) is None or str(values.get(n['selector'],'')).strip()=='']
    return []


def qa_repeated_form_issue(value,inventory):
    """Do not assume a saved form retains required fields for the next record."""
    controls=inventory.get('controls',[]);known={n['selector']:n for n in controls}
    submitted=set();entered={}
    for index,step in enumerate(value.get('steps',[])):
        selector=step.get('selector');node=known.get(selector,{})
        if step.get('op') in ('fill','select','check'):entered[selector]=step.get('value',step.get('label',''))
        form=node.get('form')
        if step.get('op')!='click' or not form or not (node.get('type')=='submit' or node.get('tag')=='button' and not node.get('type')):continue
        required=[n['selector'] for n in controls if n.get('form')==form and 'required' in n and 'disabled' not in n and 'readonly' not in n and n.get('tag') in ('input','select','textarea') and n.get('type')not in ('hidden','file','radio','checkbox')]
        if form in submitted:
            missing=[css for css in required if css not in entered or entered[css]is None or str(entered[css]).strip()=='']
            if missing:return dict(source='static_preflight',steps=value['steps'],operation=step,operation_index=index,invalid_fields=[dict(selector=css) for css in missing])
        submitted.add(form)
        for css in required:entered.pop(css,None)
    return None


def qa_validate_repeated_form_inputs(value,inventory):
    issue=qa_repeated_form_issue(value,inventory)
    if issue:raise AutoQAPlanError('次の保存操作'+str(issue['operation_index'])+'の必須欄を再入力してください: '+json.dumps(issue['invalid_fields'],ensure_ascii=False))
    return value


def repair_qa_repeated_form_inputs(value,inventory,cfg):
    for attempt in range(8):
        issue=qa_repeated_form_issue(value,inventory)
        if not issue:return value
        repaired=repair_qa_invalid_submission(value,issue,inventory,cfg)
        if repaired is None or repaired==value:break
        value=repaired
    return qa_validate_repeated_form_inputs(value,inventory)


def repair_qa_missing_initial_inputs(raw,inventory,cfg,spec):
    missing=qa_missing_initial_required_inputs(raw,inventory)
    if not missing:return None
    controls={n['selector']:n for n in inventory.get('controls',[])}
    for operation_index,step in enumerate(raw.get('steps',[])):
        node=controls.get(step.get('selector'),{})
        if step.get('op')=='click' and node.get('form') and (node.get('type')=='submit' or node.get('tag')=='button' and not node.get('type')):
            observation=dict(source='static_preflight',steps=raw['steps'],operation=step,operation_index=operation_index,invalid_fields=[dict(selector=x) for x in missing])
            return repair_qa_invalid_submission(raw,observation,inventory,dict(cfg,_qa_spec=spec))
    return None


def qa_bad_typed_inputs(value,inventory):
    controls={n['selector']:n for n in inventory.get('controls',[])};bad=[]
    for index,step in enumerate(value.get('steps',[])):
        node=controls.get(step.get('selector'),{});typ=node.get('type');v=step.get('value')
        if step.get('op')!='fill' or typ not in ('number','date'):continue
        try:
            if typ=='number':
                if isinstance(v,bool) or v is None or not decimal.Decimal(str(v)).is_finite():raise ValueError()
            else:
                if not isinstance(v,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v):raise ValueError()
                qa_date.fromisoformat(v)
        except (ValueError,decimal.InvalidOperation):bad.append(dict(step_index=index,control=node,value=v))
    return bad


def qa_normalize_select_inputs(raw,inventory):
    """Bind unchanged intended values to a unique native select option."""
    controls={n['selector']:n for n in inventory.get('controls',[])}
    steps=[dict(step) for step in raw.get('steps',[])]
    for step in steps:
        node=controls.get(step.get('selector'),{})
        if step.get('op')!='fill' or node.get('tag')!='select':continue
        value=step.get('value')
        if not isinstance(value,str):continue
        options=node.get('options',[])
        by_value=[o for o in options if o.get('value')==value]
        by_label=[o for o in options if o.get('label')==value]
        matches=by_value if len(by_value)==1 else by_label if not by_value else []
        if len(matches)!=1:continue
        selected=matches[0]
        step['op']='select'
        if selected.get('value') is not None:step['value']=selected['value'];step.pop('label',None)
        else:step.pop('value',None);step['label']=selected['label']
    return dict(raw,steps=steps)


def qa_validate_display_boundary(raw,formats):
    """Reject truncated numeric assertions without adopting observed numbers."""
    exact=raw.get('exact_check') or {}
    contract=formats.get(exact.get('selector'),{})
    text=exact.get('value')
    if not contract or not isinstance(text,str):return raw
    slots=contract.get('slots')
    if type(slots)is int and slots>0 and len(re.findall(r'-?\d+(?:,\d{3})*(?:\.\d+)?',text))!=slots:
        raise AutoQAPlanError('expected_values: 対象要素の全数値を仕様と入力から独立して計算してください。数値だけに切り詰めた期待値は禁止です')
    return raw


def qa_normalize_duration_inputs(raw,inventory):
    """Convert explicit duration HH:MM to minutes only with a minute label."""
    controls={n['selector']:n for n in inventory.get('controls',[])}
    steps=[dict(s) for s in raw.get('steps',[])]
    for step in steps:
        node=controls.get(step.get('selector'),{})
        label=str(node.get('label',''))
        match=re.fullmatch(r'(\d{1,3}):([0-5]\d)',str(step.get('value','')))
        if (step.get('op')=='fill' and node.get('type')=='number' and match
                and re.search(r'分|\bminutes?\b|\bmin\b',label,re.I)
                and re.search(r'休憩|所要|時間|期間|duration|break|minutes?',label,re.I)
                and not re.search(r'開始|終了|出発|到着|start|end|departure|arrival',label,re.I)):
            step['value']=str(int(match[1])*60+int(match[2]))
    return dict(raw,steps=steps)


def repair_qa_typed_inputs(raw,inventory,cfg,spec):
    normalized=qa_normalize_duration_inputs(raw,inventory)
    if normalized!=raw and not qa_bad_typed_inputs(normalized,inventory):return normalized
    raw=normalized
    bad=qa_bad_typed_inputs(raw,inventory)
    if not bad:return None
    indexes=[b['step_index'] for b in bad]
    schema={'type':'object','properties':{'inputs':{'type':'array','minItems':len(indexes),'maxItems':len(indexes),'items':{'type':'object','properties':{'step_index':{'type':'integer','enum':indexes},'value':{'type':'string','minLength':1,'maxLength':100}},'required':['step_index','value'],'additionalProperties':False}}},'required':['inputs'],'additionalProperties':False}
    def validate(answer):
        items=answer.get('inputs') if isinstance(answer,dict) else None
        if not isinstance(items,list) or len(items)!=len(indexes) or any(not isinstance(i,dict) or type(i.get('step_index'))is not int for i in items) or {i['step_index'] for i in items}!=set(indexes):raise AutoQAPlanError('型修復は指定の操作番号だけに値を指定してください')
        steps=[dict(s) for s in raw['steps']]
        for item in items:
            if not isinstance(item.get('value'),str) or not 1<=len(item['value'])<=100:raise AutoQAPlanError('型修復の入力値が不正です')
            steps[item['step_index']]['value']=item['value']
        fixed=dict(raw,steps=steps)
        if qa_bad_typed_inputs(fixed,inventory):raise AutoQAPlanError('型修復後も入力形式が不正です')
        return fixed
    return ai_json('独立QA。形式が不正な入力操作だけを、画面のtype・単位と元仕様に沿う値へ修復する。時刻と期間を区別し、期間のHH:MMは単位が分なら総分へ計算。dateはYYYY-MM-DD。元仕様で意味や単位を確定できなければ値を推測しない。既存の他の操作・期待値は変更しない。JSON {inputs:[{step_index,value}]}。\n元仕様:'+json.dumps(spec,ensure_ascii=False,separators=(',',':'))+'\n不正な入力:'+json.dumps(bad,ensure_ascii=False,separators=(',',':'))+'\n全操作:'+json.dumps(raw['steps'],ensure_ascii=False,separators=(',',':')),dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),300,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)


def validate_qa_inventory_actions(value,inventory,kind):
    if kind=='workflow':
        missing_inputs=qa_missing_initial_required_inputs(value,inventory)
        if missing_inputs:raise AutoQAPlanError('検査計画の必須入力が不足しています。仕様に合う値を入力してから送信してください: '+str(missing_inputs))
    if kind!='invalid':
        bad_dates=[b for b in qa_bad_typed_inputs(value,inventory) if b['control'].get('type')=='date']
        if bad_dates:raise AutoQAPlanError('日付入力欄はYYYY-MM-DD形式の実在する日付が必要です: '+str(bad_dates))
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
    if kind=='invalid':
        # When a submitted form has a known required field, test an actual
        # empty required input. Arbitrary strings such as "invalid_item" can
        # be valid and create another record instead of testing rejection.
        clicked={s.get('selector') for s in value.get('steps',[]) if s.get('op')=='click'}
        forms={n.get('form') for n in inventory['controls'] if n.get('tag')=='button' and n.get('selector') in clicked and n.get('form')}
        required=[n for n in inventory['controls'] if n.get('form') in forms and 'required' in n and n.get('tag') in ('input','textarea') and n.get('type') not in ('checkbox','radio','file','hidden')]
        if required:
            selectors={n['selector'] for n in required}
            emptied={s.get('selector') for s in value.get('steps',[]) if s.get('op')=='fill' and s.get('value')=='' and s.get('selector') in selectors}
            checked={c.get('selector') for c in value.get('checks',[]) if c.get('op')=='invalid'}
            if not emptied.intersection(checked):raise AutoQAPlanError('誤入力検査には送信フォームの必須欄を空にし、その欄のinvalidを確認してください。自由文字への任意文字列は不正値とは限りません: '+str(sorted(selectors)))
    return value


def qa_output_labels_from_html(source):
    """Read visible/accessible quantity names, excluding numeric output text."""
    class LabelTree(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True);self.root=dict(tag='root',attrs={},children=[]);self.stack=[self.root];self.ids={}
        def handle_starttag(self,tag,attrs):
            node=dict(tag=tag,attrs=dict(attrs),children=[],parent=self.stack[-1]);self.stack[-1]['children'].append(node)
            if node['attrs'].get('id'):self.ids[node['attrs']['id']]=node
            if tag not in ('input','br','hr','img','meta','link','source','area','base','embed','param','wbr'):self.stack.append(node)
        def handle_endtag(self,tag):
            for i in range(len(self.stack)-1,0,-1):
                if self.stack[i]['tag']==tag:self.stack=self.stack[:i];break
        def handle_data(self,text):
            if not any(n['tag'] in ('script','style') for n in self.stack):self.stack[-1]['children'].append(text)
    tree=LabelTree();tree.feed(source);tree.close()
    def text(node):
        if isinstance(node,str):return node
        return ''.join(text(c) for c in node['children'])
    result={}
    for key,node in tree.ids.items():
        if node['tag'] in ('input','select','textarea','button','script','style'):continue
        attrs=node['attrs'];label=''
        if attrs.get('aria-labelledby'):
            label=' '.join(text(tree.ids[i]) for i in attrs['aria-labelledby'].split() if i in tree.ids)
        if not label:label=attrs.get('aria-label','')
        if not label:
            candidates=[n for n in node['children'] if isinstance(n,dict) and n['tag'] in ('span','label') and not n['attrs'].get('id')]
            if not candidates:
                candidates=[n for n in node.get('parent',{}).get('children',[]) if isinstance(n,dict) and n is not node and n['tag'] in ('span','label') and not n['attrs'].get('id')]
            label=' '.join(text(n) for n in candidates)
        label=' '.join(label.split())
        if label and len(label)<=100:result['#'+key]=label
    return result


def qa_ratio_display(template):
    return bool(re.search(r'\{n0\}\s*[%％][^{}]*\{n1\}\s*/\s*\{n2\}',template))


def qa_fixed_quantity_format(template,label,projections):
    """Recognize units and linked measurement labels, never dynamic verdicts."""
    if len(projections)==1 and projections[0].get('metric') in ('sum','difference') and re.fullmatch(r'[¥￥]\s*\{n0\}',template):return True
    prefix=template.split('{n0}',1)[0]
    if prefix and (prefix.strip()!=label.strip() or not re.search(r'(?:率|数|合計|比率)$',label.strip())):return False
    body=template[len(prefix):]
    if re.fullmatch(r'\{n0\}\s*(?:件|人|名|円|問|分|時間)?',body):return True
    if body=='{n0}時間{n1}分' and len(projections)==2 and all(p.get('metric')=='time_component' for p in projections):return True
    if len(projections)==2 and all(p['metric']=='count' for p in projections) and re.fullmatch(r'\{n0\}件\s*[/／]\s*[^{}0-9]{1,30}\{n1\}件',body):return True
    if len(projections) in (3,4) and projections[0]['metric']=='percent' and projections[1]['metric']=='count' and projections[2]['where']=='all':
        same={k:v for k,v in projections[0].items() if k not in ('metric','basis')}=={k:v for k,v in projections[1].items() if k not in ('metric','basis')}
        pattern=r'\{n0\}[%％][（(][^{}0-9()（）]{1,30}\{n1\}/\{n2\}(?:[、,][^{}0-9()（）]{1,30}\{n3\})?[）)]'
        if same and re.fullmatch(pattern,body):return True
    return False


def qa_display_contracts_from_nodes(nodes):
    contracts={}
    for node in nodes:
        text=str(node.get('text','')).strip();selector=node.get('selector','')
        if not selector.startswith('#') or not text or len(text)>180:continue
        slots=[];styles=[];widths=[]
        def slot(match):
            key='{n'+str(len(slots))+'}';slots.append(key);styles.append('grouped' if ',' in match.group() else 'plain');widths.append(len(match.group()) if re.fullmatch(r'0[0-9]+',match.group()) else 0);return key
        template=re.sub(r'-?\d+(?:,\d{3})*(?:\.\d+)?',slot,text)
        if not 1<=len(slots)<=8:continue
        label=re.sub(r'-?\d+(?:\.\d+)?','数値',str(node.get('label','')))[:80]
        contracts[selector]=dict(template=template,slots=len(slots),label=label)
        if any(style=='grouped' for style in styles):contracts[selector]['number_styles']=styles
        if any(widths):contracts[selector]['number_widths']=widths
        for key in ('tag','ancestor_selectors'):
            if key in node:contracts[selector][key]=node[key]
        if len(contracts)>=24:break
    return contracts


def capture_qa_display_contracts(page):
    nodes=page.evaluate(r"""() => {
      const path=e=>{const parts=[];let n=e;while(n&&!n.id){const p=n.parentElement;if(!p)return '';parts.unshift(n.tagName.toLowerCase()+':nth-child('+([...p.children].indexOf(n)+1)+')');n=p;}return n?'#'+CSS.escape(n.id)+(parts.length?' > '+parts.join(' > '):''):'';};
      return [...document.querySelectorAll('[id],strong,output')].filter(e=>!['INPUT','SELECT','TEXTAREA','BUTTON','SCRIPT','STYLE'].includes(e.tagName)).map(e=>{
        const labelled=(e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText||'').join(' ').trim();
        const own=e.querySelector(':scope > span,:scope > label');const sibling=[...(e.parentElement?.children||[])].find(x=>x!==e&&['SPAN','LABEL'].includes(x.tagName));
        const ancestors=[];let n=e.parentElement;while(n){if(n.id)ancestors.push('#'+n.id);n=n.parentElement;}
        return {selector:e.id?'#'+CSS.escape(e.id):path(e),tag:e.tagName.toLowerCase(),ancestor_selectors:ancestors,text:e.innerText||'',label:labelled||e.getAttribute('aria-label')||own?.innerText||sibling?.innerText||e.closest('section')?.querySelector('h2,h3')?.innerText||''};
      }).filter(e=>e.selector&&e.text.length<=180);
    }""")
    return qa_display_contracts_from_nodes(nodes)


def qa_merge_display_inventory(inventory,formats):
    outputs=[dict(n) for n in inventory.get('outputs',[])]
    known={n['selector'] for n in outputs}
    for css,contract in formats.items():
        if css not in known and contract.get('tag')in ('strong','output') and contract.get('ancestor_selectors'):
            outputs.append(dict(selector=css,tag=contract['tag'],label=contract.get('label',''),ancestor_selectors=contract['ancestor_selectors']))
    return dict(inventory,outputs=outputs)


def qa_validate_explicit_percentage(text):
    """Check explicit arithmetic within an independent oracle, never UI output.

    Only integer percentages with an exact integral ratio are checked: rounding
    and zero-denominator domain policy must be specified separately.
    """
    match=re.search(r'(?P<p>-?\d+(?:\.\d+)?)\s*[%％].*?(?P<n>\d+)\s*/\s*(?P<d>\d+)',str(text))
    if match:
        numerator=decimal.Decimal(match['n']);denominator=decimal.Decimal(match['d'])
        if not denominator and numerator:
            raise AutoQAPlanError('expected_values: 分母0で分子が正の割合は不正です。入力と仕様から対象総数を再計算してください')
        if denominator:
            computed=numerator*100/denominator
            if computed==computed.to_integral_value() and decimal.Decimal(match['p'])!=computed:
                raise AutoQAPlanError('expected_values: 期待値内の割合と分数が算術的に矛盾しています。仕様と入力から再計算してください')
    return text


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
    if any(re.search(r'\{n\d+\}|\d',v) for v in literals):
        raise AutoQAPlanError('expected_literals: 数値や未解決の書式記号を文字列に混ぜないでください。数値はexpected_valuesに分離してください')
    styles=contract.get('number_styles',[])
    displayed=[format(decimal.Decimal(v),',f') if i<len(styles) and styles[i]=='grouped' else v for i,v in enumerate(values)]
    widths=contract.get('number_widths',[])
    displayed=[v.zfill(widths[i]) if i<len(widths) and type(widths[i])is int and 1<widths[i]<=6 and re.fullmatch(r'[0-9]+',v) else v for i,v in enumerate(displayed)]
    text=literals[0]+''.join(v+literals[i+1] for i,v in enumerate(displayed))
    qa_validate_explicit_percentage(text)
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


def qa_current_reference_clock(observed, current=None):
    """Recompute today's date in the browser's recorded timezone on resume."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    current=current or qa_datetime.now().astimezone()
    old=observed if isinstance(observed,dict) else {}
    zone=old.get('timezone')
    try:
        if not isinstance(zone,str) or not zone:raise ValueError('browser timezone unavailable')
        today=current.astimezone(ZoneInfo(zone)).date().isoformat()
        return dict(date=today,timezone=zone,source='current date in recorded browser timezone')
    except (ValueError,ZoneInfoNotFoundError):
        return dict(date=current.astimezone().date().isoformat(),source='current runner local date; browser timezone unavailable')


def qa_audit_date_oracle(raw, spec, cfg, prior, answer):
    """Audit date-based expectations against requirements, never UI output."""
    steps=[s for row in prior for s in row.get('steps',[])]+raw.get('steps',[])
    facts=qa_independent_date_facts(steps,cfg.get('_qa_reference_clock',{}))
    if not facts:return answer
    # A dated record is not necessarily a date-dependent business result.
    # Auditing every work-date was rejecting valid duration/capacity results.
    # Scope this extra audit to an explicit calendar rule or dated oracle basis;
    # arithmetic and other feature assertions still run their own checks.
    relevant=[spec.get('acceptance',[])[i] for i in raw.get('acceptance',[])
              if type(i)is int and 0<=i<len(spec.get('acceptance',[]))]
    date_rule=' '.join(map(str,relevant))+' '+str(spec.get('requested_outcome',''))+' '+' '.join(map(str,spec.get('must_have',[])))+' '+str(answer.get('oracle_basis',''))
    if not re.search(r'期限|期日|締切|締め切り|営業日|日数|前日|翌日|deadline|due date|overdue|calendar',date_rule,re.I):return answer
    schema={'type':'object','properties':{'valid':{'type':'boolean'},'reason':{'type':'string','minLength':8,'maxLength':300}},'required':['valid','reason'],'additionalProperties':False}
    prompt=('独立監査。日付の前後関係、仕様、状態と期待値・根拠が矛盾しないか確認。'
        '期限前後だけで処理済みや期限超過を決めず、状態と仕様も確認。正解を実画面から推測しない。日付規則の矛盾だけを判定し、予定時間と実績時間が異なること自体を不合格理由にしない。'
        'JSON {"valid":true,"reason":"判断根拠"}。矛盾または情報不足ならvalid:false。'
        '\n仕様:'+json.dumps(spec,ensure_ascii=False,separators=(',',':'))[:3000]
        +'\n日付差分:'+json.dumps(facts,ensure_ascii=False,separators=(',',':'))
        +'\n操作:'+json.dumps(steps,ensure_ascii=False,separators=(',',':'))[:2500]
        +'\n期待値と理由:'+json.dumps({'expected':answer.get('exact_check'),'basis':answer.get('oracle_basis')},ensure_ascii=False))
    def validate(result):
        if not isinstance(result,dict) or result.get('valid') is not True or not isinstance(result.get('reason'),str) or len(result['reason'].strip())<8:
            raise AutoQAPlanError('expected_values: 日付を使う期待値の独立監査が未合格: '+str(result)[:400])
        return result
    ai_json(prompt,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),250,schema=schema,max_attempts=1,
        request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)
    return answer


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


def qa_evaluate_record_events(steps,events):
    """Reference state reducer: no rendered values and no model arithmetic."""
    clicks=[i for i,step in enumerate(steps) if step.get('op')=='click']
    if not isinstance(events,list) or [e.get('step_index') for e in events if isinstance(e,dict)]!=clicks:
        raise AutoQAPlanError('参照状態: 全クリックを順番どおり過不足なく対応付けてください')
    records=set();trace=[]
    for event in events:
        index=event['step_index'];effect=event.get('effect');target=event.get('target')
        if type(index)is not int or effect not in ('create','update','delete','none'):
            raise AutoQAPlanError('参照状態: 未対応の状態遷移です')
        if effect in ('create','none') and target is not None:
            raise AutoQAPlanError('参照状態: 新規操作・状態不変操作に既存対象は指定できません')
        if effect in ('update','delete') and (type(target)is not int or target not in records):
            raise AutoQAPlanError('参照状態: 編集・削除の対象記録が存在しません')
        if effect=='create':records.add(index)
        elif effect=='delete':records.remove(target)
        trace.append(dict(step_index=index,effect=effect,count=len(records),record_origins=sorted(records)))
    return dict(count=len(records),trace=trace)


def qa_record_event_schema(active):
    """Only offer effects and record origins possible in reference state."""
    active=sorted(active)
    effects=['create','none']+(['update','delete'] if active else [])
    return {'type':'object','properties':{'effect':{'type':'string','enum':effects},'target':{'enum':[None]+active}},'required':['effect','target'],'additionalProperties':False}


def qa_reference_model_config(cfg):
    """Keep semantic mapping separate from a retried code/planning model."""
    return dict(cfg,model=cfg.get('qa_mapping_model') or cfg.get('qa_oracle_model') or cfg['model'])


def qa_component_events(steps,cfg):
    """Normative driver for an explicitly selected, versioned record component.

    This is a test actor contract, not a claim about observed app behavior.
    Unknown controls/lifecycles decline the driver and retain semantic QA.
    """
    if cfg.get('qa_component_contract')!='native-record-create-v1':return None
    nodes={n['selector']:n for n in cfg.get('_qa_binding_controls',[])+cfg.get('_qa_binding_outputs',[])}
    form=nodes.get('#recordForm',{});submit=nodes.get('#saveRecord',{})
    if form.get('tag')!='form' or submit.get('form')!='#recordForm' or submit.get('tag')!='button' or submit.get('type','submit')!='submit':return None
    if nodes.get('#recordCount',{}).get('tag')not in ('strong','output','span') or nodes.get('#recordRows',{}).get('tag')!='tbody':return None
    extra=cfg.get('qa_component_passive_buttons') or []
    if not isinstance(extra,(list,tuple)) or any(not isinstance(css,str) for css in extra):return None
    passive={'#downloadCsv','#downloadJson','#clearForm'}|set(extra)
    events=[]
    for index,step in enumerate(steps):
        op=step.get('op')
        if op not in ('fill','select','check','click','wait','reload','download_csv','download_json'):return None
        if op!='click':continue
        css=step.get('selector')
        if css=='#saveRecord':events.append(dict(step_index=index,effect='create',target=None))
        elif css in passive and nodes.get(css,{}).get('tag')=='button' and nodes[css].get('type')=='button':
            event=dict(step_index=index,effect='none',target=None)
            if css=='#clearForm':event['reset_inputs']=True
            events.append(event)
        else:return None
    return events


def qa_normalize_component_inputs(value):
    seen={};steps=[]
    for step in value.get('steps',[]):
        if step.get('op')=='click' and step.get('selector')=='#clearForm' and steps and steps[-1]==step:continue
        if step.get('op') in ('fill','select','check'):
            identity={k:step.get(k) for k in ('op','value','label','nth') if k in step}
            css=step.get('selector')
            if css in seen and seen[css]==identity:continue
            seen[css]=identity
        else:seen={}
        steps.append(step)
    return dict(value,steps=steps)


def qa_duration_pair_format(contract):
    count=contract.get('slots');template=contract.get('template','')
    if type(count)is not int or not 2<=count<=8 or count%2:return False
    pairs=[r'\{n'+str(i)+r'\}時間\{n'+str(i+1)+r'\}分' for i in range(0,count,2)]
    return re.fullmatch(r'\s*[/／]\s*'.join(pairs),template) is not None


def qa_quantity_scope(contract,index):
    template=contract.get('template','');label=contract.get('label','').strip()
    groups=[part.strip() for part in re.split(r'\s*[/／]\s*',label)]
    if len(groups)==contract.get('slots') and len(groups)>1 and all(groups):return groups[index]
    if qa_duration_pair_format(contract) and len(groups)*2==contract.get('slots') and all(groups):return groups[index//2]
    before=template.split('{n'+str(index)+'}',1)[0]
    suffix=re.split(r'[,、（(}/]',before)[-1].strip()
    if index and suffix and not re.search(r'\{n\d+',suffix):return suffix
    return label or contract.get('selector','') or '指定した数値項目'


def qa_projection_witnesses(rows,left,right,controls,clock):
    """Counterexamples are declared test inputs, never browser observations."""
    datasets=[rows];seen=set();result=[]
    if rows:
        for node in controls:
            css=node['selector']
            if css not in rows[0]:continue
            values=[o.get('value') for o in node.get('options',[]) if o.get('value')]
            if node.get('type')=='date':
                try:
                    import datetime as witness_time
                    reference=witness_time.date.fromisoformat(clock['date'])
                    values += [(reference+witness_time.timedelta(days=offset)).isoformat() for offset in (-1,0,1)]
                except (KeyError,ValueError,TypeError):pass
            for value in values:
                if node.get('min') and str(value)<str(node['min']) or node.get('max') and str(value)>str(node['max']):continue
                changed=[dict(row) for row in rows];changed[0][css]=value;datasets.append(changed)
    for dataset in datasets:
        signature=json.dumps(dataset,sort_keys=True,ensure_ascii=False)
        if signature in seen:continue
        seen.add(signature)
        try:a=qa_evaluate_projection(dataset,left,clock);b=qa_evaluate_projection(dataset,right,clock)
        except (ValueError,TypeError,KeyError):continue
        if a!=b:result.append(dict(declared_inputs=dataset,first_result=a,second_result=b))
        if len(result)>=3:break
    return result


def qa_source_state_composition(requirements,descriptor,controls,base,field):
    """Compile only explicit finite-set definitions and their named conjunction.

    This bounded Japanese grammar is requirement-side set algebra, not an
    interpretation of renderer code or observed quantities. Unsupported text
    falls back to the independent semantic mapper.
    """
    nodes={n['selector']:n for n in controls};node=nodes.get(field,{})
    options=list(dict.fromkeys(o.get('value') for o in node.get('options',[]) if o.get('value') and not o.get('disabled')))
    if not 2<=len(options)<=5:return None
    source=' '.join([str(requirements.get('outcome',''))]+list(map(str,requirements.get('must_have',[])))+list(map(str,requirements.get('workflow',[]))))
    atom='(?:'+'|'.join(re.escape(v) for v in sorted(options,key=len,reverse=True))+')'
    pattern=re.compile(r'(?:^|[。 、:：は])(?P<excluded>'+atom+r'(?:・'+atom+r')*)を除く(?P<name>[^\s。、「」,]{1,30}?)件数(?=[。 、,]|を表示|を数え|$)')
    definitions={}
    for match in pattern.finditer(source):
        if re.match(r'を(?:表示|数え)(?:しない|ない|ません)',source[match.end():]):return None
        name=match['name'];excluded=match['excluded'].split('・');members=[v for v in options if v not in excluded]
        owners=[n['selector'] for n in controls if set(excluded)<={o.get('value') for o in n.get('options',[]) if o.get('value') and not o.get('disabled')}]
        if owners!=[field]:return None
        if name in definitions and definitions[name]['members']!=members:raise AutoQAPlanError('元仕様で同じ状態条件の定義が矛盾しています: '+name)
        definitions[name]=dict(name=name,field=field,members=members,excluded=excluded,source_excerpt=match.group().lstrip('。 、:：は'))
    matches=[];target=str(descriptor.get('target_label',''))
    for name,definition in definitions.items():
        if base.get('where')=='in' and target==name:
            matches.append((definition,definition['source_excerpt']))
        elif base.get('where')=='before_date':
            date_node=nodes.get(base.get('field'),{});label=date_node.get('label','')
            if date_node.get('type')!='date' or not label:continue
            expression=r'(?:^|[。 、:：は])'+re.escape(label)+r'が(?:今日|基準日)より前かつ'+re.escape(name)+'の'+re.escape(target)+r'件数(?=[。 、,]|を表示|を数え|$)'
            found=re.search(expression,source)
            if found:
                if re.match(r'を(?:表示|数え)(?:しない|ない|ません)',source[found.end():]):return None
                matches.append((definition,found.group().lstrip('。 、:：は')))
    if len(matches)!=1:return None
    definition,expression=matches[0];result=dict(base);result.pop('status_family',None)
    if result['where']=='in':result['members']=definition['members']
    else:result['also']=dict(field=field,members=definition['members'])
    result['basis']='元仕様で明示された集合「'+definition['name']+'」と条件の合成'
    return result,dict(valid=True,method='bounded explicit requirement set definition and named conjunction; not model consensus or observed values',source_definition=definition,source_expression=expression,classified_states={v:int(v in definition['members']) for v in options})


def qa_resolve_status_partition(left,right,requirements,descriptor,controls,generate,key):
    """Rebuild a disputed subset from every native status, not two bad sets."""
    # An explicit source definition can resolve a disagreement about the
    # whole calculation family, not only a disagreement within one family.
    # Enumerate requirement-supported count rules; accept exactly one.
    if left.get('metric')==right.get('metric')=='count':
        explicit=[]
        for state in controls:
            field=state.get('selector')
            if not field or not state.get('options'):continue
            bases=[dict(metric='count',where='in',field=field,members=[])]
            bases += [dict(metric='count',where='before_date',field=n['selector'],members=[]) for n in controls if n.get('type')=='date' and n.get('selector')]
            for base in bases:
                resolved=qa_source_state_composition(requirements,descriptor,controls,base,field)
                if resolved is not None and resolved not in explicit:explicit.append(resolved)
        if len(explicit)==1:
            rule,audit=explicit[0]
            return rule,dict(audit,original_proposed=left,original_independent=right)
        if len(explicit)>1:raise AutoQAPlanError('元仕様の明示的な件数定義が複数の入力欄に対応しています')
    stable=('metric','where','field','reference_input','rounding','places')
    if any(left.get(k)!=right.get(k) for k in stable):return None
    if left.get('where')=='in':field=left.get('field');base=dict(left)
    elif left.get('where')in ('before_date','on_reference_date','on_input_date'):
        fields={p['also']['field'] for p in (left,right) if isinstance(p.get('also'),dict) and p['also'].get('field')}
        if not fields:
            fields={n['selector'] for n in controls if 2<=len([o for o in n.get('options',[]) if o.get('value')])<=5}
        if len(fields)!=1:return None
        field=next(iter(fields));base=dict(left);base.pop('also',None)
    else:return None
    node=next((n for n in controls if n.get('selector')==field),{})
    options=list(dict.fromkeys(o['value'] for o in node.get('options',[]) if o.get('value') and not o.get('disabled')))
    if not 2<=len(options)<=5:return None
    explicit=qa_source_state_composition(requirements,descriptor,controls,base,field)
    if explicit is not None:return explicit[0],dict(explicit[1],original_proposed=left,original_independent=right)
    clauses=[str(requirements.get('outcome',''))]+list(requirements.get('must_have',[]))+list(requirements.get('workflow',[]))
    clauses=[v for v in clauses if v.strip()]+['画面で宣言された項目名: '+descriptor['target_label']]
    schema=dict(type='object',properties=dict(membership=dict(type='array',items=dict(type='integer',enum=[-1,0,1]),minItems=len(options),maxItems=len(options)),evidence_id=dict(type='integer',enum=list(range(len(clauses))))),required=['membership','evidence_id'],additionalProperties=False)
    mappings=[];responses=[]
    for reverse in (False,True):
        ordered=list(reversed(options)) if reverse else options
        context=dict(output=descriptor,numbered_requirements=clauses,ordered_statuses=ordered,
                     fixed_condition={k:base[k] for k in ('where','field','reference_input') if k in base} if base['where']!='in' else None)
        def validate(value):
            membership=value.get('membership') if isinstance(value,dict) else None
            if not isinstance(membership,list) or len(membership)!=len(ordered) or any(type(v)is not int or v not in (-1,0,1) for v in membership) or type(value.get('evidence_id'))is not int or not 0<=value['evidence_id']<len(clauses):raise AutoQAPlanError('状態ごとの集計対象を元要件から確定できません。未確定は合格にしません')
            return value
        prompt=('独立した意味判定。出力項目「'+descriptor['target_label']+'」の集計対象を、ordered_statusesの各状態について個別に決める。含める=1、除外=0、要件不足=-1。membershipは提示順と同じ長さ。固定の日付条件があれば変更せず、その条件を満たす記録の各状態を判定する。今回入力済みの状態だけに限定しない。前の候補は示さない。原文の根拠番号evidence_idも返す。JSON {membership:[1,0],evidence_id:0}。\n'+json.dumps(context,ensure_ascii=False,separators=(',',':')))
        answer=generate('primary-projection-membership-'+key+('-reverse' if reverse else '-forward'),prompt,schema,validate,context)
        mappings.append(dict(zip(ordered,answer['membership'])));responses.append(answer)
    final=dict(mappings[0]);resolved=[]
    for status_index,status in enumerate(options):
        if mappings[0][status]==mappings[1][status] and mappings[0][status]in (0,1):continue
        bit_schema=dict(type='object',properties=dict(decision=dict(type='string',enum=['included','excluded','unknown']),evidence_id=schema['properties']['evidence_id']),required=['decision','evidence_id'],additionalProperties=False)
        votes=[]
        for excluded in (False,True):
            def validate_bit(value):
                if not isinstance(value,dict) or value.get('decision')not in ('included','excluded') or type(value.get('evidence_id'))is not int or not 0<=value['evidence_id']<len(clauses):raise AutoQAPlanError('不一致になった状態1個の意味が元要件から確定できません')
                return value
            bit_context=dict(output=descriptor,numbered_requirements=clauses,status=status,fixed_condition=context.get('fixed_condition'))
            question=('集計から除く状態か、含める状態かを判断する' if excluded else '集計に含める状態か、除く状態かを判断する')
            prompt=('独立した意味判定。対象「'+descriptor['target_label']+'」について状態「'+status+'」が'+question+'。回答の意味は質問順によって反転しない。included=集計対象、excluded=集計対象外、unknown=原文不足。提示済み入力にこの状態があるかではなく、元要件の一般則を判定する。他担当の回答は示さない。固定の日付条件があればその条件を満たす記録について答える。JSON {decision:includedまたはexcludedまたはunknown,evidence_id:根拠番号}。\n'+json.dumps(bit_context,ensure_ascii=False,separators=(',',':')))
            answer=generate('primary-projection-state-'+key+'-'+str(status_index)+('-exclude' if excluded else '-include'),prompt,bit_schema,validate_bit,dict(bit_context,question='excluded' if excluded else 'included'))
            votes.append(dict(included=int(answer['decision']=='included'),response=answer))
        qa_require_independent_agreement(votes[0]['included'],votes[1]['included'],descriptor['target_label']+'の状態'+status+'の正逆質問')
        final[status]=votes[0]['included'];resolved.append(dict(status=status,votes=votes))
    if any(value not in (0,1) for value in final.values()):raise AutoQAPlanError('未確定の状態が残るため集計を合格にできません')
    agreement=dict(valid=True,scope=descriptor['target_label']+'の全状態の独立分類',initial_classifications=mappings,resolved_disagreements=resolved)
    members=[v for v in options if final[v]]
    if base['where']=='in':base['members']=members
    elif set(members)!=set(options):base['also']=dict(field=field,members=members)
    base['basis']=descriptor['target_label']+'の元要件に基づく全状態の独立分類'
    base.pop('status_family',None)
    return base,dict(agreement,method='independent complete native-status classification in reversed order; no prior subsets disclosed',original_proposed=left,original_independent=right,classified_states=final,responses=responses)


def qa_resolve_projection_binding(left,right,requirements,descriptor,rows,controls,clock,generate,key):
    partition=qa_resolve_status_partition(left,right,requirements,descriptor,controls,generate,key)
    if partition is not None:
        selected,audit=partition
        return selected,audit
    witnesses=qa_projection_witnesses(rows,left,right,controls,clock)
    if not witnesses:raise AutoQAPlanError('独立対応が不一致です。候補を区別する有効な入力例が未確定のため、合格にはできません')
    clauses=[str(requirements.get('outcome',''))]+list(requirements.get('must_have',[]))+list(requirements.get('workflow',[]))
    clauses=[v for v in clauses if v.strip()]+['画面で宣言された項目名: '+descriptor['target_label']]
    schema=dict(type='object',properties=dict(choice=dict(type='integer',enum=[-1,0,1]),evidence_id=dict(type='integer',enum=list(range(len(clauses))))),required=['choice','evidence_id'],additionalProperties=False)
    answers=[]
    for reverse in (False,True):
        options=[right,left] if reverse else [left,right]
        def validate(value):
            if isinstance(value,dict) and set(value)=={'selected','evidence_id'}:
                if value['selected'] in options and type(value.get('evidence_id'))is int and 0<=value['evidence_id']<len(clauses):return value
            if not isinstance(value,dict) or set(value)!={'choice','evidence_id'} or type(value.get('choice'))is not int or value['choice']not in (0,1) or type(value.get('evidence_id'))is not int or not 0<=value['evidence_id']<len(clauses):raise AutoQAPlanError('候補間の意味を元要件で確定できません。第三の規則や仕様修正が必要です')
            return dict(selected=options[value['choice']],evidence_id=value['evidence_id'])
        examples=[dict(declared_inputs=w['declared_inputs'],candidate_results=[w['second_result'],w['first_result']] if reverse else [w['first_result'],w['second_result']]) for w in witnesses]
        context=dict(output=descriptor,requirements=clauses,declared_settings_and_clock=clock,candidates=options,witnesses=examples)
        prompt=('独立した対応の再診断。今回の対象は「'+descriptor['target_label']+'」1項目だけ。二つの計算規則のどちらが番号付き元要件とこの項目名に対応するか選ぶ。提示した数値は新しい宣言入力をコードで計算した比較例で、画面の実測値ではない。前の担当の選択は示さない。どちらも不適切・要件不足ならchoice=-1。原文の根拠をevidence_idで指定。JSON {choice:0または1または-1,evidence_id:原文番号}。\n'+json.dumps(context,ensure_ascii=False,separators=(',',':')))
        answer=generate('primary-projection-resolution-'+key+('-reverse' if reverse else '-forward'),prompt,schema,validate,context)
        answers.append(answer)
    agreement=qa_require_independent_agreement(answers[0]['selected'],answers[1]['selected'],descriptor['target_label']+'の順序反転再診断')
    return answers[0]['selected'],dict(agreement,method='two independent order-reversed source-grounded resolutions',original_proposed=left,original_independent=right,witnesses=witnesses,responses=answers)


def qa_record_binding_context(steps,events,index,controls):
    """Supply reference inputs and control identity, never app output values."""
    prefix=steps[:index]
    reference=qa_evaluate_record_events(prefix,events)
    origins=reference['trace'][-1]['record_origins'] if reference['trace'] else []
    rows=qa_reference_rows(prefix,events)
    last_commit=max((e['step_index'] for e in events if e['effect'] in ('create','update','delete') or e.get('reset_inputs')),default=-1)
    entered={step['selector']:step.get('value',step.get('label')) for step in prefix[last_commit+1:] if step.get('op') in ('fill','select','check')}
    nodes={n['selector']:n for n in controls}
    used=set(entered)|{css for row in rows for css in row}
    labels={css:nodes[css].get('label',nodes[css].get('text','')) for css in sorted(used) if css in nodes}
    click=steps[index];node=nodes.get(click.get('selector'),{})
    return dict(active_records=[dict(origin=origin,fields=row) for origin,row in zip(origins,rows)],entered_since_commit=entered,
                field_labels=labels,current_control={k:node[k] for k in ('selector','tag','type','form','label','text') if k in node},
                intervening_clicks=[step for step in prefix[last_commit+1:] if step.get('op')=='click'])


def qa_bind_record_clicks(steps,source,selector,cfg,folder,key):
    """The runner owns event enumeration; a model handles one click only."""
    cfg=qa_reference_model_config(cfg)
    component=qa_component_events(steps,cfg)
    if component is not None:
        write_framework_json(Path(folder)/(key+'-component-contract.json'),dict(contract=cfg['qa_component_contract'],passive_buttons=cfg.get('qa_component_passive_buttons',[]),steps=steps,method='declared test actor transitions; browser checks still required',events=component))
        return component
    events=[]
    for index,step in enumerate(steps):
        if step.get('op')!='click':continue
        known_prefix=qa_component_events(steps[:index+1],cfg)
        if known_prefix is not None:
            write_framework_json(Path(folder)/(key+'-component-prefix-'+str(index)+'.json'),dict(contract=cfg['qa_component_contract'],events=known_prefix,method='declared component prefix; unknown actions remain semantic QA'))
            events.append(known_prefix[-1]);continue
        facts=qa_record_binding_context(steps,events,index,cfg.get('_qa_binding_controls',[]))
        context=dict(policy='record-choice-2',blind=bool(cfg.get('_qa_blind_binding')),source=source,selector=selector,prefix=steps[:index+1],prior_events=events,facts=facts,model=cfg['model'])
        digest=hashlib.sha256(json.dumps(context,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        directory=folder/(key+'-reference-events');directory.mkdir(exist_ok=True)
        path=directory/(digest+'.json')
        def validate(value):
            if not isinstance(value,dict) or value.get('effect') not in ('create','update','delete','none'):raise AutoQAPlanError('参照状態: 一つのクリックの分類が必要です')
            event=dict(step_index=index,effect=value['effect'],target=value.get('target'))
            qa_evaluate_record_events(steps[:index+1],events+[event])
            return event
        event=None
        if path.exists():
            try:event=validate(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError,KeyError,TypeError):pass
        if event is None:
            previous_state=qa_evaluate_record_events(steps[:index],events)
            active=previous_state['trace'][-1]['record_origins'] if previous_state['trace'] else []
            choices=[dict(effect='create',target=None),dict(effect='none',target=None)]+[dict(effect=effect,target=origin) for origin in active for effect in ('update','delete')]
            schema=dict(type='object',properties=dict(choice=dict(type='integer',enum=list(range(len(choices))))),required=['choice'],additionalProperties=False)
            prompt=('今回のクリック1個を元要件に対応付け、提示された選択肢番号だけをJSON {"choice":整数}で回答する。createは新しい保存記録を追加。noneはCSV/JSON出力、画面表示、編集画面を開く等の保存記録を変えない操作。update/deleteは表示済みの作成操作を起源とする既存記録だけ。targetを作ったり操作番号を件数と解釈しない。'
                +'\n元要件:'+source+'\n対象集計:'+selector+'\n選択肢:'+json.dumps(list(enumerate(choices)),ensure_ascii=False)
                +'\n保存済み記録と今回の未保存入力（参照計算であり画面実測値ではない）:'+json.dumps(facts,ensure_ascii=False,separators=(',',':'))+'\n今回のクリック:'+json.dumps(step,ensure_ascii=False))
            if cfg.get('_qa_blind_binding'):prompt='独立担当。別の担当の提案は参照せず、元要件と操作履歴だけから選択する。\n'+prompt
            def choose(value):
                write_framework_json(directory/(digest+'-response.json'),value)
                if isinstance(value,dict) and type(value.get('choice'))is int and 0<=value['choice']<len(choices):return validate(choices[value['choice']])
                # Valid legacy receipts remain readable; no unknown target can pass.
                if isinstance(value,dict) and value in choices:return validate(value)
                raise AutoQAPlanError('参照状態: 提示された操作対応の選択肢を1個指定してください')
            event=ai_json(prompt,dict(cfg,_schema_in_prompt=True,_bounded_json_retry=True,_json_transport_evidence=str(directory/(digest+'-transport.json'))),100,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=choose)
            write_framework_json(path,event)
        events.append(event)
    return events


def qa_reference_click_audit_cases(steps,events):
    """Separate field editing from commit actions without reading app output."""
    proposals={e['step_index']:e for e in events};inputs={};cases=[]
    for index,step in enumerate(steps):
        if step.get('op') in ('fill','select','check'):
            inputs[step.get('selector','')]=dict(op=step['op'],value=step.get('value'),label=step.get('label'))
        elif step.get('op')=='click':
            cases.append(dict(click_index=index,click=step,entered_fields=dict(inputs),proposed_effect=proposals.get(index)))
    return cases


def qa_reference_mapping_audit_prompt(selector,steps,binding):
    """Audit one component contract, not coverage of an entire product."""
    return ('独立した操作対応の監査。今回の判定対象は、選択した仕様に照らして、この表示が全保存記録の件数か、各クリックのcreate/update/delete/noneと対象記録が正しいか、の二点だけ。'
        '初期状態は空の保存領域。入力欄へのfill/select/checkは保存記録の作成ではない。入力済み欄があっても保存クリック以前の記録を仮定しない。番号は操作識別子であり件数ではない。以下の資料はクリックごとに入力値を付けたもので、入力欄の数を記録数と解釈しない。'
        'データ形式の定義: step_indexは元の操作番号。createは新しい記録を作るため既存対象targetはnullが正しい。noneもtargetはnull。update/deleteだけは先行createのstep_indexをtargetに指定する。新規追加のtargetがnullであることを対象情報不足と判断しない。'
        '全製品機能の網羅性を採点しない。返金計算や期限確認等の別機能が今回の操作にないことを不合格理由にしない。それらの完成条件は別の機能検査が担当する。'
        '部分的な検査であること自体は不備ではない。保存しない操作をcreateとした等の具体的な対応誤り、関連しない仕様の選択、対象記録の誤りや情報不足はvalid:falseとし根拠を示す。件数の算術はプログラムが行う。JSON {valid,reason}。'
        +'\n対象の表示:'+selector+'\n対応する元仕様の原文:'+binding['source_quote']
        +'\nクリックごとの監査資料:'+json.dumps(qa_reference_click_audit_cases(steps,binding['events']),ensure_ascii=False,separators=(',',':'))
        +'\n対応案:'+json.dumps(dict(quantity=binding['quantity'],events=binding['events']),ensure_ascii=False,separators=(',',':')))


def qa_reference_count_oracle(raw,contract,spec,cfg,folder,key,prior):
    """Pilot reference semantics for explicit record-count outputs only.

    AI maps business actions; code alone carries state and calculates count.
    A separate semantic audit is still required. Unmapped outputs use the
    existing path and receive no claim of reference-model verification.
    """
    selector=raw['exact_check']['selector']
    if not re.search(r'count|件数|人数',selector+' '+str(contract.get('label','')),re.I):return None
    steps=[step for row in prior for step in row.get('steps',[])]+raw.get('steps',[])
    component=qa_component_events(steps,cfg)
    if component is not None and selector=='#recordCount':
        reference=qa_evaluate_record_events(steps,component)
        write_framework_json(Path(folder)/(key+'-reference-count-proof.json'),dict(contract=cfg['qa_component_contract'],steps=steps,events=component,reference=reference,method='declared registration-total component contract; actual browser still required'))
        return dict(raw,exact_check=dict(op='text_equals',selector=selector,value=str(reference['count'])),reference_count=reference,oracle_basis='宣言した記録コンポーネントの登録総数と独立参照計算')
    if any(step.get('op') not in ('fill','select','check','click','wait') for step in steps):return None
    source_items=[v for v in [spec.get('requested_outcome')]+list(spec.get('must_have') or [])+list(spec.get('acceptance') or []) if isinstance(v,str) and v.strip()]
    if not source_items:return None
    source=json.dumps(list(enumerate(source_items)),ensure_ascii=False)
    event_schema={'type':'object','properties':{'step_index':{'type':'integer','minimum':0},'effect':{'type':'string','enum':['create','update','delete','none']},'target':{'type':['integer','null']}},'required':['step_index','effect','target'],'additionalProperties':False}
    schema={'type':'object','properties':{'quantity':{'type':'string','enum':['record_count','other']},'source_index':{'type':'integer','enum':list(range(len(source_items)))},'events':{'type':'array','maxItems':0,'items':event_schema}},'required':['quantity','source_index','events'],'additionalProperties':False}
    prompt=('仕様の状態遷移を操作へ対応付ける担当。件数の計算や最終件数の回答は禁止。対象が全保存記録の件数ならquantity=record_count、それ以外や不明ならother。'
        'この呼出しでは対象の集計種類と仕様番号だけを判断。操作分類は別の呼出しで行うためeventsは必ず空配列。操作や件数を列挙しない。'
        'フィルタ後件数・出席人数等の部分集合はother。source_indexは対応する元仕様の番号。引用文はプログラムが取り出す。JSON {quantity,source_index,events:[{step_index,effect,target}]}。'
        +'\n元仕様:'+source+'\n対象:'+selector+' '+str(contract.get('label',''))
        +'\n全操作:'+json.dumps(list(enumerate(steps)),ensure_ascii=False,separators=(',',':')))
    def validate(value):
        write_framework_json(folder/(key+'-reference-binding-response.json'),value)
        if not isinstance(value,dict) or value.get('quantity') not in ('record_count','other') or type(value.get('source_index'))is not int or not 0<=value['source_index']<len(source_items):
            raise AutoQAPlanError('参照状態: 元仕様からの引用と集計対象の対応が必要です')
        if value.get('events')!=[]:raise AutoQAPlanError('参照状態: 集計対象の選択ではeventsは空配列です')
        return dict(value,source_quote=source_items[value['source_index']])
    mapping_cfg=qa_reference_model_config(cfg)
    binding=ai_json(prompt,dict(mapping_cfg,_schema_in_prompt=False,_bounded_json_retry=True),200,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_part_timeout',180)),validator=validate)
    if binding['quantity']=='other':return None
    binding['events']=qa_bind_record_clicks(steps,source,selector,cfg,folder,key)
    audit_schema={'type':'object','properties':{'valid':{'type':'boolean'},'reason':{'type':'string','minLength':12,'maxLength':300}},'required':['valid','reason'],'additionalProperties':False}
    def audit_validate(value):
        write_framework_json(folder/(key+'-reference-audit-response.json'),value)
        if not isinstance(value,dict) or value.get('valid') is not True or not isinstance(value.get('reason'),str) or len(value['reason'].strip())<12:
            raise AutoQAPlanError('参照状態: 操作と仕様の独立監査が未合格: '+str(value))
        return value
    if qa_component_events(steps,cfg) is not None:
        audit=dict(valid=True,method='declared component transitions; independently evaluated count')
    else:
        audit=ai_json(qa_reference_mapping_audit_prompt(selector,steps,binding),dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True),250,schema=audit_schema,max_attempts=1,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=audit_validate)
    result=qa_evaluate_record_events(steps,binding['events'])
    write_framework_json(folder/(key+'-reference-count-proof.json'),dict(binding=binding,audit=audit,reference=result,steps=steps,source=source,method='independent state reducer; browser verification still required'))
    return dict(raw,exact_check=dict(op='text_equals',selector=selector,value=str(result['count'])),oracle_basis=('宣言したコンポーネント操作契約と独立参照計算' if qa_component_events(steps,cfg) is not None else '仕様と操作の対応を独立監査し、参照状態遷移で件数を計算'),reference_count=result)


def qa_reference_composite_oracle(raw,formats,spec,cfg,folder,key,prior):
    """Use the reference count in a composite summary; other facts stay independent."""
    exact=raw.get('exact_check',{});contract=formats.get(exact.get('selector'),{})
    template=contract.get('template','')
    if not template.startswith('{n0}件 / '):return None
    component=dict(contract,label=str(contract.get('label',''))+' 先頭の件数（全保存記録か元仕様で確認）')
    reference=qa_reference_count_oracle(raw,component,spec,cfg,folder,key,prior)
    if reference is None:return None
    count=reference['reference_count']['count']
    checks=raw.get('checks',[])
    indexes=[i for i,c in enumerate(checks) if c.get('selector')==exact['selector'] and c.get('nth',0)==exact.get('nth',0) and c.get('op') in ('text_equals','text_contains')]
    contains=[i for i in indexes if checks[i]['op']=='text_contains']
    schema={'type':'object','properties':{'suffix':{'type':'string','minLength':1,'maxLength':180},'contains_values':{'type':'array','minItems':len(contains),'maxItems':len(contains),'items':{'type':'string','minLength':1,'maxLength':180}},'basis':{'type':'string','minLength':12,'maxLength':300}},'required':['suffix','contains_values','basis'],'additionalProperties':False}
    prompt=('独立QA。全記録件数は参照状態計算で確定済み。件数は回答せず、先頭の件数の後ろに続く表示suffix（件 / から開始）と、指定の部分一致期待値だけを元仕様と入力から判断。'
        '期限超過数や稼働状態など残りの業務判断は独立して計算。表示形式は正解を意味しない。JSON {suffix,contains_values,basis}。'
        +'\n元仕様:'+json.dumps(spec,ensure_ascii=False,separators=(',',':'))
        +'\n確定した件数:'+str(count)+'\n参照計算過程:'+json.dumps(reference['reference_count'],ensure_ascii=False)
        +'\n先行入力:'+json.dumps([r.get('steps',[]) for r in prior],ensure_ascii=False)
        +'\n今回入力:'+json.dumps(raw.get('steps',[]),ensure_ascii=False)
        +'\n基準日:'+json.dumps(cfg.get('_qa_reference_clock',{}),ensure_ascii=False)
        +'\n数値を除去した表示形式:'+template
        +'\n部分一致対象:'+json.dumps([dict(selector=checks[i]['selector'],op=checks[i]['op']) for i in contains],ensure_ascii=False))
    def validate(answer):
        write_framework_json(folder/(key+'-composite-response.json'),answer)
        suffix=answer.get('suffix') if isinstance(answer,dict) else None
        literals=answer.get('contains_values') if isinstance(answer,dict) else None
        if not isinstance(suffix,str) or not suffix.startswith('件 / ') or re.search(r'\{n\d+\}',suffix) or not isinstance(literals,list) or len(literals)!=len(contains) or not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:
            raise AutoQAPlanError('参照状態: 件数以外の期待表示と根拠が不足しています')
        expected=str(count)+suffix
        if len(re.findall(r'-?\d+(?:\.\d+)?',expected))!=contract.get('slots'):
            raise AutoQAPlanError('参照状態: 複合表示の残りの数値が不足しています')
        revised=[dict(c) for c in checks]
        for i in indexes:
            if revised[i]['op']=='text_equals':revised[i]['value']=expected
        for i,value in zip(contains,literals):
            if not isinstance(value,str) or not value or value not in expected:raise AutoQAPlanError('参照状態: 補助期待値が計算した表示と矛盾します')
            revised[i]['value']=value
        return dict(raw,checks=revised,exact_check=dict(op='text_equals',selector=exact['selector'],value=expected),reference_count=reference['reference_count'],oracle_basis=reference['oracle_basis']+' / '+answer['basis'])
    return ai_json(prompt,dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True),350,schema=schema,max_attempts=1,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate)


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
    composite=qa_reference_composite_oracle(raw,formats,spec,cfg,folder,key,prior)
    if composite is not None:return composite
    if contract.get('template')=='{n0}':
        reference=qa_reference_count_oracle(raw,contract,spec,cfg,folder,key,prior)
        if reference is not None:return reference
        # A numeric-only counter does not need a full-page prose oracle.
        # Retain prior inputs so an added record is not mistaken for a reset.
        numeric_schema={'type':'object','properties':{'value':{'type':'string','pattern':r'^-?\d+(?:\.\d+)?$','maxLength':30},'basis':{'type':'string','minLength':12,'maxLength':240}},'required':['value','basis'],'additionalProperties':False}
        numeric_prompt=('独立QA。数値だけを表示する対象要素の正解を、要件と操作から計算。JSON {value:数値文字列,basis:計算根拠}。'
            '先行操作の保存状態を保持する。追加・編集・削除を区別し、入力回数だけで件数を決めない。対象以外の集計や見出しは出力しない。'
            +'\n対象:'+exact['selector']+'\n要件:'+json.dumps(relevant,ensure_ascii=False)
            +'\n先行操作:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
            +'\n今回:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':')))
        def numeric_validate(answer):
            write_framework_json(folder/(key+'-numeric-oracle-last-response.json'),answer)
            if not isinstance(answer,dict) or not re.fullmatch(r'-?\d+(?:\.\d+)?',str(answer.get('value',''))) or not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:
                raise AutoQAPlanError('expected_values: 単一数値の独立した計算と根拠が必要です')
            return dict(raw,exact_check=dict(op='text_equals',selector=exact['selector'],value=answer['value']),oracle_basis=answer['basis'])
        return ai_json(numeric_prompt,dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True),180,schema=numeric_schema,max_attempts=1,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=numeric_validate)
    if re.match(r'^\s*\{n0\}\s*[%％]',contract.get('template','')) and (re.search(r'\{n\d+\}/\{n\d+\}',contract.get('template','')) or any(phrase in error for phrase in ('対象要素は割合から始まります','主結果は割合から始まります'))):
        # After a real-model format failure, request the independent numeric
        # answers and independent surrounding text separately. The observed
        # display supplies slot count only, never values or literal text.
        count=contract.get('slots')
        if type(count) is not int or not 1<=count<=8:return None
        ratio_layout=bool(re.search(r'\{n\d+\}/\{n\d+\}',contract.get('template','')))
        schema={'type':'object','properties':{'expected_values':{'type':'array','minItems':count,'maxItems':count,'items':{'type':'string','minLength':1,'maxLength':30}},'expected_suffixes':{'type':'array','minItems':count,'maxItems':count,'items':{'type':'string','maxLength':180}},'basis':{'type':'string','minLength':12,'maxLength':300}},'required':['expected_values','expected_suffixes','basis'],'additionalProperties':False}
        if ratio_layout:
            del schema['properties']['expected_suffixes'];schema['required'].remove('expected_suffixes')
            schema['properties']['expected_values'].update(minItems=count-1,maxItems=count-1)
        prompt=('独立QA。観測した数値・状態を正解に使わず、要件と入力から数値と文字列を計算。'
            '見出しや一覧は含めない。JSON {"expected_values":["数値"],"expected_suffixes":["各数値の直後の文字列"],"basis":"根拠"}。'
            '数値と後続文字列はそれぞれ'+str(count)+'個。先頭の数値の前にはプログラムが空文字を置く。先頭の後続文字列は%から始める。見出しは不要。'
            '\n要件:'+json.dumps(relevant,ensure_ascii=False)
            +'\n先行検査の入力と独立した期待値（実測値ではない。次の操作まで状態を保持し、根拠を要件から再計算）:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
            +'\n今回の操作:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':'))
            +'\n書式の参考（数値は未記載、正解ではない）:'+str(contract.get('template','')))
        def validate_parts(answer):
            if not isinstance(answer,dict) or not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('独立した計算根拠が不足しています')
            write_framework_json(folder/(key+'-oracle-last-response.json'),answer)
            # For a percentage with an explicit fraction, labels and separators
            # are presentation only. Independent QA still supplies every number.
            suffixes=(re.split(r'\{n\d+\}',contract['template'])[1:] if ratio_layout else answer.get('expected_suffixes'))
            if not isinstance(suffixes,list) or len(suffixes)!=count or not all(isinstance(x,str) for x in suffixes) or not re.match(r'^\s*[%％]',suffixes[0]):
                raise AutoQAPlanError('expected_values: 割合の各数値の後続文字列を指定し、最初は%から始めてください')
            values=answer.get('expected_values')
            if ratio_layout:
                if not isinstance(values,list) or len(values)!=count-1:raise AutoQAPlanError('expected_values: 割合以外の独立した集計値が必要です')
                fraction=re.search(r'\{n(?P<n>\d+)\}/\{n(?P<d>\d+)\}',contract['template'])
                try:
                    numerator=decimal.Decimal(values[int(fraction['n'])-1]);denominator=decimal.Decimal(values[int(fraction['d'])-1])
                    if not numerator.is_finite() or not denominator.is_finite() or numerator<0 or denominator<=0:raise ValueError()
                    percentage=numerator*100/denominator
                    if percentage!=percentage.to_integral_value():raise ValueError('丸め規則が必要')
                except (ValueError,IndexError,TypeError,decimal.InvalidOperation) as exc:
                    raise AutoQAPlanError('expected_values: 正の分母と非負の分子が必要です。非整数割合の丸め規則は別途検証してください') from exc
                values=[str(int(percentage))]+values
            candidate=dict(raw,exact_check=dict(selector=exact['selector'],expected_values=values,expected_literals=['']+suffixes))
            result=compile_qa_formatted_expectation(candidate,formats)
            if not re.match(r'^\s*-?\d+(?:\.\d+)?\s*[%％]',result['exact_check']['value']):raise AutoQAPlanError('expected_values: 主結果は割合から始まります。見出しを混ぜないでください')
            return dict(result,oracle_basis=answer['basis'])
        if ratio_layout:
            prompt=('独立QA。割合の算術はプログラムが行う。先頭の%値を回答せず、分数の分子・分母と残りの数値だけを表示順に'+str(count-1)+'個返す。'
                'JSON {expected_values:[数値文字列],basis:根拠}。操作前ではなく全操作後の状態を集計する。入力欄の数・操作番号を人数と解釈しない。保存されていない仮想記録を作らない。'
                '\n元仕様:'+json.dumps(dict(requested_outcome=spec.get('requested_outcome'),must_have=spec.get('must_have'),acceptance=relevant),ensure_ascii=False,separators=(',',':'))
                +'\n先行操作:'+json.dumps(prior,ensure_ascii=False,separators=(',',':'))
                +'\n今回の入力と操作:'+json.dumps(inputs,ensure_ascii=False,separators=(',',':'))
                +'\n数値を含まない表示の形式:'+contract['template'])
        oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
        answer=ai_json(prompt,oracle_cfg,450,schema=schema,max_attempts=2,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate_parts)
        return qa_audit_date_oracle(raw,spec,cfg,prior,answer)
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
        qa_validate_explicit_percentage(answer['expected_text'])
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
        if len(re.findall(r'-?\d+(?:\.\d+)?',answer['expected_text']))!=contract.get('slots'):
            raise AutoQAPlanError('expected_values: 主結果の数値項目が不足または過剰です。表示書式の全項目を仕様から計算してください')
        if not isinstance(answer.get('basis'),str) or len(answer['basis'].strip())<12:raise AutoQAPlanError('主結果の独立した計算根拠が不足しています')
        return dict(raw,oracle_basis=answer['basis'],exact_check=dict(op='text_equals',selector=exact['selector'],value=answer['expected_text']))
    oracle_cfg=dict(cfg,model=cfg.get('qa_oracle_model') or cfg['model'],_schema_in_prompt=False,_bounded_json_retry=True)
    repaired=ai_json(prompt,oracle_cfg,450,schema=schema,
        max_attempts=2,request_timeout=int(cfg.get('qa_oracle_timeout',cfg.get('qa_part_timeout',180))),validator=validate)
    repaired=qa_audit_date_oracle(raw,spec,cfg,prior,repaired)
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
    composite=qa_reference_composite_oracle(raw,formats or {},spec,cfg,folder,key,prior)
    if composite is not None:return composite
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
        contract=(formats or {}).get(exact.get('selector'),{})
        if contract:
            if re.search(r'\{n\d+\}',expected) or len(re.findall(r'-?\d+(?:\.\d+)?',expected))!=contract.get('slots'):
                raise AutoQAPlanError('expected_values: 矛盾修復でも全数値の独立した期待値が必要です')
            if contract.get('template','').startswith('{n0}') and not re.match(r'^\s*-?\d',expected):
                raise AutoQAPlanError('expected_values: 矛盾修復に対象外の見出しを含めないでください')
        qa_validate_explicit_percentage(expected)
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


def repair_qa_secondary_oracle(name,raw,fault,formats,spec,cfg,folder,key,error):
    """Repair one independent secondary assertion, preserving primary/actions."""
    checks=raw.get('checks',[])
    if fault not in checks or fault.get('op') not in ('text_equals','text_contains') or fault.get('selector') not in formats:return None
    isolated=dict(raw,exact_check=dict(fault))
    repaired=repair_qa_exact_oracle(name,isolated,formats,spec,cfg,folder,key,error)
    if repaired is None:return None
    exact=repaired['exact_check']
    if exact.get('selector')!=fault.get('selector'):raise AutoQAPlanError('補助期待値の修復で対象要素を変更できません')
    replacement=dict(fault,value=exact['value'])
    return dict(raw,checks=[replacement if c==fault else dict(c) for c in checks],secondary_oracle_basis=repaired.get('oracle_basis',''))


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


def qa_bound_step_schema(original,inventory,kind):
    """Bind native actions to observed control types and actual options."""
    choices=[];props=original['properties'];controls=inventory.get('controls',[])
    def branch(op,selectors,value=None):
        if not selectors:return
        fields=dict(op=dict(type='string',enum=[op]),selector=dict(type='string',enum=sorted(set(selectors))))
        required=['op','selector']
        if value is not None:fields['value']=value;required.append('value')
        if 'nth' in props:fields['nth']=props['nth']
        choices.append(dict(type='object',properties=fields,required=required,additionalProperties=False))
    for typ,pattern in ((None,None),('number',r'^-?\d+(?:\.\d+)?$'),('date',r'^\d{4}-\d{2}-\d{2}$'),('time',r'^\d{2}:\d{2}(?::\d{2})?$')):
        nodes=[n for n in controls if n.get('tag') in ('input','textarea') and n.get('type') not in ('file','checkbox','radio','button','submit','hidden') and (n.get('type')==typ if typ else n.get('type') not in ('number','date','time'))]
        value=dict(type='string',maxLength=300)
        if pattern:value['pattern']=pattern
        branch('fill',[n['selector'] for n in nodes],value)
    for node in controls:
        if node.get('tag')!='select':continue
        values=list(dict.fromkeys(o['value'] for o in node.get('options',[]) if o.get('value') is not None))
        value=dict(type='string',enum=values) if values else dict(type='string',minLength=1,maxLength=100)
        branch('select',[node['selector']],value)
    branch('check',[n['selector'] for n in controls if n.get('type') in ('checkbox','radio')],dict(type='boolean'))
    buttons=[n['selector'] for n in controls if n.get('tag')=='button' or n.get('type') in ('button','submit')]
    buttons += [n['selector'] for n in inventory.get('outputs',[]) if n.get('tag')=='a' or n.get('role')=='button']
    buttons += [n['selector']+' button' for n in inventory.get('outputs',[]) if n.get('tag') in ('tbody','table')]
    branch('click',buttons)
    passive=['wait']+(['reload','download_csv','download_json','restore_file','restore_invalid','cancel_restore'] if kind=='feature' else [])
    fallback=json.loads(json.dumps(original));fallback['properties']['op']['enum']=passive
    choices.append(fallback)
    return dict(anyOf=choices)


def qa_validate_step_choices(value,bound_schema):
    """Retain native grammar constraints even if the server uses JSON fallback."""
    def matches(step,branch):
        if not isinstance(step,dict) or any(k not in step for k in branch.get('required',[])):return False
        props=branch['properties']
        if branch.get('additionalProperties') is False and set(step)-set(props):return False
        for name,item in step.items():
            rule=props.get(name,{})
            if 'enum' in rule and item not in rule['enum']:return False
            types=rule.get('type',[]);types=[types] if isinstance(types,str) else types
            if types:
                checks=dict(string=isinstance(item,str),integer=type(item)is int,boolean=type(item)is bool,array=isinstance(item,list),object=isinstance(item,dict),null=item is None)
                if not any(checks.get(t,False) for t in types):return False
            if rule.get('pattern') and (not isinstance(item,str) or re.fullmatch(rule['pattern'],item) is None):return False
            if isinstance(item,str) and (len(item)<rule.get('minLength',0) or len(item)>rule.get('maxLength',10**9)):return False
            if type(item)is int and (item<rule.get('minimum',-10**30) or item>rule.get('maximum',10**30)):return False
        return True
    for index,step in enumerate(value.get('steps',[])):
        if not any(matches(step,branch) for branch in bound_schema['anyOf']):raise AutoQAPlanError('実画面の型・選択肢に対応付かない操作です: steps['+str(index)+'] '+json.dumps(step,ensure_ascii=False))
    return value


def qa_split_stage_context(fallback,cfg,inventory,key,actions=None):
    """Send only selected full criteria to an oracle, not every example."""
    spec=cfg.get('_qa_spec') or {}
    if not spec.get('acceptance'):return fallback
    criteria=spec['acceptance'];feature=key.startswith('feature-')
    if actions is not None:indexes=actions.get('acceptance',[])
    elif feature:indexes=[int(key.split('-')[1])]
    else:indexes=list(range(len(criteria)))
    titles=spec.get('acceptance_source_requirements',[])
    conditions={str(i):(titles[i] if actions is None and not feature and len(titles)==len(criteria) else criteria[i]) for i in indexes if type(i)is int and 0<=i<len(criteria)}
    used={step.get('selector') for step in (actions or {}).get('steps',[])}
    controls=[n for n in inventory.get('controls',[]) if not actions or n.get('selector') in used]
    outputs=[{k:n[k] for k in ('tag','selector','label') if k in n} for n in inventory.get('outputs',[]) if n.get('tag') not in ('main','section','header','form')]
    feature_context=cfg.get('_qa_feature_context')
    if feature and isinstance(feature_context,dict):
        index=feature_context.get('case_index',0);example=feature_context.get('design_example') or {};cases=example.get('test_cases',[])
        selected=cases[index] if type(index)is int and isinstance(cases,list) and 0<=index<len(cases) else {}
        feature_context=dict(condition_index=feature_context.get('condition_index'),case_index=index,
            design_case={k:selected[k] for k in ('input','action','expected') if isinstance(selected,dict) and k in selected},
            previous_inputs=[[{k:s[k] for k in ('op','selector','value','label') if k in s} for s in p.get('steps',[]) if s.get('op') in ('fill','select','check')] for p in feature_context.get('previous_cases',[])])
    view=dict(audience=spec.get('audience'),outcome=spec.get('requested_outcome'),conditions_by_index=conditions,
              controls=controls,outputs=outputs,prior=cfg.get('_qa_prior_scenarios',[]),kind=key,
              reference_clock=cfg.get('_qa_reference_clock',{}),feature_case=feature_context,
              display_contracts={k:v for k,v in (cfg.get('_qa_display_contracts') or {}).items() if not actions or k==actions.get('result_selector')})
    return json.dumps(view,ensure_ascii=False,separators=(',',':'))


def qa_validate_workflow_overwrites(value):
    pending=set()
    for step in value.get('steps',[]):
        if step.get('op')=='click':pending.clear()
        elif step.get('op') in ('fill','select'):
            selector=step.get('selector')
            if selector in pending:raise AutoQAPlanError('中心作業では保存前に同じ入力欄を繰り返し上書きしないでください。複数記録は各記録を保存してから次を入力してください: '+str(selector))
            pending.add(selector)
    return value


def qa_bound_primary_schema(original,selector,formats):
    """Make every numeric display slot explicit without using observed values."""
    exact=json.loads(json.dumps(original));exact['properties']['selector']=dict(type='string',enum=[selector])
    contract=formats.get(selector,{})
    count=contract.get('slots')
    if type(count)is int and 1<=count<=8:
        parts={}
        for index in range(count):
            parts['n'+str(index)]=dict(type='string',pattern=r'^-?\d+(?:\.\d+)?$')
        for index in range(count+1):
            rule=dict(type='string',maxLength=180,pattern=r'^[^0-9]*$')
            if index==0 and contract.get('template','').startswith('{n0}'):rule=dict(type='string',enum=[''])
            parts['l'+str(index)]=rule
        exact=dict(type='object',properties=dict(op=dict(type='string',enum=['text_equals']),selector=dict(type='string',enum=[selector]),
            display_parts=dict(type='object',properties=parts,required=list(parts),additionalProperties=False)),
            required=['op','selector','display_parts'],additionalProperties=False)
    return dict(type='object',properties=dict(exact_check=exact),required=['exact_check'],additionalProperties=False)


def qa_compile_bound_primary(value,selector,formats):
    exact=value.get('exact_check') if isinstance(value,dict) else None
    if not isinstance(exact,dict) or exact.get('op')!='text_equals' or exact.get('selector')!=selector:raise AutoQAPlanError('主結果は指定したCSSだけを照合してください')
    contract=formats.get(selector,{})
    if 'display_parts' in exact:
        count=contract.get('slots',0);parts=exact['display_parts']
        keys={'n'+str(i) for i in range(count)}|{'l'+str(i) for i in range(count+1)}
        if not isinstance(parts,dict) or set(parts)!=keys:raise AutoQAPlanError('display_partsには表示位置ごとの数値nと前後文字列lを過不足なく指定してください')
        exact=dict(exact,expected_values=[parts['n'+str(i)] for i in range(count)],expected_literals=[parts['l'+str(i)] for i in range(count+1)])
        exact.pop('display_parts')
        value=dict(value,exact_check=exact)

    if contract.get('template','').startswith('{n0}') and exact.get('expected_literals') and exact['expected_literals'][0]!='':
        raise AutoQAPlanError('数値から始まる結果要素に外側の見出しを追加できません')
    value=compile_qa_formatted_expectation(value,formats)
    exact=value.get('exact_check',{})
    if not isinstance(exact.get('value'),str) or not exact['value']:raise AutoQAPlanError('主結果全体の独立した期待値が必要です')
    if contract.get('template','').startswith('{n0}') and not re.match(r'^-?\d',exact['value']):raise AutoQAPlanError('対象外の見出しを数値表示の期待値へ追加できません')
    return qa_validate_display_boundary(value,formats)


def qa_reference_rows(steps,events):
    """Snapshot submitted inputs; never infer state from rendered text."""
    qa_evaluate_record_events(steps,events)
    events_by_index={e['step_index']:e for e in events};pending={};rows={}
    for index,step in enumerate(steps):
        if step.get('op') in ('fill','select','check'):
            pending[step['selector']]=step.get('value')
        event=events_by_index.get(index)
        if not event:continue
        effect=event['effect']
        if event.get('reset_inputs'):pending={}
        if effect=='create':rows[index]=dict(pending);pending={}
        elif effect=='update':rows[event['target']].update(pending);pending={}
        elif effect=='delete':rows.pop(event['target'])
    return list(rows.values())


def qa_evaluate_projection(rows,projection,reference_clock,_depth=0):
    """Small explicit aggregate language, with no eval or model arithmetic."""
    if _depth>3:raise AutoQAPlanError('参照集計: 計算式が深すぎます')
    metric=projection.get('metric');where=projection.get('where');field=projection.get('field');members=projection.get('members',[])
    if metric=='time_component':
        if projection.get('component')not in ('hours','minutes') or not isinstance(projection.get('source_rule'),dict):raise AutoQAPlanError('参照集計: 時間・分の対応が不正です')
        total=decimal.Decimal(qa_evaluate_projection(rows,projection['source_rule'],reference_clock,_depth+1))
        if total<0 or total!=total.to_integral_value():raise AutoQAPlanError('参照集計: 負数・端数分の時間表示規則は未確定です')
        return str(int(total)//60 if projection['component']=='hours' else int(total)%60)
    if metric in ('duration','difference'):
        D=decimal.Decimal
        if metric=='duration':
            inputs=reference_clock.get('input_values',{})
            def minute(css):
                value=inputs.get(css,'')
                if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise AutoQAPlanError('参照集計: 開始・終了の独立したHH:MM入力が必要です')
                hour,minutes=map(int,value.split(':'));return D(hour*60+minutes)
            start=minute(projection.get('start_input'));end=minute(projection.get('end_input'))
            pause=D(0)
            if projection.get('break_input'):
                value=inputs.get(projection['break_input'],'')
                if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d+)?',value):raise AutoQAPlanError('参照集計: 休憩の独立した分数入力が必要です')
                pause=D(value)
            if end<start or pause>end-start:raise AutoQAPlanError('参照集計: 日をまたぐ時間・休憩超過の扱いは仕様で未確定です')
            result=end-start-pause
        else:
            if not isinstance(projection.get('left'),dict) or not isinstance(projection.get('right'),dict):raise AutoQAPlanError('参照集計: 差分の両辺が必要です')
            result=D(qa_evaluate_projection(rows,projection['left'],reference_clock,_depth+1))-D(qa_evaluate_projection(rows,projection['right'],reference_clock,_depth+1))
        return qa_evaluate_projection([{'#derived':str(result)}],dict(metric='sum',where='all',field='#derived',rounding=projection.get('rounding','exact'),places=projection.get('places',0)),reference_clock,_depth+1)

    if metric not in ('count','percent','sum') or where not in ('all','in','before_date','on_reference_date','on_input_date'):raise AutoQAPlanError('参照集計: 未対応の計算は推測できません')
    if not isinstance(members,list) or any(not isinstance(v,str) for v in members):raise AutoQAPlanError('参照集計: 条件値が不正です')
    if where in ('before_date','on_reference_date','on_input_date'):
        try:
            reference_value=reference_clock['input_values'][projection['reference_input']] if where=='on_input_date' else reference_clock['date']
            qa_date.fromisoformat(reference_value)
        except (KeyError,TypeError,ValueError):raise AutoQAPlanError('参照集計: 独立した日付基準が必要です')
    selected=[]
    for row in rows:
        if where=='all':matched=True
        else:
            if field not in row:raise AutoQAPlanError('参照集計: 保存操作に集計項目がありません: '+str(field))
            if where=='in':matched=str(row[field]) in members
            else:
                try:
                    import datetime as projection_time
                    actual=projection_time.date.fromisoformat(str(row[field]))
                    if where in ('before_date','on_reference_date'):
                        reference=projection_time.date.fromisoformat(reference_clock['date']);matched=actual<reference if where=='before_date' else actual==reference
                    else:reference=projection_time.date.fromisoformat(reference_clock['input_values'][projection['reference_input']]);matched=actual==reference
                except (KeyError,TypeError,ValueError):raise AutoQAPlanError('参照集計: 正しい日付入力と独立した基準値が必要です')
        also=projection.get('also')
        if also:
            if not isinstance(also,dict) or set(also)!={'field','members'} or not isinstance(also['members'],list):raise AutoQAPlanError('参照集計: 追加の状態条件が不正です')
            if also['field'] not in row:raise AutoQAPlanError('参照集計: 追加条件の保存入力がありません')
            matched=matched and str(row[also['field']]) in also['members']
        if matched:selected.append(row)
    import decimal as projection_decimal
    D=projection_decimal.Decimal
    if metric=='count':result=D(len(selected))
    elif metric=='percent':
        if not rows:raise AutoQAPlanError('参照集計: 母数0の割合の仕様が未定義です')
        result=D(len(selected))*100/D(len(rows))
    else:
        value_field=projection.get('value_field',field)
        if any(value_field not in row or not re.fullmatch(r'-?\d+(?:\.\d+)?',str(row[value_field])) for row in selected):raise AutoQAPlanError('参照集計: 合計対象の独立した数値入力が必要です')
        result=sum((D(str(row[value_field])) for row in selected),D(0))
    rounding=projection.get('rounding','exact');places=projection.get('places',0)
    if type(places)is not int or not 0<=places<=4:raise AutoQAPlanError('参照集計: 桁数が範囲外です')
    quant=D(1).scaleb(-places)
    if rounding=='exact':
        if result!=result.quantize(quant):raise AutoQAPlanError('参照集計: 非整数の丸め規則が仕様で未確定です')
    elif rounding=='nearest':result=result.quantize(quant,rounding=projection_decimal.ROUND_HALF_UP)
    else:raise AutoQAPlanError('参照集計: 未対応の丸め規則です')
    if not result.is_finite() or abs(result)>D('1e15'):raise AutoQAPlanError('参照集計: 計算範囲外です')
    return format(result,'f').rstrip('0').rstrip('.') if '.' in format(result,'f') else format(result,'f')


def qa_projection_candidates(controls,template,index,output=None,input_values=None,row_fields=None):
    import itertools as projection_itertools
    after=template.split('{n'+str(index)+'}',1)[-1]
    percent=after.startswith(('%','％'))
    metric='percent' if percent else 'count'
    def rule(where='all',field='',members=None,label='全保存記録'):
        return dict(metric=metric,where=where,field=field,members=members or [],rounding='exact',places=0,basis=label+('の割合（全保存記録を分母）' if percent else 'の件数'))
    candidates=[rule()]
    if not percent and re.fullmatch(r'登録数|総件数|全件数|総登録数',str((output or {}).get('label','')).strip()) and re.fullmatch(r'\{n0\}\s*(?:件)?',template):return candidates

    for node in sorted(controls,key=lambda n:n['selector']):
        field=node['selector'];label=node.get('label') or field
        if row_fields is not None and field not in row_fields:continue
        if node.get('type')=='date':
            candidates.append(rule('before_date',field,label=label+'が実行基準日より前の保存記録'))
            if re.search(r'今日|本日|当日',str((output or {}).get('label',''))+template):
                candidates.append(rule('on_reference_date',field,label=label+'が今日（独立した実行基準日）と同じ保存記録'))
        options=list(dict.fromkeys(o['value'] for o in node.get('options',[]) if o.get('value')))
        if 0<len(options)<=5:
            for length in range(1,len(options)+1):
                for members in projection_itertools.combinations(options,length):
                    # In a required, enabled native choice every valid new
                    # record has one of these values. Its complete-set filter
                    # duplicates 'all'; optional fields retain that distinction.
                    if length==len(options) and 'required' in node and node['required']is not False and 'disabled' not in node:continue
                    candidates.append(rule('in',field,list(members),label+'が'+('または'.join(members))+'の保存記録'))
        if not percent and node.get('type')=='number':candidates.append(dict(metric='sum',where='all',field=field,members=[],rounding='exact',places=0,basis=label+'の全保存記録の合計'))
    date_rules=[p for p in candidates if p['where']in ('before_date','on_reference_date')]
    state_rules=[p for p in candidates if p['where']=='in']
    for date_rule in date_rules:
        for state_rule in state_rules:
            candidates.append(dict(date_rule,also=dict(field=state_rule['field'],members=state_rule['members']),basis=date_rule['basis']+'、かつ'+state_rule['basis']))
    for node in controls:
        if node.get('type')!='date' or row_fields is not None and node['selector']not in row_fields:continue
        for reference in controls:
            css=reference['selector']
            if reference.get('type')=='date' and css!=node['selector'] and isinstance((input_values or {}).get(css),str):
                candidates.append(dict(rule('on_input_date',node['selector'],label=(node.get('label')or node['selector'])+'が入力済みの'+(reference.get('label')or css)+'と同じ日付の保存記録'),reference_input=css))


    if not percent:
        numbers=[n for n in controls if n.get('type')=='number' and (row_fields is None or n['selector']in row_fields)]
        scoped=[]
        for date_rule in [p for p in candidates if p['where']=='on_input_date']:
            for number in numbers:
                candidate=dict(date_rule,metric='sum',value_field=number['selector'],basis=(number.get('label')or number['selector'])+'の対象日合計')
                scoped.append(candidate)
        candidates.extend(scoped)
        times=[n for n in controls if n.get('type')=='time' and n['selector']in (input_values or {})]
        starts=[n for n in times if re.search(r'開始|start',n.get('label','')+' '+n['selector'],re.I)]
        ends=[n for n in times if re.search(r'終了|end',n.get('label','')+' '+n['selector'],re.I)]
        pauses=[n for n in controls if n.get('type')=='number' and n['selector']in (input_values or {}) and re.search(r'休憩|break',n.get('label','')+' '+n['selector'],re.I)]
        durations=[]
        if len(starts)==len(ends)==1:
            for pause in ([None]+pauses[:1]):
                candidate=dict(metric='duration',where='inputs',field='',members=[],start_input=starts[0]['selector'],end_input=ends[0]['selector'],break_input=pause['selector'] if pause else '',rounding='exact',places=0,basis='終了−開始'+('−休憩' if pause else '')+'の分数')
                durations.append(candidate)
        candidates.extend(durations)
        sums=scoped or [p for p in candidates if p['metric']=='sum' and p['where']=='all']
        def difference(left,right):return dict(metric='difference',where='inputs',field='',members=[],left=left,right=right,rounding='exact',places=0,basis=left['basis']+'−'+right['basis'])
        for duration in durations:
            for total in sums:candidates.append(difference(duration,total))
        for left in sums:
            for right in sums:
                if left!=right:candidates.append(difference(left,right))
    return candidates


def qa_factor_status_candidates(candidates,controls):
    """Choose a calculation family before classifying states, avoiding 2**N menus."""
    fields={n['selector'] for n in controls if 2<=len({o.get('value') for o in n.get('options',[]) if o.get('value') and not o.get('disabled')})<=5}
    result=[];seen=set()
    for item in candidates:
        p=dict(item)
        if p.get('where')=='in' and p.get('field') in fields:
            p.update(members=[],status_family=True,basis='状態ごとの対象判定を次工程で独立に行う')
        elif p.get('also',{}).get('field') in fields:
            p.update(also=dict(field=p['also']['field'],members=[]),status_family=True,basis='日付条件と状態ごとの対象判定を独立に行う')
        signature=json.dumps(p,sort_keys=True,ensure_ascii=False)
        if signature not in seen:result.append(p);seen.add(signature)
    return result


def qa_compact_projection_choices(candidates,controls):
    """Lossless short meanings keep finite semantic choices within CPU budgets."""
    labels={n['selector']:n.get('label')or n['selector'] for n in controls}
    def meaning(p):
        if p['metric']=='duration':return '分数('+labels.get(p['end_input'],p['end_input'])+'−'+labels.get(p['start_input'],p['start_input'])+('−'+labels.get(p['break_input'],p['break_input']) if p.get('break_input') else '')+')'
        if p['metric']=='difference':return '('+meaning(p['left'])+' − '+meaning(p['right'])+')'
        field=labels.get(p.get('value_field',p.get('field')),p.get('value_field',p.get('field','')))
        filter_field=labels.get(p.get('field'),p.get('field',''))
        where=p['where']
        if p.get('status_family'):
            if where=='in':return ('割合' if p['metric']=='percent' else '件数')+'('+filter_field+'の対象状態を次工程で全状態ごとに判定)'
            date_condition=filter_field+('<基準日' if where=='before_date' else '=今日(基準日)' if where=='on_reference_date' else '=入力['+labels.get(p.get('reference_input'),p.get('reference_input',''))+']')
            extra=p['also'];return ('割合' if p['metric']=='percent' else '件数')+'('+date_condition+' AND '+labels.get(extra['field'],extra['field'])+'の対象状態を次工程で判定)'
        condition=('全保存記録' if where=='all' else field+'∈{'+','.join(p.get('members',[]))+'}' if where=='in' else field+'<基準日' if where=='before_date' else field+'=今日(基準日)' if where=='on_reference_date' else filter_field+'=入力['+labels.get(p.get('reference_input'),p.get('reference_input',''))+']')
        if p.get('also'):
            extra=p['also'];condition+=' AND '+labels.get(extra['field'],extra['field'])+'∈{'+','.join(extra['members'])+'}'
        return ('件数' if p['metric']=='count' else '割合(分母=全保存記録)' if p['metric']=='percent' else field+'合計')+'('+condition+')'
    return [[i,meaning(p)] for i,p in enumerate(candidates)]


def qa_require_independent_agreement(proposed,independent,scope):
    if proposed!=independent:raise AutoQAPlanError('独立対応が不一致です（'+scope+'）。どちらも合格にせず、仕様と対応資料を再診断します: '+json.dumps(dict(proposed=proposed,independent=independent),ensure_ascii=False)[:900])
    return dict(valid=True,method='blind independent semantic binding agreement',scope=scope,independent=independent)


def qa_blind_record_event_audit(steps,events,source,selector,cfg,folder,key):
    component=qa_component_events(steps,cfg)
    if component is not None:
        if component!=events:raise AutoQAPlanError('操作計画が宣言した記録コンポーネント契約と一致しません')
        return dict(valid=True,method='declared versioned component transition contract, not AI inference',contract=cfg['qa_component_contract'])
    # The second mapper never sees the first mapper's event assignments.
    independent_cfg=dict(cfg,qa_mapping_model=cfg.get('qa_oracle_model') or cfg.get('qa_mapping_model') or cfg['model'],_qa_blind_binding=True)
    independent=qa_bind_record_clicks(steps,source,selector,independent_cfg,Path(folder),key+'-independent')
    return qa_require_independent_agreement(events,independent,'保存操作と既存対象の対応')


def qa_reference_requirements(spec,cfg):
    requirements=dict(outcome=spec.get('requested_outcome',''),must_have=list(spec.get('must_have',[])),workflow=list(spec.get('workflow',[])))
    addenda=cfg.get('qa_requirement_addenda',[])
    if not isinstance(addenda,list) or len(addenda)>8:raise AutoQAPlanError('実証要求の追加定義が不正です')
    if addenda:
        for entry in addenda:
            if not isinstance(entry,dict) or set(entry)!={'source','text'} or any(not isinstance(entry[k],str) or not 1<=len(entry[k])<=1000 for k in ('source','text')):raise AutoQAPlanError('追加定義には出典と要求本文が必要です')
            if entry['text'] not in requirements['must_have']:requirements['must_have'].append(entry['text'])
        requirements['source_addenda']=addenda
    return requirements


def qa_reference_primary_expectation(actions,formats,spec,cfg,inventory,folder,key,generate):
    """Bind requirements to a checked projection; compute instead of guessing."""
    selector=actions['result_selector'];contract=formats.get(selector,{})
    count=contract.get('slots');template=contract.get('template','')
    if type(count)is not int or not 1<=count<=8:raise AutoQAPlanError('参照集計: 数値表示の契約が必要です')
    # Original capability requirements set the rules. Repaired test examples
    # are not records and must never enter the reference data set.
    requirements=qa_reference_requirements(spec,cfg)
    source=json.dumps(requirements,ensure_ascii=False,separators=(',',':'))
    steps=[step for prior in cfg.get('_qa_prior_scenarios',[]) for step in prior.get('steps',[])]+actions['steps']
    binding_cfg=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    events=qa_bind_record_clicks(steps,source,selector,binding_cfg,Path(folder),key)
    audit_schema=dict(type='object',properties=dict(valid=dict(type='boolean'),reason=dict(type='string',minLength=12,maxLength=300)),required=['valid','reason'],additionalProperties=False)
    event_audit=qa_blind_record_event_audit(steps,events,source,selector,binding_cfg,folder,key)
    rows=qa_reference_rows(steps,events)
    controls=[{k:n[k] for k in ('selector','label','type','options','required','disabled','min','max') if k in n} for n in inventory.get('controls',[]) if n.get('tag') in ('input','select','textarea')]
    fields=['']+[n['selector'] for n in controls]
    input_values=dict(cfg.get('_qa_input_defaults',{}));input_values.update({step['selector']:str(step.get('value','')) for step in steps if step.get('op') in ('fill','select')})
    evaluation_context=dict(cfg.get('_qa_reference_clock',{}),input_values=input_values)
    row_fields=set.intersection(*(set(row) for row in rows)) if rows else set()
    previous=cfg.get('_qa_workflow_projection_proof') or {}
    reusable=(key=='base-variant' and previous.get('binding_identity')==qa_compilation_identity(cfg)
        and previous.get('requirements')==requirements and previous.get('display_contract')==contract
        and previous.get('expected',{}).get('selector')==selector
        and previous.get('affix_audit',{}).get('valid') is True
        and len(previous.get('projections',[]))==count
        and len(previous.get('projection_audits',[]))==count
        and all(a.get('valid') is True for a in previous['projection_audits'])
        and not any(p.get('where')=='in' or p.get('also') for p in previous.get('projections',[])))
    if reusable:
        # These are already independently audited semantics for this source,
        # specification and model policy, not a previous observed result.
        # Recompute every number from the new declared state, then execute
        # Chromium again. Do not ask models to rediscover 63 subsets.
        values=[qa_evaluate_projection(rows,p,evaluation_context) for p in previous['projections']]
        literals=re.split(r'\{n\d+\}',template)
        result=qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector=selector,expected_values=values,expected_literals=literals)),selector,formats)
        write_framework_json(Path(folder)/(key+'-aggregate-proof.json'),dict(previous,steps=steps,events=events,event_audit=event_audit,rows=rows,values=values,expected=result['exact_check'],reference_clock=evaluation_context,reused_binding_from='base-workflow; independently audited rule only, not observed values or browser acceptance'))
        return result
    values=[];projections=[];audits=[]
    hours_minutes=qa_duration_pair_format(contract)
    for index in range(count):
        if hours_minutes and index%2==1:
            projection=dict(metric='time_component',component='minutes',source_rule=projections[index-1]['source_rule'],basis='同じ独立した分数から60で割った余り')
            values.append(qa_evaluate_projection(rows,projection,evaluation_context));projections.append(projection);audits.append(dict(valid=True,method='minute remainder of the same independently bound duration',derived_from=index-1));continue
        if qa_ratio_display(template) and index in (1,2) and projections and projections[0]['metric']=='percent':
            projection=dict(projections[0],metric='count') if index==1 else dict(metric='count',where='all',field='',members=[],rounding='exact',places=0,basis='割合の全保存記録の分母')
            values.append(qa_evaluate_projection(rows,projection,evaluation_context));projections.append(projection);audits.append(dict(valid=True,method='algebraic fraction identity from independently agreed percentage',derived_from=0))
            continue
        candidates=qa_projection_candidates(controls,template,index,contract,input_values,row_fields)
        if cfg.get('qa_factored_status_bindings'):candidates=qa_factor_status_candidates(candidates,controls)
        if hours_minutes:candidates=[p for p in candidates if p['metric']in ('duration','difference','sum')]
        if selector=='#recordCount' and len(candidates)==1 and qa_component_events(steps,binding_cfg) is not None:
            projection=candidates[0]
            values.append(qa_evaluate_projection(rows,projection,evaluation_context));projections.append(projection);audits.append(dict(valid=True,method='declared component registration-total quantity, not AI inference'))
            continue
        schema=dict(type='object',properties=dict(choice=dict(type='integer',enum=[-1]+list(range(len(candidates))))),required=['choice'],additionalProperties=False)
        def validate(value):
            if isinstance(value,dict) and type(value.get('choice'))is int and 0<=value['choice']<len(candidates):return candidates[value['choice']]
            if isinstance(value,dict) and value in candidates:return value
            raise AutoQAPlanError('参照集計: 対象位置に対応する選択肢が未確定です。未対応の規則を推測して採用できません')
        marked=template.replace('{n'+str(index)+'}','【今回の対象数値】')
        output_descriptor=dict(selector=selector,label=contract.get('label',''),target_label=qa_quantity_scope(contract,index),before_target=template.split('{n'+str(index)+'}',1)[0],after_target=template.split('{n'+str(index)+'}',1)[1])
        input_conditions=[dict(selector=n['selector'],label=n.get('label',''),value=input_values[n['selector']],scope='saved record' if n['selector']in row_fields else 'explicit view setting') for n in controls if n['selector']in input_values]
        context=dict(requirements=requirements,controls=controls,input_values=input_values,input_conditions=input_conditions,output=output_descriptor,display_template=template,target_position=index+1,target_marked_display=marked,candidates=candidates)
        scoped_output={k:output_descriptor[k] for k in ('selector','target_label')}
        prompt=('対象の数値項目「'+scoped_output['target_label']+'」だけの意味に対応する計算規則を選択肢から選ぶ。他の項目は今回扱わない。計算結果は回答しない。該当なしは-1。JSON {"choice":選択肢番号}のみ。\n出力項目:'+json.dumps(scoped_output,ensure_ascii=False)+'\n元要件:'+source+'\n入力した条件（画面の項目名付き）:'+json.dumps(input_conditions,ensure_ascii=False,separators=(',',':'))+'\n選択肢（各配列は[番号,規則]）:'+json.dumps(qa_compact_projection_choices(candidates,controls),ensure_ascii=False,separators=(',',':')))
        projection=generate('primary-projection-'+str(index),prompt,schema,validate,context)
        blind_prompt=('別担当が独立して規則を選ぶ。先行する提案は示さない。対象は出力項目「'+scoped_output['target_label']+'」1個だけ。ほかの集計・表示形式の網羅性は判定しない。原文に対応する選択肢番号を選び、未確定は-1。JSON {"choice":番号}のみ。\n出力項目:'+json.dumps(scoped_output,ensure_ascii=False)+'\n元要件:'+source+'\n入力した条件（画面の項目名付き）:'+json.dumps(input_conditions,ensure_ascii=False,separators=(',',':'))+'\n選択肢（各配列は[番号,規則]）:'+json.dumps(qa_compact_projection_choices(candidates,controls),ensure_ascii=False,separators=(',',':')))
        independent=generate('primary-projection-blind-'+str(index),blind_prompt,schema,validate,context)
        if projection==independent:
            partition=qa_resolve_status_partition(projection,independent,requirements,output_descriptor,controls,generate,str(index))
            if partition is not None:projection,audit=partition
            else:audit=qa_require_independent_agreement(projection,independent,selector+'の数値位置'+str(index+1))
        else:projection,audit=qa_resolve_projection_binding(projection,independent,requirements,output_descriptor,rows,controls,evaluation_context,generate,str(index))
        if projection.get('status_family'):
            partition=qa_resolve_status_partition(projection,projection,requirements,output_descriptor,controls,generate,str(index)+'-family')
            if partition is None:raise AutoQAPlanError('状態の計算方式だけでは合格にできません。全状態の対象判定が未確定です')
            projection,state_audit=partition
            audit=dict(state_audit,family_selection_audit=audit)
        if hours_minutes and index%2==0:projection=dict(metric='time_component',component='hours',source_rule=projection,basis='独立した分数を60で割った整数時間')
        values.append(qa_evaluate_projection(rows,projection,evaluation_context));projections.append(projection);audits.append(audit)
    literals=re.split(r'\{n\d+\}',template)
    if len(literals)!=count+1:raise AutoQAPlanError('参照集計: 表示位置の形式が不正です')
    static_context=dict(requirements=requirements,template=template,projections=projections)
    static_prompt=('独立監査。表示の数値以外の文字列が固定のラベル・単位・句読点だけならvalid=true。稼働枠内/枠超過、成功/失敗等、入力や状態で変わる判定結果を含むなら必ずfalse。falseは不合格ではなく独立した状態判断が別に必要という意味。JSON {valid,reason}。\n'+json.dumps(static_context,ensure_ascii=False,separators=(',',':')))
    def static_validate(value):
        if not isinstance(value,dict) or type(value.get('valid'))is not bool or not isinstance(value.get('reason'),str) or len(value['reason'])<12:raise AutoQAPlanError('参照集計: 表示文言の分類が必要です')
        return value
    if qa_fixed_quantity_format(template,contract.get('label',''),projections):fixed=dict(valid=True,method='checked quantity-format grammar; no business verdict text adopted')
    else:fixed=generate('primary-affix-audit',static_prompt,audit_schema,static_validate,static_context)
    if not fixed['valid']:
        def reuse_numbers(name,prompt,part_schema,check,dependency):
            if name.startswith('primary-number-'):return check(dict(value=values[int(name.rsplit('-',1)[1])]))
            return generate(name,prompt,part_schema,check,dependency)
        result=qa_primary_component_expectation(selector,formats,json.dumps(dict(requirements=requirements,steps=steps,reference_rows=rows,reference_values=values),ensure_ascii=False),reuse_numbers)
    else:result=qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector=selector,expected_values=values,expected_literals=literals)),selector,formats)
    write_framework_json(Path(folder)/(key+'-aggregate-proof.json'),dict(requirements=requirements,binding_identity=qa_compilation_identity(cfg),display_contract=contract,steps=steps,events=events,event_audit=event_audit,rows=rows,projections=projections,projection_audits=audits,values=values,affix_audit=fixed,expected=result['exact_check'],reference_clock=evaluation_context,method='audited requirement projections; independent code arithmetic; browser acceptance still required'))
    return result


def qa_secondary_saved_literal(check,actions,inventory,cfg):
    """Bind submitted text to its saved collection, without inventing row layout."""
    if check.get('op') not in ('text_equals','text_contains'):return check
    css=check.get('selector');value=check.get('value')
    if not isinstance(value,str) or not 2<=len(value)<=250 or value!=value.strip():return check
    nodes={n['selector']:n for n in inventory.get('controls',[])+inventory.get('outputs',[])}
    target=nodes.get(css,{})
    draft=target.get('form')=='#recordForm' and target.get('tag') in ('input','textarea') and target.get('type','text') in ('text','textarea')
    if css!='#recordRows' and not draft:return check
    steps=[step for prior in cfg.get('_qa_prior_scenarios',[]) for step in prior.get('steps',[])]+actions.get('steps',[])
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    events=qa_component_events(steps,binding)
    if events is None:return check
    if draft:
        creates=[e['step_index'] for e in events if e.get('effect')=='create']
        if not creates or any(step.get('selector')==css and step.get('op')in ('fill','select','check') for step in steps[max(creates)+1:]):return check
    rows=qa_reference_rows(steps,events)
    fields=[n['selector'] for n in inventory.get('controls',[]) if n.get('form')=='#recordForm' and n.get('tag') in ('input','textarea') and n.get('type','text') in ('text','textarea')]
    if draft:fields=[css]
    if not any(row.get(field)==value for row in rows for field in fields):return check
    return dict(op='text_contains',selector='#recordRows',value=value)


def qa_secondary_reference_check(check,actions,formats,spec,cfg,inventory,folder,key,generate):
    """Numeric secondary assertions use the same source-only compiler as primary."""
    selector=check.get('selector');contract=formats.get(selector,{})
    if not cfg.get('qa_reference_aggregates') or check.get('op') not in ('text_equals','text_contains'):return check
    if not any(n.get('selector')==selector for n in inventory.get('outputs',[])):return check
    count=contract.get('slots')
    if type(count)is not int or not 1<=count<=8:return check
    isolated=dict(actions,result_selector=selector)
    result=qa_reference_primary_expectation(isolated,formats,spec,cfg,inventory,folder,key,generate)
    exact=result.get('exact_check',{})
    if exact.get('selector')!=selector or exact.get('op')!='text_equals':raise AutoQAPlanError('補助数値の独立計算で照合先が変化しました')
    return exact


def qa_primary_component_expectation(selector,formats,context,generate):
    """Predict one scalar per request; retain independent business-value checks."""
    contract=formats.get(selector,{})
    count=contract.get('slots')
    if type(count)is not int or not 1<=count<=8:raise AutoQAPlanError('主結果の数値書式を確定できません')
    values=[];literals=[]
    template=contract.get('template','')
    for index in range(count):
        schema=dict(type='object',properties=dict(value=dict(type='string',pattern=r'^-?\d+(?:\.\d+)?$')),required=['value'],additionalProperties=False)
        def validate(value):
            if not isinstance(value,dict) or set(value)!={'value'} or not isinstance(value['value'],str) or not re.fullmatch(r'-?\d+(?:\.\d+)?',value['value']):raise AutoQAPlanError('主結果の数値1個だけをvalueに指定してください。単位・分数・全文は不可です')
            return value
        prompt=('独立QA。確定した全操作後の表示位置 {n'+str(index)+'} の正しい数値1個だけを元仕様と入力から計算する。他の数値・単位・見出しは返さない。JSON {"value":"数値だけ"}。表示書式:'+template+'\n'+context)
        answer=generate('primary-number-'+str(index),prompt,schema,validate,dict(context=context,selector=selector,index=index))
        values.append(validate(answer)['value'])
    for index in range(count+1):
        # Empty leading text is a structural boundary, not a business outcome.
        if index==0 and template.startswith('{n0}'):
            literals.append('');continue
        schema=dict(type='object',properties=dict(value=dict(type='string',maxLength=180,pattern=r'^[^0-9]*$')),required=['value'],additionalProperties=False)
        def validate(value):
            if not isinstance(value,dict) or set(value)!={'value'} or not isinstance(value['value'],str) or len(value['value'])>180 or re.search(r'\d|\{n\d+\}',value['value']):raise AutoQAPlanError('数値の前後に表示する文字列1個だけをvalueに指定してください。数字や書式変数は不可です')
            return value
        location=('最初の数値の前' if index==0 else '最後の数値の後' if index==count else '{n'+str(index-1)+'}と{n'+str(index)+'}の間')
        prompt=('独立QA。確定操作後の主結果のうち '+location+' の文字列だけを元仕様から求める。数値・周囲の見出し・他の位置の文字列を含めない。業務状態の文言は書式を正解としてコピーせず、入力と仕様から判定する。JSON {"value":"対象位置の文字列だけ"}。表示書式:'+template+'\n独立計算済み数値:'+json.dumps(values,ensure_ascii=False)+'\n'+context)
        answer=generate('primary-literal-'+str(index),prompt,schema,validate,dict(context=context,selector=selector,index=index,values=values))
        literals.append(validate(answer)['value'])
    return qa_compile_bound_primary(dict(exact_check=dict(op='text_equals',selector=selector,expected_values=values,expected_literals=literals)),selector,formats)


def qa_prepare_native_submissions(value,inventory,kind,cfg):
    """Apply submission checks to feature units using the same create actor."""
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    known=qa_component_events(value.get('steps',[]),binding) is not None
    if not known and kind!='workflow':return value
    if known:
        value=qa_normalize_component_inputs(value)
        # Repeated passive cycles do not exercise another saved input. Reject
        # the plan before expensive oracle calls; never silently trim a test.
        passive=set()
        for step in value.get('steps',[]):
            if step.get('op') in ('fill','select','check') or step.get('selector')=='#saveRecord':passive.clear()
            elif step.get('op')=='click' and step.get('selector') in ('#downloadCsv','#downloadJson','#clearForm'):
                css=step['selector']
                if css in passive:raise AutoQAPlanError('入力変更・保存のない出力/クリアの反復です。必要な操作だけで検査を再設計してください: '+css)
                passive.add(css)
    if known and kind=='feature':
        # A feature starts from a fresh browser context. Record dates do not
        # change an independent date filter or capacity date outside the form.
        dates=[n for n in inventory.get('controls',[]) if n.get('tag')=='input' and n.get('type')=='date' and not n.get('disabled') and not n.get('readonly')]
        record_dates=[n for n in dates if n.get('form')=='#recordForm']
        view_dates=[n for n in dates if n.get('form')!='#recordForm']
        filled={step.get('selector') for step in value.get('steps',[]) if step.get('op')=='fill'}
        if len(record_dates)==len(view_dates)==1 and record_dates[0]['selector'] in filled and view_dates[0]['selector'] not in filled:
            raise AutoQAPlanError('記録の日付と集計の対象日は別の入力です。機能検査では対象日も明示してください: '+view_dates[0]['selector']+'。同じ日の集計を検査するなら記録の日付と揃え、別の日を検査するならその入力から正解を独立計算してください')
    feature=cfg.get('_qa_feature_context')or {};spec=cfg.get('_qa_spec')or {}
    index=feature.get('condition_index');criteria=spec.get('acceptance',[])
    condition=criteria[index] if type(index)is int and 0<=index<len(criteria) else ''
    draft_edit=kind=='feature' and bool(re.search(r'誤入力|修正|訂正|上書き|編集',str(condition)))
    if kind=='workflow' or kind=='feature' and not draft_edit:qa_validate_workflow_overwrites(value)
    if qa_missing_initial_required_inputs(value,inventory):
        repaired=repair_qa_missing_initial_inputs(value,inventory,cfg,spec)
        if repaired is not None:value=repaired
        missing=qa_missing_initial_required_inputs(value,inventory)
        if missing:raise AutoQAPlanError('必須入力の補修が未完了です。操作数の上限内で入力してから保存してください: '+str(missing))
    return repair_qa_repeated_form_inputs(value,inventory,cfg)


def qa_component_invalid_case(cfg,inventory,scenarios,count):
    """Compile native required-field and corrupt-file rejection operations."""
    if not scenarios:return None
    workflow=next((s for s in scenarios if s.get('kind')=='workflow'),None)
    if not workflow:return None
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    if qa_component_events(workflow.get('steps',[]),binding) is None:return None
    target=next((n for n in inventory.get('controls',[]) if n.get('form')=='#recordForm' and n.get('required') and n.get('tag')in ('input','textarea') and n.get('type','text')in ('text','date') and not n.get('readonly') and not n.get('disabled')),None)
    restore=next((s.get('selector') for s in reversed(scenarios[-1].get('steps',[])) if s.get('op')=='restore_file'),None)
    if target is None or not any(n.get('selector')==restore and n.get('type')=='file' for n in inventory.get('controls',[])):return None
    checks=[dict(c) for c in scenarios[-1].get('checks',[])]+[dict(op='invalid',selector=target['selector'])]
    if len(checks)>8:return None
    return compile_qa_invalid(dict(restore_selector=restore,invalid_steps=[dict(op='fill',selector=target['selector'],value=''),dict(op='click',selector='#saveRecord')],checks=checks,acceptance=[],rationale='必須欄を明示的に空にして送信し、不正ファイル復元も拒否されることと、直前の独立した保存状態が変わらないことを確認する'),count)


def qa_duration_variant_inputs(cfg,inventory,prior):
    """Perturb an independently bound input duration, never a live result.

    A new record cannot change an input-only capacity. Use the previous
    audited rule to choose the causal input, and re-run the independent oracle
    afterward. Unknown dependencies decline this compiler.
    """
    proof=cfg.get('_qa_workflow_projection_proof') or {}
    if proof.get('steps')!=prior.get('steps') or proof.get('expected',{}).get('selector')!=prior.get('result_selector'):return []
    rules=proof.get('projections',[])
    while rules and all(r.get('metric')=='time_component' for r in rules):rules=[r.get('source_rule',{}) for r in rules]
    if not rules or any(r.get('metric')!='duration' or r!=rules[0] for r in rules):return []
    rule=rules[0];nodes={n['selector']:n for n in inventory.get('controls',[])}
    values=proof.get('reference_clock',{}).get('input_values',{})
    fields=[rule.get(k) for k in ('start_input','end_input','break_input') if rule.get(k)]
    if any(css not in nodes or css not in values or nodes[css].get('form')=='#recordForm' for css in fields):return None
    buttons=cfg.get('qa_component_passive_buttons',[])
    if len(buttons)!=1 or nodes.get(buttons[0],{}).get('tag')!='button':return None
    changed=dict(values);css=rule.get('break_input')
    if css and nodes[css].get('type')=='number':
        try:
            old=decimal.Decimal(values[css]);new=old+15
            if new>decimal.Decimal(str(nodes[css].get('max',100000))) or new<decimal.Decimal(str(nodes[css].get('min',0))):return None
            changed[css]=str(new)
        except (decimal.InvalidOperation,ValueError,TypeError):return None
    else:return None
    try:
        before=qa_evaluate_projection([],rule,dict(input_values=values))
        after=qa_evaluate_projection([],rule,dict(input_values=changed))
        if before==after:return None
    except (ValueError,AutoQAPlanError):return None
    # Preserve explicit selectors such as the target date when saving the
    # independent window; do not reuse unrelated record form inputs.
    explicit=[s for s in prior['steps'] if s.get('op')=='fill' and s.get('selector')not in fields and nodes.get(s.get('selector'),{}).get('type')=='date' and nodes[s['selector']].get('form')!='#recordForm']
    return [dict(s) for s in explicit]+[dict(op='fill',selector=f,value=changed[f]) for f in fields]+[dict(op='click',selector=buttons[0])]


def qa_reload_view_steps(scenarios,inventory,cfg):
    """Reopen the same date after reload without rewriting saved business data."""
    workflow=next((s for s in scenarios if s.get('kind')=='workflow'),None)
    if not workflow:return [dict(op='reload')]
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    if qa_component_events(workflow.get('steps',[]),binding) is None:return [dict(op='reload')]
    views={n['selector'] for n in inventory.get('controls',[]) if n.get('tag')=='input' and n.get('type')=='date' and n.get('form')!='#recordForm' and not n.get('disabled') and not n.get('readonly')}
    values={s['selector']:s['value'] for prior in scenarios for s in prior.get('steps',[]) if s.get('op')=='fill' and s.get('selector') in views}
    return [dict(op='reload')]+[dict(op='fill',selector=css,value=value) for css,value in values.items()]


def qa_component_variant_actions(cfg,inventory):
    """Build different declared actor inputs before deriving any expectation."""
    prior=next((p for p in cfg.get('_qa_prior_scenarios',[]) if p.get('kind')=='workflow'),None)
    if not prior:return None
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    events=qa_component_events(prior.get('steps',[]),binding)
    if events is None:return None
    rows=qa_reference_rows(prior['steps'],events)
    if not rows:return None
    nodes={n['selector']:n for n in inventory.get('controls',[])}
    text_fields=[css for css,n in nodes.items() if n.get('form')=='#recordForm' and n.get('tag')=='input' and n.get('type','text')=='text' and not n.get('pattern')]
    changed=[css for css in text_fields if nodes[css].get('required')] or text_fields[:1]
    if not changed or any(not any(css in row for css in changed) for row in rows):return None
    used={str(value) for row in rows for value in row.values()};steps=[]
    search=nodes.get('#searchRecords',{})
    if search.get('type')=='search':steps.append(dict(op='fill',selector='#searchRecords',value=''))
    for row_index,row in enumerate(rows):
        different=False
        for css,value in row.items():
            node=nodes.get(css,{})
            if node.get('form')!='#recordForm':continue
            if css in changed and isinstance(value,str):
                original=value
                value=original+' '+cfg.get('_qa_variant_suffix','別入力B')+str(row_index+1)
                if value in used or len(value)>min(250,int(node.get('maxlength',250))):return None
                used.add(value);different=True
            options=[o.get('value') for o in node.get('options',[]) if o.get('value') and not o.get('disabled')]
            if node.get('tag')=='select':
                alternatives=[v for v in options if v!=value]
                value=alternatives[0] if alternatives else value
                steps.append(dict(op='select',selector=css,value=value))
            elif node.get('type')in ('checkbox','radio'):steps.append(dict(op='check',selector=css,value=value))
            else:steps.append(dict(op='fill',selector=css,value=value))
        if not different:return None
        steps.append(dict(op='click',selector='#saveRecord'))
    duration_steps=qa_duration_variant_inputs(cfg,inventory,prior)
    if duration_steps is None:return None
    steps+=duration_steps
    if len(steps)>24:return None
    return dict(steps=steps,result_selector=prior.get('result_selector'),acceptance=[],
                rationale='宣言した記録操作契約で、前の各入力と異なる記録と状態を追加する。期待値は後続で独立計算する')


def qa_component_saved_checks(actions,primary,inventory,cfg):
    """Check declared collection state, never draft values or guessed row layout.

    The full numeric primary and feature audits still run. Unrecognized actors
    decline this path; no generic record workflow is imposed on other apps.
    """
    steps=[step for prior in cfg.get('_qa_prior_scenarios',[]) for step in prior.get('steps',[])]+actions['steps']
    binding=dict(cfg,_qa_binding_controls=inventory.get('controls',[]),_qa_binding_outputs=inventory.get('outputs',[]))
    events=qa_component_events(steps,binding)
    if events is None:return None
    rows=qa_reference_rows(steps,events)
    if not rows:return None
    nodes={n['selector']:n for n in inventory.get('controls',[])}
    checks=[]
    if primary.get('selector')!='#recordCount':
        checks.append(dict(op='text_equals',selector='#recordCount',value=str(len(rows))))
    # Select distinct literal submitted text fields, not punctuation, ordering,
    # action labels, dates with unknown localization, or a now-cleared input.
    for row in reversed(rows):
        for css,value in row.items():
            node=nodes.get(css,{})
            if node.get('form')!='#recordForm' or node.get('tag')not in ('input','textarea') or node.get('type','text')not in ('text','textarea'):continue
            if not isinstance(value,str) or not 2<=len(value)<=250 or value!=value.strip():continue
            check=dict(op='text_contains',selector='#recordRows',value=value)
            if check not in checks:checks.append(check)
            if len(checks)==2:return checks
    return None


def qa_clear_primary_components(directory):
    directory=Path(directory)
    for path in directory.glob('primary-*.json'):
        if re.fullmatch(r'primary-(?:(?:number|literal|projection|projection-audit|projection-blind)-[0-9]+|projection-(?:resolution|membership)-[0-9]+-(?:forward|reverse)|projection-state-[0-9]+-[0-9]+-(?:include|exclude))\.json',path.name):path.unlink(missing_ok=True)


def qa_split_unit_generation(context,cfg,folder,key,input_sha,schema,validator,inventory,hint=''):
    """Cache action planning and each independent assertion separately."""
    import time as qa_stage_time
    directory=Path(folder)/(key+'-split');directory.mkdir(parents=True,exist_ok=True)
    properties=schema['properties']
    semantic=cfg.get('qa_action_model') or cfg.get('qa_mapping_model') or cfg['model']
    oracle=cfg.get('qa_oracle_model') or semantic
    kind='workflow' if key=='base-workflow' else 'variant' if key=='base-variant' else 'feature'
    def stage(name,prompt,stage_schema,model,tokens,check,dependency=None):
        digest=hashlib.sha256(json.dumps(dict(policy='split-unit-2',input_sha=input_sha,model=model,dependency=dependency,schema=stage_schema),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        path=directory/(name+'.json')
        if path.exists():
            try:
                receipt=json.loads(path.read_text(encoding='utf-8'))
                if receipt.get('input_sha')==digest:return check(receipt['value'])
                if name=='actions' and kind=='workflow':
                    request_path=directory/'actions-request.json'
                    request=json.loads(request_path.read_text(encoding='utf-8')) if request_path.exists() else {}
                    if request.get('model')==model and request.get('schema')==stage_schema:
                        resumed=check(receipt['value'])
                        write_framework_json(directory/'actions-resumed.json',dict(prior_input_sha=receipt.get('input_sha'),input_sha=digest,model=model,method='same source/spec checkpoint and exact native schema; actions revalidated, assertions not reused'))
                        write_framework_json(path,dict(receipt,input_sha=digest,value=resumed))
                        return resumed
            except (ValueError,TypeError,KeyError):pass
        def capture(value):
            write_framework_json(directory/(name+'-last-response.json'),value)
            return check(value)
        if name=='actions':(directory/'actions-resumed.json').unlink(missing_ok=True)
        started=qa_stage_time.monotonic()
        write_framework_json(directory/(name+'-request.json'),dict(prompt=prompt,prompt_chars=len(prompt),schema=stage_schema,model=model,tokens=tokens,timeout=int(cfg.get('qa_part_timeout',180))))
        try:
            answer=ai_json(prompt,dict(cfg,model=model,_schema_in_prompt=name.startswith('primary-'),_bounded_json_retry=True,
                _json_transport_evidence=str(directory/(name+'-transport.json'))),tokens,schema=stage_schema,max_attempts=1,
                request_timeout=int(cfg.get('qa_part_timeout',180)),validator=capture)
        except Exception as exc:
            write_framework_json(directory/(name+'-error.json'),dict(error=type(exc).__name__+': '+str(exc),model=model,tokens=tokens,seconds=round(qa_stage_time.monotonic()-started,2),prompt_chars=len(prompt)))
            raise
        write_framework_json(path,dict(input_sha=digest,value=answer,seconds=round(qa_stage_time.monotonic()-started,2),prompt_chars=len(prompt)))
        (directory/(name+'-error.json')).unlink(missing_ok=True)
        return answer
    action_props={k:json.loads(json.dumps(properties[k])) for k in ('steps','acceptance','rationale')}
    action_props['steps']['items']=qa_bound_step_schema(properties['steps']['items'],inventory,kind)
    context=qa_split_stage_context(context,cfg,inventory,key)
    action_props['result_selector']=properties.get('result_selector',dict(type='string',minLength=1,maxLength=180))
    target=properties.get('exact_check',{}).get('properties',{}).get('selector',{})
    output_selectors=[n['selector'] for n in inventory.get('outputs',[]) if n.get('tag') not in ('main','section','header','form','script','style','tbody','table','thead','tr')]
    # Prefer an actual numeric leaf over its container, which also contains
    # headings and can confuse quantity names with business-state text.
    available_formats=cfg.get('_qa_display_contracts') or {}
    parents=set();leaf_replacements={}
    for node in inventory.get('outputs',[]):
        child=available_formats.get(node['selector'],{})
        if not child:continue
        for parent in node.get('ancestor_selectors',[]):
            outer=available_formats.get(parent,{})
            if cfg.get('qa_reference_aggregates') and child.get('slots') and outer.get('slots'):
                parents.add(parent)
            if child.get('slots')==outer.get('slots') and child.get('template','') in outer.get('template','') and child.get('label')==outer.get('label'):
                parents.add(parent);leaf_replacements.setdefault(parent,set()).add(node['selector'])
    output_selectors=[css for css in output_selectors if css not in parents]
    if kind in ('workflow','variant') and cfg.get('qa_reference_aggregates'):
        numeric=[css for css in output_selectors if 1<=(cfg.get('_qa_display_contracts') or {}).get(css,{}).get('slots',0)<=8 and re.search(r'summary|total|count|capacity|balance',css,re.I)]
        if not numeric:raise AutoQAPlanError('主集計の数値表示契約が未確定です。初期画面の書式取得が必要です')
        output_selectors=numeric
    if target.get('enum'):
        permitted=[v for v in target['enum'] if v in output_selectors]
        if not permitted:raise AutoQAPlanError('主結果には一覧表以外の独立した結果要素が必要です')
        action_props['result_selector']=dict(type='string',enum=permitted)
    elif output_selectors:action_props['result_selector']=dict(type='string',enum=output_selectors)
    if kind=='feature':
        condition_index=int(key.split('-')[1])
        action_props['acceptance']=dict(type='array',items=dict(type='integer',enum=[condition_index]),minItems=1,maxItems=1)
    action_schema=dict(type='object',properties=action_props,required=list(action_props),additionalProperties=False)
    def validate_actions(value):
        if not isinstance(value,dict) or not isinstance(value.get('steps'),list) or not value['steps']:raise AutoQAPlanError('操作計画には入力と実行が必要です')
        covers=value.get('acceptance')
        maximum=properties['acceptance']['items']['maximum']
        if not isinstance(covers,list) or any(type(i)is not int or not 0<=i<=maximum for i in covers):raise AutoQAPlanError('操作計画の完成条件番号が不正です')
        if kind=='feature' and covers!=[int(key.split('-')[1])]:raise AutoQAPlanError('今回の完成条件だけを検査してください')
        if not isinstance(value.get('result_selector'),str) or not value['result_selector']:raise AutoQAPlanError('操作計画の主結果CSSが必要です')
        replacements=leaf_replacements.get(value['result_selector'],set())
        if len(replacements)==1:value=dict(value,result_selector=next(iter(replacements)))
        permitted=action_props['result_selector'].get('enum')
        if permitted and value['result_selector'] not in permitted:raise AutoQAPlanError('保存された操作計画の表示先は現在の表示契約に含まれていません')
        allowed=properties['steps']['items']['properties']['op']['enum'] if kind=='feature' else ('fill','select','check','click','wait')
        if any(not isinstance(step,dict) or step.get('op') not in allowed for step in value['steps']):raise AutoQAPlanError('操作計画には今回の検査に必要な実操作を指定してください')
        value=qa_normalize_duration_inputs(qa_normalize_select_inputs(value,inventory),inventory)
        qa_validate_step_choices(value,action_props['steps']['items'])
        value=qa_prepare_native_submissions(value,inventory,kind,cfg)
        qa_validate_step_choices(value,action_props['steps']['items'])
        for step in value['steps']:
            node=next((n for n in inventory.get('controls',[]) if n['selector']==step.get('selector')),None)
            if node and step.get('op')=='select' and node.get('options'):
                options=[o.get('value') for o in node['options']]
                if step.get('value') not in options:raise AutoQAPlanError('選択値は画面に実在するoptionのvalueから指定してください')
        if kind=='variant' and qa_variant_repeats_workflow(value,cfg.get('_qa_prior_scenarios',[])):
            raise AutoQAPlanError('variantはworkflowと同一操作です。入力値を変えた別の例で再設計してください')
        return validate_qa_inventory_actions(value,inventory,kind)
    variant=qa_component_variant_actions(cfg,inventory) if kind=='variant' else None
    if variant is not None:
        actions=validate_actions(variant)
        write_framework_json(directory/'actions-component-contract.json',dict(contract=cfg['qa_component_contract'],value=actions,method='different native actor inputs compiled before independent assertions; not app generation'))
    else:actions=stage('actions','独立した操作計画。今回は操作だけを返す。期待値やchecksは生成しない。入力例と保存・実行を最後まで指定し、主結果CSSと検査する完成条件番号を選ぶ。複数記録は1件ごとに保存する。feature_caseがある場合はその条件を操作し、ケース1はケース0とは異なる入力例にする。JSON {steps,result_selector,acceptance,rationale}。\n'+context+'\n前回の不備:'+hint,
        action_schema,semantic,700,validate_actions)
    action_context=json.dumps(actions,ensure_ascii=False,separators=(',',':'))
    oracle_context=qa_split_stage_context(context,cfg,inventory,key,actions)
    formats=cfg.get('_qa_display_contracts') or {}
    primary_schema=qa_bound_primary_schema(properties['exact_check'],actions['result_selector'],formats)
    def validate_primary(value):
        return qa_compile_bound_primary(value,actions['result_selector'],formats)
    primary_shape=('JSON {exact_check:{op:text_equals,selector:指定CSS,display_parts:{n0:最初の数値だけ,n1:次の数値だけ,l0:最初の数値の前の文字列,l1:数値の間の文字列,l2:最後の数値の後の文字列}}}。スキーマの全n/lキーを埋める。nには単位・%・分数を入れず数値だけ。lには数字を入れない。' if 'display_parts' in primary_schema['properties']['exact_check']['properties'] else 'JSON {exact_check:{op:text_equals,selector:指定CSS,value:単位や補足まで含む完全な正解}}。')
    component_context=oracle_context+'\n確定済み操作:'+action_context
    if type(formats.get(actions['result_selector'],{}).get('slots'))is int and 1<=formats[actions['result_selector']]['slots']<=8:
        def component(name,prompt,part_schema,check,dependency):
            return stage(name,prompt,part_schema,oracle,180 if 'audit' in name else 100 if 'projection' in name else 120,check,dependency)
        if cfg.get('qa_reference_aggregates'):
            primary=qa_reference_primary_expectation(actions,formats,cfg.get('_qa_spec',{}),cfg,inventory,folder,key,component)['exact_check']
        else:primary=qa_primary_component_expectation(actions['result_selector'],formats,component_context,component)['exact_check']
    else:
        primary=stage('primary','独立QA。今回は主結果の期待値1個だけ。操作は変更せず、全操作後の結果を元仕様から計算。対象要素全体の表示を返し、周囲の見出しを混ぜない。'+primary_shape+'数値や業務状態は元仕様と確定操作から独立に求め、表示書式を正解として採用しない。仕様中の入力例の人数ではなく、確定済み操作で実際に保存した記録を集計する。\n'+oracle_context+'\n確定済み操作:'+action_context,
            primary_schema,oracle,300,validate_primary,actions)['exact_check']
    component_checks=qa_component_saved_checks(actions,primary,inventory,cfg) if kind in ('workflow','variant') else None
    if component_checks is not None:
        write_framework_json(directory/'secondary-component-contract.json',dict(contract=cfg['qa_component_contract'],checks=component_checks,method='declared saved collection count and submitted text membership; not model/layout inference'))
        return validator(dict(actions,checks=component_checks,exact_check=primary))
    checks=[]
    check_schema=dict(type='object',properties={'check':properties['checks']['items']},required=['check'],additionalProperties=False)
    for index in range(2):
        excluded={primary['selector']}|{c['selector'] for c in checks}
        options=sorted({n['selector'] for n in inventory.get('controls',[])+inventory.get('outputs',[]) if n.get('tag') not in ('main','section','header','form','script','style')} - excluded)
        if not options:raise AutoQAPlanError('主結果と別の補助検査先が画面にありません')
        check_schema=json.loads(json.dumps(check_schema))
        check_schema['properties']['check']['properties']['selector']=dict(type='string',enum=options)
        def validate_check(value):
            check=value.get('check') if isinstance(value,dict) else None
            if not isinstance(check,dict) or check.get('op') not in ('text_equals','text_contains','value_equals','count','invalid','visible') or not isinstance(check.get('selector'),str):raise AutoQAPlanError('補助検査1個の具体的な照合が必要です')
            if check.get('selector') not in options or check==primary or check in checks:raise AutoQAPlanError('補助検査は主結果や前の検査と同一にしないでください')
            saved=qa_secondary_saved_literal(check,actions,inventory,cfg)
            if saved!=check:
                write_framework_json(directory/('secondary-'+str(index)+'-saved-binding.json'),dict(original=check,compiled=saved,method='submitted literal found in independently declared saved records; not cleared draft or guessed row layout'))
                if saved.get('selector') in excluded:raise AutoQAPlanError('保存先への対応づけが既存の検査先と重複します。別の独立した結果を検査してください')
                return dict(value,check=saved)
            return value
        dependency=dict(actions=actions,primary=primary,earlier=checks)
        value=stage('secondary-'+str(index),'独立QA。補助検査を1個だけ返す。主結果とは別の表示先で、入力内容または処理後の保存状態を具体的に照合する。画面にない通知文や見出しを創作しない。操作・主結果は変更しない。JSON {check:{op,selector,value}}。\n'+oracle_context+'\n確定済みの操作と検査:'+json.dumps(dependency,ensure_ascii=False,separators=(',',':')),
            check_schema,oracle,220,validate_check,dependency)
        def secondary_component(name,prompt,part_schema,check,dependency):
            return stage('secondary-'+str(index)+'-reference-'+name,prompt,part_schema,oracle,180 if 'audit' in name else 100 if 'projection' in name else 120,check,dependency)
        saved=qa_secondary_saved_literal(value['check'],actions,inventory,cfg)
        if saved!=value['check']:write_framework_json(directory/('secondary-'+str(index)+'-saved-binding.json'),dict(original=value['check'],compiled=saved,method='submitted literal found in independently declared saved records; not cleared draft or guessed row layout'))
        checked=qa_secondary_reference_check(saved,actions,formats,cfg.get('_qa_spec',{}),cfg,inventory,folder,key+'-secondary-'+str(index),secondary_component)
        checks.append(checked)
    raw=dict(actions,checks=checks,exact_check=primary)
    try:return validator(raw)
    except Exception:
        # Actions already passed structural validation. A combined oracle
        # error must not discard the completed action plan.
        for name in ('primary','secondary-0','secondary-1'):(directory/(name+'.json')).unlink(missing_ok=True)
        qa_clear_primary_components(directory)
        raise


def qa_invalidate_split_failure(folder,key,raw,observation):
    """Only invalidate the stage implicated by real browser evidence."""
    directory=Path(folder)/(key+'-split')
    if not directory.exists() or not isinstance(raw,dict):return
    fault=observation.get('check') or {}
    if observation.get('invalid_fields') or not fault:
        (directory/'actions.json').unlink(missing_ok=True);return
    if fault==raw.get('exact_check'):
        (directory/'primary.json').unlink(missing_ok=True);qa_clear_primary_components(directory);return
    for i,check in enumerate(raw.get('checks',[])):
        if check==fault:(directory/('secondary-'+str(i)+'.json')).unlink(missing_ok=True)


def qa_capture_view_input_defaults(page):
    """Independent starting parameters, excluding record inputs and credentials."""
    return page.evaluate("() => Object.fromEntries([...document.querySelectorAll('input[id]')].filter(e=>e.form?.id!=='recordForm'&&['date','time','number'].includes(e.type)).map(e=>['#'+e.id,e.value]))")


def qa_initial_display_context(name,source,directory):
    """Collect masked formats before planning, shared by every scenario.

    Only interface format and the independent browser clock are returned.
    Rendered numerical results never become expected values.
    """
    directory=Path(directory);path=directory/'initial-display-context.json'
    digest=hashlib.sha256(source.encode()).hexdigest()
    if path.exists():
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('survey_policy')=='numeric-leaves-4-time-components' and saved.get('source_sha')==digest and saved.get('reference_clock',{}).get('date')==qa_current_reference_clock(saved.get('reference_clock'))['date']:
                return saved
        except (ValueError,TypeError,KeyError):pass
    from playwright.sync_api import sync_playwright
    preview=ensure_product_preview(name,source,{})
    url=preview.get('local_url') or preview['url']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            context=browser.new_context(viewport=dict(width=1280,height=900),service_workers='block')
            context.route('**/*',lambda route:route.continue_() if route.request.url==url else route.abort())
            page=context.new_page();page.goto(url,wait_until='networkidle',timeout=15000)
            clock=page.evaluate("() => {const d=new Date();const p=n=>String(n).padStart(2,'0');return {date:d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate()),timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,source:'browser local clock'};}")
            input_defaults=qa_capture_view_input_defaults(page)
            result=dict(survey_policy='numeric-leaves-4-time-components',input_defaults=input_defaults,source_sha=digest,display_contracts=capture_qa_display_contracts(page),reference_clock=clock,
                        method='numeric-stripped interface survey; no acceptance verdict or observed numeric expectations')
            result=json.loads(json.dumps(result,sort_keys=True,ensure_ascii=False))
            write_framework_json(path,result);context.close()
            return result
        finally:browser.close()


def qa_compilation_identity(cfg):
    """Whole-unit receipts must not bypass a newly selected compiler/role."""
    return dict(policy='2026-10-30-survey-before-plan-10-saved-literals-and-currency',split=bool(cfg.get('qa_split_units')),
                reference_aggregates=bool(cfg.get('qa_reference_aggregates')),
                component=cfg.get('qa_component_contract'),passive_buttons=cfg.get('qa_component_passive_buttons',[]),
                backup_component=cfg.get('qa_backup_component_contract'),
                requirement_addenda_sha=hashlib.sha256(json.dumps(cfg.get('qa_requirement_addenda',[]),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
                factored_status_bindings=bool(cfg.get('qa_factored_status_bindings')),
                action_model=cfg.get('qa_action_model'),mapping_model=cfg.get('qa_mapping_model'),oracle_model=cfg.get('qa_oracle_model'))


def checkpointed_independent_qa_plan(name,page,cfg,spec,quotes):
    import time as qa_time
    inventory=compact_qa_inventory(page)
    full_inventory=inventory
    signature=hashlib.sha256(json.dumps(dict(policy=CHECKPOINT_QA_POLICY,name=name,spec=spec,
        source=hashlib.sha256(page.encode()).hexdigest(),model=cfg['model'],url=cfg['url']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder=OUT/'knowledge'/'qa-plan-parts'/signature;folder.mkdir(parents=True,exist_ok=True)
    initial_context=qa_initial_display_context(name,page,folder) if cfg.get('qa_split_units') and cfg.get('qa_reference_aggregates') and cfg.get('qa_probe_units') else {}
    cfg=dict(cfg,_qa_input_defaults=initial_context.get('input_defaults',{}))
    full_inventory=qa_merge_display_inventory(full_inventory,initial_context.get('display_contracts',{}));inventory=full_inventory
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
        formats=dict(initial_context.get('display_contracts',{}))
        labels={n['selector']:n['label'] for n in full_inventory['outputs'] if n.get('label')}
        formats={css:dict(contract,**({'label':labels[css]} if css in labels else {})) for css,contract in formats.items()}
        reference_clock=qa_current_reference_clock(initial_context.get('reference_clock'))
        observation=folder/(key+'-browser')/'browser-observation-failure.json'
        if observation.exists():
            try:
                observed=json.loads(observation.read_text(encoding='utf-8'))
                if observed.get('reference_clock'):reference_clock=qa_current_reference_clock(observed['reference_clock'])
                available=observed.get('display_contracts',{})
                labels={n['selector']:n['label'] for n in full_inventory['outputs'] if n.get('label')}
                available={css:dict(contract,**({'label':labels[css]} if css in labels else {})) for css,contract in available.items()}
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
        compilation=qa_compilation_identity(cfg)
        input_sha=hashlib.sha256(((prompt+unit_context if include_context else prompt)+json.dumps(compilation,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
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
        attempt_timeout=qa_retry_timeout(cfg,failure)
        attempt_cfg=dict(cfg,_qa_input_repair_directory=str(folder),model=retry_model,qa_mapping_model=cfg.get('qa_mapping_model') or cfg['model'],qa_oracle_model=retry_oracle,qa_part_timeout=attempt_timeout)
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
        # Do not endlessly patch the same bad plan. Replan only this failed
        # checkpoint after two identical failures; retain successful siblings.
        if type(failure.get('repeats'))is int and failure['repeats']>=2:
            previous='';cached=None
        started=qa_time.monotonic()
        trial=None;current_response=False
        unit_operations=('mutation_stepsは{op:fill/click/select/check/wait,selector:CSS,value:入力値}の配列。select要素にはselectを使用。checks/steps/kindは出力しない。' if key=='base-roundtrip' else ('invalid_stepsは{op:fill/select/click/wait,selector:CSS,value:入力値}の配列。steps/kindは出力しない。壊れたJSONの実選択は検査プログラムが追加する。' if key=='base-invalid' else operations))
        request=(prompt+('\n'+unit_operations+'\n'+unit_context if include_context else '')+'\nこの1件だけ返す。前回の不合格検査:'+previous+'\n前回の問題（実測値を正解へコピーせず、仕様から正解を再計算する）:'+qa_independent_failure_hint(error))
        try:
            def capture_and_validate(value):
                nonlocal current_response
                current_response=True
                write_framework_json(folder/(key+'-last-response.json'),value)
                value=qa_resolve_unique_date_selector(value,inventory)
                selected=qa_normalize_select_inputs(value,full_inventory)
                if selected!=value:write_framework_json(folder/(key+'-normalized-selects.json'),dict(original=value,normalized=selected,method='unique native option match; expected values unchanged'))
                value=selected
                if key!='base-invalid':
                    normalized=qa_normalize_duration_inputs(value,full_inventory)
                    if normalized!=value:write_framework_json(folder/(key+'-normalized-inputs.json'),dict(original=value,normalized=normalized,method='explicit minute-label duration conversion'))
                    value=normalized
                validated=validate(qa_validate_display_boundary(compile_qa_formatted_expectation(value,formats),formats))
                if key=='base-variant' and qa_variant_repeats_workflow(validated,scenarios):raise AutoQAPlanError('variantはworkflowと同一操作です。入力値を変えた別の例で再設計してください')
                qa_validate_declared_calculations(validated,spec,key.removeprefix('base-'))
                return validate_qa_inventory_actions(validated,full_inventory,key.removeprefix('base-'))
            split_mode=bool(cfg.get('qa_split_units') and (key in ('base-workflow','base-variant') or key.startswith('feature-')))
            repaired=None
            if split_mode:previous=''
            if cached is None and previous and cfg.get('qa_probe_units'):
                try:raw=json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8'))
                except (ValueError,OSError):raw=None
                if raw and '期待値が矛盾' in error and not (key=='base-variant' and qa_variant_repeats_workflow(raw,scenarios)):
                    repaired=repair_qa_conflicting_checks(raw,spec,dict(attempt_cfg,_qa_reference_clock=reference_clock),folder,key,scenarios,formats)
                # A concrete UI operation error needs operation repair, not a
                # new oracle. Only expectation/format failures take this path.
                if formatted and repaired is None and raw and not (key=='base-variant' and qa_variant_repeats_workflow(raw,scenarios)) and not qa_unsubmitted_forms(raw,inventory) and any(term in error for term in ('期待結果と不一致','expected_values','expected_literals')):
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
                        if repaired is None:
                            repaired=repair_qa_secondary_oracle(name,raw,fault,formats,spec,dict(attempt_cfg,_qa_reference_clock=reference_clock,_qa_prior_scenarios=scenarios if key=='base-variant' else []),folder,key,error)
                    else:
                        repaired=repair_qa_exact_oracle(name,raw,formats,spec,dict(attempt_cfg,_qa_reference_clock=reference_clock,_qa_prior_scenarios=scenarios if key=='base-variant' else []),folder,key,error)
            if repaired is None and cached is None and previous and key!='base-invalid' and any(t in error for t in ('数値入力欄','日付入力欄','Malformed value')):
                raw=json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8'))
                repaired=repair_qa_typed_inputs(raw,full_inventory,attempt_cfg,spec)
            if repaired is None and cached is None and previous and key=='base-workflow' and '検査計画の必須入力が不足' in error:
                raw=json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8'))
                repaired=repair_qa_missing_initial_inputs(raw,full_inventory,attempt_cfg,spec)
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
            elif cached is None and split_mode:
                value=qa_split_unit_generation(unit_context+'\n'+prompt,dict(attempt_cfg,_qa_spec=spec,_qa_display_contracts=formats,_qa_prior_scenarios=scenarios if key=='base-variant' else [],_qa_reference_clock=reference_clock,_qa_feature_context=(dict(condition_index=int(key.split('-')[1]),case_index=int(key.split('-')[2]),previous_cases=[c for c in feature_cases if c.get('acceptance_index')==int(key.split('-')[1])],design_example=feature_contracts.get(int(key.split('-')[1]),{})) if key.startswith('feature-') else None)),folder,key,input_sha,schema,capture_and_validate,full_inventory,qa_independent_failure_hint(error))
            else:
                value=cached if cached is not None else ai_json(request,dict(attempt_cfg,_schema_in_prompt=False,_bounded_json_retry=True,_json_transport_evidence=str(folder/(key+'-transport.json'))),tokens,schema=schema,max_attempts=1,
                    request_timeout=attempt_timeout,validator=capture_and_validate)
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
                    observation.unlink(missing_ok=True)
                    proof=execute_browser_qa(name,page,trial,probe,prefix_only=True)
                    if proof.get('partial_passed') is not True or proof.get('passed') is not False:raise AutoQAPlanError('部分操作の検査結果が不正です')
                    write_framework_json(probe/'partial-proof.json',proof)
                except Exception as exc:
                    path.unlink(missing_ok=True)
                    if split_mode and observation.exists():
                        try:qa_invalidate_split_failure(folder,key,json.loads((folder/(key+'-last-response.json')).read_text(encoding='utf-8')),json.loads(observation.read_text(encoding='utf-8')))
                        except (ValueError,OSError,TypeError):pass
                    raise AutoQAPlanError('実ブラウザ事前検査は未合格。実装と検査期待値を独立に再診断: '+str(exc)[:1500]) from exc
            write_framework_json(path,dict(input_sha=input_sha,compilation=compilation,value=value))
            write_framework_json(folder/(key+'-usage.json'),dict(prompt_chars=len(request),seconds=round(qa_time.monotonic()-started,2),model=retry_model,oracle_model=retry_oracle,timeout=attempt_timeout))
            error_path.unlink(missing_ok=True)
            return value
        except Exception as exc:
            detail=type(exc).__name__+': '+str(exc)[:1500]
            qa_save_failure_diagnosis(folder,key,page,spec,scenarios,trial,detail,dict(planner=retry_model,oracle=retry_oracle,timeout=attempt_timeout),current_response)
            previous_streak=failure.get('timeout_streak',1) if re.search(r'\b(?:TimeoutError|timed out)\b',str(failure.get('error','')),re.I) else 0
            if type(previous_streak)is not int:previous_streak=0
            timeout_streak=previous_streak+1 if re.search(r'\b(?:TimeoutError|timed out)\b',detail,re.I) else 0
            write_framework_json(error_path,dict(error=detail,seconds=round(qa_time.monotonic()-started,2),prompt_chars=len(request),model=retry_model,oracle_model=retry_oracle,timeout=attempt_timeout,timeout_streak=timeout_streak,**qa_failure_memory(failure,detail),checked=now()))
            if isinstance(exc,TimeoutError):raise TimeoutError('検査工程 '+key+' / '+detail) from exc
            if isinstance(exc,AutoQAPlanError):raise AutoQAPlanError('検査工程 '+key+' / '+detail) from exc
            if hasattr(exc,'add_note'):exc.add_note('検査工程 '+key)
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
        if kind=='variant':
            try:
                projection_proof=json.loads((folder/'base-workflow-aggregate-proof.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):projection_proof={}
            cfg=dict(cfg,_qa_workflow_projection_proof=projection_proof)
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
            same_state=dict(steps=qa_reload_view_steps(scenarios,full_inventory,cfg),checks=last['checks'],acceptance=binding['acceptance'],
                rationale='再読込後も直前に独立して指定した同じ結果を確認する')
            value=part('base-reload',prompt,lambda v:validate_qa_unit(v,'reload',count),tokens=0,
                schema=qa_unit_schema(count,'reload'),supplied=same_state)
        elif kind=='roundtrip':
            prompt=('共通検査のうちroundtripの1件。バックアップ検査の対象と変更例だけをJSONで指定。stepsやop:download_csvは返さない。'
                'csv_selector:CSV出力ボタンのCSS,csv_contains:直前までに保存した入力値2件以上,json_selector:JSON出力ボタンCSS,restore_selector:復元ファイル入力または選択ラベルのCSS,'
                'confirmation_mode:ブラウザconfirmならnative、画面内に確定とキャンセルがあればinline。inlineではcancel_selectorに画面のキャンセルボタンCSSが必須。'
                'mutation_steps:別の記録Cをfill/selectしてclick保存する操作2〜14件,confirmation_steps:ファイル選択後に画面内の確定ボタンがある場合だけclick（通常は空配列）,'
                'acceptance:実際に復元で確認する条件番号配列,rationale:根拠。checksは出力しない。直前の独立検査を復元後に実行する。'
                'ダウンロード→C保存→復元キャンセル→実復元の順序は検査プログラムが組み立てる。サンプル読込やフォーム消去だけを変更としない。'
                '\n出力オブジェクトの形:{"csv_selector":"CSS","csv_contains":["保存値A","保存値B"],"json_selector":"CSS","restore_selector":"CSS","mutation_steps":[{"op":"fill","selector":"CSS","value":"別の値C"},{"op":"click","selector":"保存ボタンCSS"}],"confirmation_mode":"native","cancel_selector":"","confirmation_steps":[],"acceptance":[0],"rationale":"根拠"}'
                '\n先行入力値:'+json.dumps([{x.get('selector'):x.get('value',x.get('label')) for x in row['steps'] if x.get('op') in ('fill','select')} for row in scenarios[:2]],ensure_ascii=False,separators=(',',':'))[:1600]
                )
            schema=qa_roundtrip_schema(count)
            del schema['properties']['checks'];schema['required'].remove('checks')
            def roundtrip_with_prior_checks(value):
                if not isinstance(value,dict):raise AutoQAPlanError('復元検査の指定が必要です')
                return compile_qa_roundtrip(dict(value,checks=scenarios[-1]['checks']),count)
            mutation=qa_component_variant_actions(dict(cfg,_qa_prior_scenarios=scenarios,
                _qa_workflow_projection_proof={},_qa_variant_suffix='復元変更C'),full_inventory)
            if mutation is not None and 2<=len(mutation['steps'])<=14:
                # Generate only the file/confirmation wiring. Native record
                # inputs are already typed; assertions remain the prior
                # independent oracle. The browser must prove mutation,
                # cancelled restore, and byte-for-byte state restoration.
                target_keys=('csv_selector','json_selector','restore_selector','confirmation_mode','cancel_selector','confirmation_steps')
                target_schema=dict(type='object',properties={k:schema['properties'][k] for k in target_keys},
                    required=['csv_selector','json_selector','restore_selector','confirmation_mode','confirmation_steps'],additionalProperties=False)
                target_controls=[n for n in full_inventory['controls'] if n.get('tag')=='button' or n.get('type')=='file']
                buttons=[n['selector'] for n in target_controls if n.get('tag')=='button'];files=[n['selector'] for n in target_controls if n.get('type')=='file']
                for field in ('csv_selector','json_selector'):target_schema['properties'][field]['enum']=buttons
                target_schema['properties']['restore_selector']['enum']=files
                target_schema['properties']['cancel_selector']['enum']=['']+buttons
                target_prompt=('バックアップの配線だけをJSONで返す。csv_selector:CSVボタン、json_selector:JSON保存ボタン、restore_selector:復元file入力。'
                    'confirmation_modeはブラウザconfirmならnative、画面内の確定/取消ならinline。inlineだけcancel_selectorとconfirmation_stepsの確定clickが必要。nativeのconfirmation_stepsは空配列。記録入力・期待値・checks・完成条件は生成しない。\n操作要素:'+json.dumps(target_controls,ensure_ascii=False,separators=(',',':')))
                def validate_targets(value):
                    return qa_validate_backup_targets(value,dict(controls=target_controls))
                declared=qa_declared_backup_targets(cfg,full_inventory)
                targets=part('roundtrip-targets',target_prompt,validate_targets,tokens=0 if declared else 250,include_context=False,schema=target_schema,supplied=declared)
                strings=list(dict.fromkeys(str(s['value']) for p in scenarios[:2] for s in p['steps'] if s.get('op') in ('fill','select') and s.get('value') and next((n.get('form') for n in full_inventory['controls'] if n['selector']==s.get('selector')),None)=='#recordForm'))
                if len(strings)<2:raise AutoQAPlanError('CSVで照合する保存済み入力が不足しています')
                supplied=dict(targets,csv_contains=strings[:4],mutation_steps=mutation['steps'],acceptance=[],rationale='宣言済み記録契約の別入力で保存状態を変更し、直前の独立期待値へ実ファイルで復元する')
                value=part('base-roundtrip',prompt,roundtrip_with_prior_checks,tokens=0,schema=schema,supplied=supplied)
            else:
                value=part('base-roundtrip',prompt,roundtrip_with_prior_checks,tokens=900,schema=schema)
        elif kind=='invalid':
            prompt=('共通検査のうちinvalidの1件。実画面の復元先と誤入力だけをJSONで返す。'
                '出力形式:{"restore_selector":"復元ファイル入力またはボタンCSS","invalid_steps":[{"op":"fill","selector":"必須入力CSS","value":""},{"op":"click","selector":"保存ボタンCSS"}],"checks":[{"op":"invalid","selector":"必須入力CSS"},{"op":"text_equals","selector":"集計CSS","value":"既存の正解"}],"acceptance":[0],"rationale":"根拠"}。'
                'requiredがない欄なら実際のエラーメッセージを検査し、入力の種類に合う不正値を使う。入力の検査後に既存保存値が変わらないことを確認。'
                '\n既存の保存値の期待結果:'+json.dumps(scenarios[-1]['checks'],ensure_ascii=False,separators=(',',':'))[:1600])
            native_invalid=qa_component_invalid_case(cfg,full_inventory,scenarios,count)
            if native_invalid is not None:
                write_framework_json(folder/'base-invalid-component-contract.json',dict(contract=cfg['qa_component_contract'],value=native_invalid,method='native required-field and corrupt-file protocol; prior independent saved-state assertions retained'))
                value=part('base-invalid',prompt,lambda v:validate_qa_unit(v,'invalid',count),tokens=0,schema=qa_unit_schema(count,'invalid'),supplied=native_invalid)
            else:value=part('base-invalid',prompt,lambda v:compile_qa_invalid(v,count),tokens=800,schema=qa_invalid_schema(count))
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

