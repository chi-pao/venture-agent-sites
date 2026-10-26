"""Replay genuine failed-run screenshots through the production visual reviewer.
No app regeneration and no mocked model response. This isolates model/runtime faults.
"""
import importlib.util
import json
import os
import time
import tempfile
from pathlib import Path

module = importlib.util.spec_from_file_location("agent", Path(__file__).resolve().parents[1] / "agent/venture_agent_integrated.py")
app = importlib.util.module_from_spec(module)
module.loader.exec_module(app)

def main():
    evidence = Path(os.environ.get("VISION_EVIDENCE", "prior-evidence"))
    product = os.environ["VENTURE_LIVE_PRODUCT"]
    reports = list(evidence.glob("**/" + product + "/outputs/**/autoqa/**/report.json"))
    if len(reports) != 1:
        raise RuntimeError(f"Expected one real saved QA report, found {len(reports)}")
    report_path = reports[0]
    product_root = next(parent for parent in report_path.parents if parent.name == product)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, str) and "/outputs/" in value:
            return str(product_root / "outputs" / value.split("/outputs/", 1)[1])
        return value
    brief = relocate(report["competitive_brief"])
    browser = relocate(report["browser"])
    if not app.competitive_visual_ready(brief):
        raise RuntimeError("Real competitor screenshots did not pass provenance checks")
    app.competitive_context = lambda name: {"brief": brief}
    output = Path("vision-probe-results") / product
    output.mkdir(parents=True, exist_ok=True)
    model = "qwen2.5vl:3b"
    cfg = dict(app.DEFAULT, model=model, qa_vision_model=model,
               url="http://127.0.0.1:11434", qa_vision_context=4096,
               qa_vision_timeout=300)
    started = time.monotonic()
    result = {"product": product, "source_report": str(report_path),
              "context": 4096, "timeout_seconds": 300, "model": model}
    with tempfile.TemporaryDirectory() as directory:
        app.DB = Path(directory) / "probe.db"
        app.OUT = Path(directory) / "outputs"
        app.OUT.mkdir()
        app.init()
        print("PRODUCTION_VISION_START", json.dumps(result), flush=True)
        try:
            review = app.review_qa_images(product, browser, cfg)
            result.update(status="completed", review=review,
                          quality_passed=all(review[key]["score"] >= 4 for key in ("audience", "design", "readability", "mobile", "usefulness")))
        except Exception as exc:
            result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            import shutil
            traces=app.OUT/"knowledge"/"vision-traces"
            if traces.exists():
                shutil.copytree(traces, output/"traces", dirs_exist_ok=True)
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
            (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("PRODUCTION_VISION_RESULT", json.dumps(result, ensure_ascii=False), flush=True)
    if result["status"] != "completed":
        raise RuntimeError(result["error"])
    # Inference completion is not product acceptance. Full build QA is separate.
    print("INFERENCE_COMPLETED; PRODUCT_ACCEPTANCE_NOT_GRANTED", flush=True)

if __name__ == "__main__":
    main()
