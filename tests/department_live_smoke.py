"""Real model/browser proof of the department coordinator; never substitutes engines.

Failures remain failures. The installation manifest must not point to this
experimental program just because the control-plane unit tests passed.
"""
import json
import os
from pathlib import Path
import time
from test_preview import app
from live_generation_smoke import PRODUCTS


def main():
    key=os.environ['VENTURE_LIVE_PRODUCT']
    products=dict(PRODUCTS)
    names={'attendance':'オンライン授業参加管理アプリ','workday':'在宅ワーク支援アプリ','returns':'小規模EC向け返品対応管理アプリ'}
    name=names[key]
    products[names['returns']]=dict(category='EC業務支援',
        customer_pain='小規模EC運営者が注文ごとの返品期限、返金、対応漏れを複数の表で確認している。',
        hypothesis='注文登録、返品理由・期限・対応状況、返金計算、未対応一覧を一連で扱うと見落としを減らせる。',
        mvp_scope='架空の注文を手入力し、返品受付、注文金額・送料・返金額、期限超過、対応完了、検索、保存・再読込、CSV出力とJSON復元を試せる。外部API不要。',
        differentiation='注文ごとに次の対応と期限を明示し、返金計算と対応一覧を結ぶ操作導線を仮説として検証する。')
    root=Path(os.environ.get('VENTURE_LIVE_DATA_HOME','department-live-artifacts/'+key)).resolve()
    root.mkdir(parents=True,exist_ok=True);app.DB=root/'live.db';app.OUT=root/'outputs';app.OUT.mkdir(exist_ok=True)
    app.init();app.execute('UPDATE autonomous_control SET enabled=1')
    job=app.execute('INSERT INTO agent_jobs(started,state,details) VALUES(?,?,?)',(app.now(),'実行中','部署制御の実モデル・実ブラウザ検証'))
    app.execute('INSERT OR REPLACE INTO autonomous_ideas(name,rationale,attempts,created,updated) VALUES(?,?,?,?,?)',
        (name,json.dumps(products[name],ensure_ascii=False),1,app.now(),app.now()))
    cfg=dict(app.DEFAULT,model='qwen2.5-coder:7b',code_model='qwen2.5-coder:7b',qa_vision_model='qwen2.5vl:3b',
        url=os.environ.get('OLLAMA_HOST','http://127.0.0.1:11435'),ai_context=8192,autoqa_setup=False,max_revisions=2,publish=False)
    proposal_model=os.environ.get('VENTURE_LIVE_PROPOSAL_MODEL','').strip()
    qa_model=os.environ.get('VENTURE_LIVE_QA_MODEL','').strip()
    cfg['department_models']={role:model for role,model in (('proposal',proposal_model),('verification',qa_model)) if model}
    oracle_model=os.environ.get('VENTURE_LIVE_ORACLE_MODEL','').strip()
    if oracle_model:cfg.update(qa_oracle_model=oracle_model,qa_oracle_timeout=300)
    if qa_model=='qwen2.5:14b':cfg.update(qa_part_timeout=300,qa_part_timeout_ceiling=480)
    cfg['qa_mapping_model']=qa_model or oracle_model or cfg['model']
    results=[];started=time.monotonic()
    try:
        for iteration in range(3):
            result=app.run_product_departments(job,name,cfg)
            results.append(dict(iteration=iteration+1,stage=result['stage'],details=result['details'],
                departments=result['departments'],feedback=result['feedback']))
            print('DEPARTMENT_REAL_RESULT',json.dumps(results[-1],ensure_ascii=False),flush=True)
            if result['stage']=='のぼるさん確認待ち':
                candidate=result['candidate']
                if not app.production_acceptance(name,candidate['content_sha']):raise AssertionError('合格証拠がない')
                if result['departments']['operations']['status']!='approval_wait':raise AssertionError('公開承認制御が不正')
                return
        raise RuntimeError('部署制御の実生成は3周内に品質基準へ到達していません。未完成のまま保持します。')
    finally:
        (root/'department-proof.json').write_text(json.dumps(dict(product=name,models=dict(coding=cfg['model'],proposal=proposal_model or cfg['model'],verification=qa_model or cfg['model'],vision=cfg['qa_vision_model'],oracle=oracle_model or qa_model or cfg['model']),rounds=results,
            seconds=round(time.monotonic()-started,2),release_ready=bool(results and results[-1]['stage']=='のぼるさん確認待ち')),
            ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
