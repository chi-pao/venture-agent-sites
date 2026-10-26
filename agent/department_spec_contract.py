"""Repair demonstrably contaminated model acceptance criteria from original scope."""

DEPARTMENT_SPEC_POLICY='2026-10-26-source-grounded-acceptance-1'


def department_spec_contract_issue(spec,rationale):
    criteria=' / '.join(map(str,spec.get('acceptance',[])))
    if any(x in criteria for x in ('実装済みとは書かない','外部リンクやコピーに縮小しない')):
        return '生成指示の文章が製品の完成条件に混入しています'
    source=' '.join(str(rationale.get(k,'')) for k in ('mvp_scope','customer_pain','hypothesis','differentiation'))
    source+=' '+str(spec.get('requested_outcome',''))+' '+' '.join(map(str,spec.get('must_have',[])))
    if '共同編集' in criteria and '共同編集' not in source:
        return '元の事業要件にない共同編集が完成条件に混入しています'
    generic=('入力画面が使いやすい','データの保存と共有が容易','検索機能が効果的')
    if any(x in criteria for x in generic):
        return '具体値・利用操作・正解がない抽象的な完成条件です'
    return ''


def ensure_department_product_spec(name,cfg):
    spec=ensure_product_spec(name,cfg)
    rationale=idea_details(name)
    issue=department_spec_contract_issue(spec,rationale)
    if not issue:return spec
    rows=query('SELECT source FROM venture_product_specs WHERE idea=?',(name,))
    if rows and str(rows[0]['source']).startswith('ユーザー'):
        raise AutoQAPlanError('ユーザー指定の完成条件に確認が必要です: '+issue)
    signature=hashlib.sha256(json.dumps(dict(policy=DEPARTMENT_SPEC_POLICY,spec=spec,
        rationale=rationale,model=cfg['model']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    folder=OUT/'knowledge'/'spec-contracts'/signature;folder.mkdir(parents=True,exist_ok=True)
    requirements=spec.get('must_have') or []
    conditions=[]
    for index,requirement in enumerate(requirements):
        path=folder/(str(index)+'.json')
        def validate(value):
            if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or len(value[k].strip())<8 for k in ('input','action','expected')):
                raise AutoQAPlanError('完成条件に具体的な入力・操作・正解が必要です')
            if any(term in value['expected'] for term in ('使いやすい','期待通り','正しく動作','効果的','実装予定','要検証')):
                raise AutoQAPlanError('抽象評価ではなく照合する具体値・保存状態を指定してください')
            original=str(requirement)
            if '共同編集' in ' '.join(value.values()) and '共同編集' not in original and '共同編集' not in str(rationale):
                raise AutoQAPlanError('指定されていない共同編集を追加しないでください')
            return value
        value=None
        if path.exists():
            try:value=validate(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError,TypeError,KeyError):pass
        if value is None:
            prompt=('製品要件担当。壊れた完成条件を元の事業範囲から修復します。今回の必須機能1件だけについて、'
                'JSON {input:具体的な入力例,action:最後までの操作,expected:画面や保存値で照合できる正解}を返す。'
                '画面の見やすさ等は別の画像審査で評価する。一般論や機能名の言い換えは不可。依頼されていない検索・共同編集・AI機能を追加しない。'
                '元の要件がAPI機能を含む場合だけ、サンプル操作と外部接続後の検証を分け、実取得したと偽らない。'
                '\n対象者:'+str(spec.get('audience',''))+'\n達成する目的:'+str(spec.get('requested_outcome',''))
                +'\n今回の必須機能:'+str(requirement)+'\n元の事業範囲:'+str(rationale.get('mvp_scope') or rationale.get('hypothesis') or '')[:2000])
            value=ai_json(prompt,cfg,650,max_attempts=1,request_timeout=180,validator=validate)
            write_framework_json(path,value)
        conditions.append('入力: '+value['input']+' / 操作: '+value['action']+' / 期待結果: '+value['expected'])
    if len(conditions)<3:raise AutoQAPlanError('元の必須機能が3件未満のため完成条件を再設計する必要があります')
    repaired=dict(spec,acceptance=conditions,acceptance_contract_policy=DEPARTMENT_SPEC_POLICY,
                  acceptance_repair_reason=issue,acceptance_source_requirements=list(requirements))
    return store_product_spec(name,repaired,source='AI設計・元要件から完成条件を修復')
