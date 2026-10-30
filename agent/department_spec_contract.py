"""Repair demonstrably contaminated model acceptance criteria from original scope."""

import re

DEPARTMENT_SPEC_POLICY='2026-10-29-source-grounded-acceptance-3'


def department_duration_correction(condition):
    """Correct one same-day source equation in unit or H:MM duration form."""
    from decimal import Decimal
    if re.search(r'別の入力\s*[:：]',condition):return None
    inputs=re.split(r'/\s*操作\s*[:：]|期待結果\s*[:：]',condition,maxsplit=1)[0]
    starts=set(re.findall(r'開始(?:時間|時刻)?\s*[=＝:：]?\s*((?:[01]\d|2[0-3]):[0-5]\d)',condition))
    ends=set(re.findall(r'終了(?:時間|時刻)?\s*[=＝:：]?\s*((?:[01]\d|2[0-3]):[0-5]\d)',condition))
    pauses={Decimal(n)*(60 if unit=='時間' else 1) for n,unit in re.findall(r'休憩(?:時間)?\s*[=＝:：]?\s*(\d+(?:\.\d+)?)\s*(時間|分)',inputs)}
    pauses.update(Decimal(int(h)*60+int(m)) for h,m in re.findall(r'休憩(?:時間)?\s*[=＝:：]?\s*(\d{1,3}):([0-5]\d)(?![0-9])',inputs))
    pattern=r'(?:稼働可能時間|使える稼働時間)\s*[:：=＝]\s*(?:(?P<h>\d{1,3}):(?P<m>[0-5]\d)(?![0-9])|(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>時間|分)(?:\s*(?P<mins>\d+)分)?)'
    matches=list(re.finditer(pattern,condition))
    if len(starts)!=1 or len(ends)!=1 or len(pauses)!=1 or len(matches)!=1:return None
    def minute(t):h,m=map(int,t.split(':'));return Decimal(h*60+m)
    pause=next(iter(pauses));computed=minute(next(iter(ends)))-minute(next(iter(starts)))-pause
    if computed<0 or computed!=computed.to_integral_value():return None
    match=matches[0]
    if match['h'] is not None:declared=Decimal(int(match['h'])*60+int(match['m']))
    else:declared=Decimal(match['n'])*(60 if match['unit']=='時間' else 1)+Decimal(match['mins']or 0)
    if declared==computed:return None
    if match['h'] is not None:
        hours,mins=divmod(int(computed),60);replacement=str(hours).zfill(len(match['h']) if match['h'].startswith('0') else 1)+':'+str(mins).zfill(2);start=match.start('h')
    else:
        if match['mins'] is not None or match['unit']=='時間':
            hours,mins=divmod(int(computed),60);replacement=str(hours)+'時間'+str(mins).zfill(2)+'分'
        else:replacement=str(int(computed))+'分'
        start=match.start('n')
    return dict(before=condition,after=condition[:start]+replacement+condition[match.end():],start=next(iter(starts)),end=next(iter(ends)),break_minutes=str(pause),declared_minutes=str(declared),computed_minutes=str(int(computed)),method='same-day source input arithmetic; no observed output or model consensus')


def department_difference_issue(condition):
    from decimal import Decimal
    number=r'-?\d+(?:\.\d+)?';unit=r'(?:時間|分)'
    pattern=r'差分\s*[:：]\s*('+number+r')\s*('+unit+r')\s*[（(]\s*('+number+r')\s*('+unit+r')\s*[-−]\s*('+number+r')\s*('+unit+r')\s*[）)]'
    for match in re.finditer(pattern,condition):
        values=match.groups();minutes=[Decimal(values[i])*(60 if values[i+1]=='時間' else 1) for i in (0,2,4)]
        if minutes[0]!=minutes[1]-minutes[2]:return '差分の定義式と正解が矛盾しています: '+match.group()
    clock=r'-?\d{1,3}:[0-5]\d'
    for match in re.finditer(r'差分\s*[:：]\s*('+clock+r')\s*[（(]([^（）()]{1,220})[）)]',condition):
        expressions=list(re.finditer('('+clock+r')\s*[-−]\s*('+clock+r')(?:\s*=\s*('+clock+r'))?',match[2]))
        if len(expressions)!=1:continue
        def minutes(value):
            sign=-1 if value.startswith('-') else 1;h,m=map(int,value.lstrip('-').split(':'));return sign*(h*60+m)
        expression=expressions[0];computed=minutes(expression[1])-minutes(expression[2])
        if minutes(match[1])!=computed or expression[3] is not None and minutes(expression[3])!=computed:return '差分の定義式と正解が矛盾しています: '+match.group()
    return ''


def department_unrequested_file_contract(text,source):
    named=bool(re.search(r'ファイル名.{0,40}(?:YYYY|HH.?MM|\.csv)|(?:バックアップ名|復元名)\s*[=＝]|バックアップ一覧画面',str(text),re.I))
    return named and not re.search(r'ファイル名|命名|バックアップ名|復元名|バックアップ一覧',str(source))


def department_spec_contract_issue(spec,rationale):
    criteria=' / '.join(map(str,spec.get('acceptance',[])))
    if any(x in criteria for x in ('実装済みとは書かない','外部リンクやコピーに縮小しない')):
        return '生成指示の文章が製品の完成条件に混入しています'
    source=' '.join(str(rationale.get(k,'')) for k in ('mvp_scope','customer_pain','hypothesis','differentiation'))
    source+=' '+str(spec.get('requested_outcome',''))+' '+' '.join(map(str,spec.get('must_have',[])))
    if department_unrequested_file_contract(criteria,source):
        return '元の要件にないファイル命名規則・名前付きバックアップ画面が完成条件に混入しています'
    if '共同編集' in criteria and '共同編集' not in source:
        return '元の事業要件にない共同編集が完成条件に混入しています'
    generic=('入力画面が使いやすい','データの保存と共有が容易','検索機能が効果的')
    if any(x in criteria for x in generic):
        return '具体値・利用操作・正解がない抽象的な完成条件です'
    vague=[str(c) for c in spec.get('acceptance',[]) if re.search(r'完了し[、,て].*(?:表示される|ダウンロードされる|保存・復元される)$',str(c)) and not re.search(r'[0-9０-９=＝「」]',str(c))]
    if vague:return '具体入力と照合値がなく、機能名を完了・表示と言い換えた完成条件です'
    if any(department_duration_correction(str(c)) for c in spec.get('acceptance',[])):return '時間算術: 開始・終了・休憩と稼働可能時間の正解が矛盾しています'
    for c in spec.get('acceptance',[]):
        difference=department_difference_issue(str(c))
        if difference:return difference
    return ''


def department_spec_source_requirements(spec,rationale=None):
    # Preserve original acceptance coverage as well as must-have scope.
    original=spec.get('acceptance_original_criteria')
    if original is None:original=[] if spec.get('acceptance_contract_policy') else spec.get('acceptance',[])
    requirements=list(spec.get('acceptance_source_requirements') or spec.get('must_have') or [])
    source=' '.join(map(str,spec.get('must_have',[])))+' '+str(spec.get('requested_outcome',''))+' '+str(rationale or {})
    requirements=[r for r in requirements if not department_unrequested_file_contract(r,source)]
    for requirement in spec.get('must_have',[]):
        if requirement not in requirements:requirements.append(requirement)
    for requirement in original:
        if not isinstance(requirement,str):continue
        if any(x in requirement for x in ('実装済みとは書かない','外部リンクやコピーに縮小しない','入力画面が使いやすい','データの保存と共有が容易','検索機能が効果的')):continue
        if '共同編集' in requirement and '共同編集' not in source:continue
        if department_unrequested_file_contract(requirement,source):continue
        if isinstance(requirement,str) and requirement.strip() and requirement not in requirements:requirements.append(requirement)
    return requirements


def department_file_backup_protocol(requirement,spec,rationale,cfg):
    """Compile a declared backup lifecycle; AI chooses data, not extra screens."""
    if cfg.get('department_backup_protocol')!='browser-json-file-v1' or spec.get('delivery_mode')!='browser_local':return False
    if not re.fullmatch(r'バックアップ(?:と|・|/|／)復元(?:機能)?',str(requirement).strip()):return False
    scope=' '.join(map(str,spec.get('must_have',[])))+' '+str(rationale)
    return not re.search(r'バックアップ名|復元名|履歴|クラウド|遠隔|命名|ファイル名',scope)


def department_compile_backup_acceptance(value):
    if not isinstance(value,dict) or set(value)!={'saved_input','changed_input'}:raise AutoQAPlanError('バックアップ用の保存前後の具体入力が必要です')
    for k in ('saved_input','changed_input'):
        if not isinstance(value[k],str) or not 8<=len(value[k])<=120 or not re.search(r'[=＝]',value[k]):raise AutoQAPlanError('状態ごとの項目名=具体値を指定してください')
        if re.search(r'バックアップ名|復元名|ファイル名|バックアップ日時|保存パス|一覧画面',value[k]):raise AutoQAPlanError('データ例に要件外のバックアップ管理機能を混ぜないでください')
    if value['saved_input']==value['changed_input']:raise AutoQAPlanError('復元前の変更状態は保存時と異なる具体値が必要です')
    a=value['saved_input'];b=value['changed_input']
    return dict(input='保存するデータA: '+a+'。変更後のデータB: '+b,
        action='Aを入力して保存し、実際のJSONバックアップファイルを取得する。次にBへ変更して保存する。復元をキャンセルしてBを維持することを確認する。取得した同じファイルを選んで復元を確定し、再読込する。',
        expected='復元キャンセル後はB（'+b+'）のまま。復元確定・再読込後はA（'+a+'）と一致し、Bの変更は残らない。')


def ensure_department_product_spec(name,cfg):
    spec=ensure_product_spec(name,cfg)
    rationale=idea_details(name)
    issue=department_spec_contract_issue(spec,rationale)
    if not issue and spec.get('acceptance_repair_reason') and spec.get('acceptance_contract_policy')!=DEPARTMENT_SPEC_POLICY:
        issue='旧修復条件の計算・操作範囲は独立監査されていません'
    if not issue:return spec
    rows=query('SELECT source FROM venture_product_specs WHERE idea=?',(name,))
    if rows and str(rows[0]['source']).startswith('ユーザー'):
        raise AutoQAPlanError('ユーザー指定の完成条件に確認が必要です: '+issue)
    if issue.startswith('時間算術:'):
        corrected=[];proof=[]
        for index,condition in enumerate(spec.get('acceptance',[])):
            fix=department_duration_correction(str(condition));corrected.append(fix['after'] if fix else condition)
            if fix:proof.append(dict(fix,acceptance_index=index))
        saved=store_product_spec(name,dict(spec,acceptance=corrected,arithmetic_contract_corrections=list(spec.get('arithmetic_contract_corrections',[]))+proof),source='AI設計・元の時刻と休憩の算術だけを訂正')
        remaining=department_spec_contract_issue(saved,rationale)
        if remaining:raise AutoQAPlanError('時刻算術は訂正済み。残る仕様の不一致を企画担当で修復してください: '+remaining)
        return saved
    signature=hashlib.sha256(json.dumps(dict(policy=DEPARTMENT_SPEC_POLICY,issue=issue,spec=spec,
        rationale=rationale,model=cfg['model']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder=OUT/'knowledge'/'spec-contracts'/signature;folder.mkdir(parents=True,exist_ok=True)
    requirements=department_spec_source_requirements(spec,rationale)
    conditions=[]
    for index,requirement in enumerate(requirements):
        path=folder/(str(index)+'.json')
        def validate(value):
            write_framework_json(folder/(str(index)+'-last-response.json'),value)
            if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not 8<=len(value[k].strip())<=400 for k in ('input','action','expected')):
                missing=[k for k in ('input','action','expected') if not isinstance(value,dict) or not isinstance(value.get(k),str) or not 8<=len(value[k].strip())<=400]
                raise AutoQAPlanError('完成条件に具体的な入力・操作・正解が必要です。不足: '+','.join(missing))
            if any(term in value['expected'] for term in ('使いやすい','期待通り','正しく動作','効果的','実装予定','要検証')):
                raise AutoQAPlanError('抽象評価ではなく照合する具体値・保存状態を指定してください')
            original=str(requirement)
            if '共同編集' in ' '.join(value.values()) and '共同編集' not in original and '共同編集' not in str(rationale):
                raise AutoQAPlanError('指定されていない共同編集を追加しないでください')
            if department_unrequested_file_contract(' '.join(value.values()),original+' '+str(rationale)):
                raise AutoQAPlanError('元要件にないファイル名・名前付きバックアップ画面を完成条件へ追加しないでください')
            if department_duration_correction('入力: '+value['input']+' / 操作: '+value['action']+' / 期待結果: '+value['expected']):raise AutoQAPlanError('開始・終了・休憩と稼働可能時間の計算が矛盾しています')
            difference=department_difference_issue(value['expected'])
            if difference:raise AutoQAPlanError(difference)
            return value
        value=None
        if path.exists():
            try:value=validate(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError,TypeError,KeyError):pass
        if value is None:
            error_path=folder/(str(index)+'-error.json');error=''
            if error_path.exists():
                try:error=json.loads(error_path.read_text(encoding='utf-8')).get('error','')
                except (ValueError,OSError):pass
            previous=''
            previous_path=folder/(str(index)+'-last-response.json')
            if previous_path.exists():
                try:previous=json.dumps(json.loads(previous_path.read_text(encoding='utf-8')),ensure_ascii=False)[:1800]
                except (ValueError,OSError):pass
            if department_unrequested_file_contract(previous,str(requirement)+' '+str(rationale)):
                previous='要件外のファイル命名・バックアップ管理画面を含んだ候補は破棄。元要件だけから再構成する。'
            prompt=('製品要件担当。壊れた完成条件を元の事業範囲から修復します。今回の必須機能1件だけについて、'
                'JSON {input:具体的な入力例,action:最後までの操作,expected:画面や保存値で照合できる正解}を返す。各項目8〜400字で、必要な操作を末尾で切らず、単位・計算式と照合値を具体的に書く。'
                '入力は名前=値+単位で列挙し、時刻HH:MMと期間（整数分等）を混同しない。期待値には式と結果を併記し、入力値と操作で違う値を使わない。'
                '画面の見やすさ等は別の画像審査で評価する。一般論や機能名の言い換えは不可。依頼されていない検索・共同編集・AI機能を追加しない。'
                '元の要件がAPI機能を含む場合だけ、サンプル操作と外部接続後の検証を分け、実取得したと偽らない。'
                '\n対象者:'+str(spec.get('audience',''))+'\n達成する目的:'+str(spec.get('requested_outcome',''))
                +'\n今回の必須機能:'+str(requirement)+'\n元の事業範囲:'+str(rationale.get('mvp_scope') or rationale.get('hypothesis') or '')[:2000]+'\n修正すべき前回の候補:'+previous+'\n前回の不備（この箇所を具体的に修復）:'+error[:1200])
            schema={'type':'object','properties':{k:{'type':'string','minLength':8,'maxLength':400} for k in ('input','action','expected')},'required':['input','action','expected'],'additionalProperties':False}
            try:
                if department_file_backup_protocol(requirement,spec,rationale,cfg):
                    data_schema=dict(type='object',properties={k:dict(type='string',minLength=8,maxLength=120) for k in ('saved_input','changed_input')},required=['saved_input','changed_input'],additionalProperties=False)
                    data_prompt=('バックアップ試験のデータだけをJSON {saved_input:保存時の項目名=具体値,changed_input:変更後の同じ項目名=異なる具体値}で返す。バックアップ管理画面・操作・バックアップ名・バックアップ作成日時・ファイル名は生成しない。各8〜120字。通常記録の必須日付等はデータ例へ含める。\n目的:'+str(spec.get('requested_outcome',''))+'\n元の必須入力:'+json.dumps(spec.get('must_have',[]),ensure_ascii=False))
                    def compile_data(answer):
                        write_framework_json(folder/(str(index)+'-backup-data-last-response.json'),answer)
                        compiled=validate(department_compile_backup_acceptance(answer))
                        write_framework_json(folder/(str(index)+'-backup-protocol.json'),dict(protocol=cfg['department_backup_protocol'],data=answer,compiled=compiled,method='declared file lifecycle; independent source audit still required'))
                        return compiled
                    value=ai_json(data_prompt,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True,_json_transport_evidence=str(folder/(str(index)+'-backup-data-transport.json'))),360,schema=data_schema,max_attempts=1,request_timeout=int(cfg.get('spec_contract_timeout',300)),validator=compile_data)
                else:value=ai_json(prompt,dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),800,schema=schema,max_attempts=1,request_timeout=int(cfg.get('spec_contract_timeout',300)),validator=validate)
            except Exception as exc:
                write_framework_json(error_path,dict(error=type(exc).__name__+': '+str(exc)[:1500],checked=now()))
                raise
            write_framework_json(path,value)
            error_path.unlink(missing_ok=True)
        # A valid JSON shape does not prove a correct oracle. Audit the
        # source requirement, units, arithmetic and coverage independently.
        audit_path=folder/(str(index)+'-audit.json')
        audit_sha=hashlib.sha256(json.dumps(dict(requirement=requirement,value=value),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        audit=None
        if audit_path.exists():
            try:
                saved=json.loads(audit_path.read_text(encoding='utf-8'))
                if saved.get('input_sha')==audit_sha and saved.get('valid') is True:audit=saved
            except (ValueError,TypeError):pass
        if audit is None:
            def validate_audit(result):
                write_framework_json(folder/(str(index)+'-audit-last-response.json'),result)
                if not isinstance(result,dict) or result.get('valid') is not True:
                    reasons=str(result.get('issues') if isinstance(result,dict) else result)[:1200]
                    if isinstance(result,dict) and result.get('valid') is False:
                        path.unlink(missing_ok=True)
                        write_framework_json(folder/(str(index)+'-error.json'),dict(error='独立監査: '+reasons,checked=now()))
                    raise AutoQAPlanError('完成条件の独立監査: '+reasons)
                return result
            audit_schema={'type':'object','properties':{'valid':{'type':'boolean'},'issues':{'type':'array','maxItems':4,'items':{'type':'string','maxLength':200}}},'required':['valid','issues'],'additionalProperties':False}
            audit=ai_json('完成条件の独立監査。元要件にない制約を追加しない（予定と実績が異なること自体は不具合ではない）。主検証は今回の必須機能を扱うこと。保存確認の再読込や製品の必須入力など必要な前提操作を、元要件外の新機能と混同しない。別機能だけの検証へ置換は不合格とする。元の必須機能の各操作を条件が全て扱うか、入力の単位と型は一貫するか、計算結果を独立に再計算して正しいか、文章が途中で切れず具体値で検査できるかを確認。機能の削除・別機能への置換・曖昧な正解を合格にしない。JSON {valid:true/false,issues:[具体的な不備]}。'
                +'\n元の必須機能:'+str(requirement)+'\n承認された製品全体の範囲:'+json.dumps(dict(must_have=spec.get('must_have',[]),mvp_scope=rationale.get('mvp_scope','')),ensure_ascii=False)+'\n製品の目的:'+str(spec.get('requested_outcome',''))+'\n候補:'+json.dumps(value,ensure_ascii=False),
                dict(cfg,_schema_in_prompt=False,_bounded_json_retry=True),450,schema=audit_schema,max_attempts=1,request_timeout=int(cfg.get('spec_contract_timeout',300)),validator=validate_audit)
            write_framework_json(audit_path,dict(audit,input_sha=audit_sha))
        conditions.append('入力: '+value['input']+' / 操作: '+value['action']+' / 期待結果: '+value['expected'])
    if len(conditions)<3:raise AutoQAPlanError('元の必須機能が3件未満のため完成条件を再設計する必要があります')
    repaired=dict(spec,acceptance=conditions,acceptance_contract_policy=DEPARTMENT_SPEC_POLICY,
                  acceptance_repair_reason=issue,acceptance_source_requirements=list(requirements),
                  acceptance_original_criteria=spec.get('acceptance_original_criteria') or ([] if spec.get('acceptance_contract_policy') else list(spec.get('acceptance',[]))))
    return store_product_spec(name,repaired,source='AI設計・元要件から完成条件を修復')
