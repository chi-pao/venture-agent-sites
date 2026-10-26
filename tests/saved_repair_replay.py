"""Replay only the failed repair on genuine saved candidates; never claim a fresh build."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import time
from pathlib import Path

module=importlib.util.spec_from_file_location("agent",Path(__file__).resolve().parents[1]/"agent/venture_agent_integrated.py")
app=importlib.util.module_from_spec(module)
module.loader.exec_module(app)

def main():
    product=os.environ["VENTURE_LIVE_PRODUCT"]
    roots=list(Path("prior-evidence").glob("**/"+product+"/live.db"))
    if len(roots)!=1:raise RuntimeError("Exactly one real saved product database is required")
    output=Path("saved-repair-evidence")/product
    shutil.copytree(roots[0].parent,output,dirs_exist_ok=True)
    app.DB=output/"live.db";app.OUT=output/"outputs";app.init()
    app.execute("INSERT OR REPLACE INTO agent_jobs(id,started,state,details) VALUES(?,?,?,?)",(0,app.now(),"実行中","保存済み実物の修正単独検証"))
    name=app.query("SELECT name FROM autonomous_ideas")[0]["name"]
    reports=list(app.OUT.glob("**/autoqa/**/report.json"))
    reports=[p for p in reports if json.loads(p.read_text(encoding="utf-8")).get("browser",{}).get("screenshots")]
    report_path=max(reports,key=lambda p:json.loads(p.read_text(encoding="utf-8")).get("checked",""))
    old=json.loads(report_path.read_text(encoding="utf-8"))
    selected_report_checked=old.get("checked")
    def relocate(value):
        if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
        if isinstance(value,list):return [relocate(v) for v in value]
        if isinstance(value,str) and "/outputs/" in value:return str(app.OUT/value.split("/outputs/",1)[1])
        return value
    old=relocate(old)
    candidates=[p for p in app.OUT.glob("**/*.html") if hashlib.sha256(p.read_bytes()).hexdigest()==old["content_sha"]]
    if not candidates:raise RuntimeError("Saved HTML does not match the actual QA report")
    page=candidates[0].read_text(encoding="utf-8")
    brief=old["competitive_brief"]
    if not app.competitive_visual_ready(brief):raise RuntimeError("Competitor screenshot provenance is invalid")
    app.competitive_context=lambda _:{"brief":brief}
    cfg=dict(app.DEFAULT,model="qwen2.5-coder:7b",qa_vision_model="qwen2.5vl:3b",
             url=os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434"),ai_context=8192,visual_repair_timeout=300,autoqa_setup=False)
    result={"product":product,"name":name,"selected_report_checked":selected_report_checked,"source_sha":old["content_sha"],"before_visual":old.get("visual"),"status":"failed"}
    started=time.monotonic()
    try:
        print("SAVED_REPAIR_START",name,flush=True)
        prior_path=output/"repair-result.json"
        prior=json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
        resume=None
        if "対象者・使い方の案内が画面に見つかりません" in prior.get("error",""):
            assets=app.query("SELECT path FROM agent_assets WHERE idea=? AND kind='修正単独検証HTML' ORDER BY id DESC LIMIT 1",(name,))
            if assets:
                saved=Path(relocate(assets[0]["path"]))
                if saved.is_file():resume=saved.read_text(encoding="utf-8")
        if resume:
            candidate,detail=resume,"前回保存した修正案から検査を再開"
            result["resumed_saved_candidate"]=True
        else:
            candidate,detail=app.incremental_product_repair(0,name,page,old["details"],cfg,diagnose=True)
        result["repair_seconds"]=round(time.monotonic()-started,2)
        print("SAVED_REPAIR_GENERATED",result["repair_seconds"],detail,flush=True)
        path=app.save(0,name,"修正単独検証HTML",candidate,"html","機能・画像の再検証前")
        result["candidate"]=str(path)
        errors=app.validate_html(candidate,name)+app.preserve_checkpoint_features(page,candidate)
        if errors:raise RuntimeError(" / ".join(errors))
        if re.findall(r'<script\b[^>]*>.*?</script\s*>',candidate,re.I|re.S)!=re.findall(r'<script\b[^>]*>.*?</script\s*>',page,re.I|re.S):
            raise RuntimeError("Visual repair changed application JavaScript")
        digest=hashlib.sha256(candidate.encode()).hexdigest()
        directory=report_path.parents[2]/digest[:16]/app.uuid.uuid4().hex
        directory.mkdir(parents=True,exist_ok=True)
        plan=dict(old["plan"],audience_quotes=app.visible_audience_copy(candidate)[:2])
        plan=app.validate_qa_plan(plan,app.get_product_spec(name))
        browser=app.execute_browser_qa(name,candidate,plan,directory)
        print("SAVED_REPAIR_BROWSER_PASS",len(browser["scenarios"]),flush=True)
        visual=app.review_qa_images(name,browser,cfg)
        keys=("audience","design","readability","mobile","usefulness")
        issues=[key+": "+visual[key]["reason"] for key in keys if visual[key]["score"]<4]
        updated=dict(old,checked=app.now(),content_sha=digest,browser=browser,plan=plan,visual=visual,passed=not issues,
                     details="画像判定で改善が必要: "+" / ".join(issues) if issues else "修正単独検証合格。全生成検証・公開許可は別。",
                     repair_seconds=result["repair_seconds"])
        app.write_framework_json(directory/"report.json",updated)
        result.update(status="pass" if not issues else "needs_repair",candidate=str(path),visual=visual,browser_checks=len(browser["scenarios"]))
        if issues:raise RuntimeError(updated["details"])
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        result["total_seconds"]=round(time.monotonic()-started,2)
        app.write_framework_json(output/"repair-result.json",result)
        print("SAVED_REPAIR_RESULT",json.dumps(result,ensure_ascii=False),flush=True)
    if result["status"]!="pass":raise RuntimeError(result.get("error","repair incomplete"))

if __name__=="__main__":main()
