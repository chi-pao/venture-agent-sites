"""Live Ollama + Chromium verification of distinct end-to-end app builds.

This is intentionally separate from mocked unit tests. It asks the configured
model to define each product, research design references, create a screen,
inspect it, and execute real browser QA. Any incomplete candidate fails the job.
"""
import json
import os
import tempfile
from pathlib import Path

from test_preview import app


PRODUCTS = [
    (
        "オンライン授業参加管理アプリ",
        {
            "category": "教育・講師支援",
            "customer_pain": "個人講師や少人数スクールが、名簿・授業ごとの出欠・遅刻・欠席集計を手作業で管理している。",
            "hypothesis": "名簿登録から授業作成、出欠記録、集計、保存・CSV出力までを一画面で行えると、授業後の確認時間と集計ミスを減らせる。",
            "mvp_scope": "外部APIなしで、受講者名簿、授業日時、出欠状態、出席率の集計、検索、ローカル保存、再読込、CSV出力、JSONバックアップと復元を実際に操作できる。",
            "differentiation": "汎用名簿ではなく、授業単位の出欠と出席率が連動し、誤入力から戻せる講師向けの短い操作導線を検証する。",
        },
    ),
    (
        "在宅ワーク支援アプリ",
        {
            "category": "個人の業務効率化",
            "customer_pain": "在宅勤務者やフリーランスが、予定作業時間と実績時間、休憩を別々に記録し、超過や残り時間を把握しにくい。",
            "hypothesis": "一日の稼働枠と作業予定、実績、休憩をまとめて記録し、残り時間や超過を自動計算できると、時間管理の手間を減らせる。",
            "mvp_scope": "外部APIなしで、日付・開始終了・休憩・作業名・予定時間・実績を入力し、稼働可能時間、予定合計、実績、差分を計算。編集、完了状態、検索、ローカル保存、再読込、CSV出力、JSONバックアップと復元を実装する。",
            "differentiation": "単なるタスク一覧ではなく、休憩を引いた稼働可能時間と予定・実績の差を同じ日付で照合する個人向け導線を検証する。",
        },
    ),
]


def verify_domain_specific_flow(name, html):
    """Exercise the two requested workflows in real Chromium before the general QA."""
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "app.html"
        target.write_text(html, encoding="utf-8")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(target.as_uri())
            operation = page.evaluate("APP.operation")
            if "在宅ワーク" in name:
                if operation != "workday":
                    raise AssertionError(f"expected workday operation, got {operation}")
                page.locator("#workdayDate").fill("2026-10-25")
                page.locator("#workdayStart").fill("09:00")
                page.locator("#workdayEnd").fill("17:00")
                page.locator("#workdayBreak").fill("60")
                page.locator("#saveWorkday").click()
                page.locator("#loadWorkdaySample").click()
                text = page.locator("#workdayTotals").inner_text()
                for expected in ("7時間00分", "4時間30分 / 4時間20分", "-0時間10分", "2時間40分"):
                    if expected not in text:
                        raise AssertionError(f"workday calculation missing {expected!r}: {text}")
                page.reload()
                text = page.locator("#workdayTotals").inner_text()
                if "2時間40分" not in text or page.locator("#recordCount").inner_text() != "3":
                    raise AssertionError(f"workday save/reload failed: {text}")
            elif "授業参加管理" in name:
                if operation != "attendance":
                    raise AssertionError(f"expected attendance operation, got {operation}")
                fields = page.evaluate("APP.fields")
                def submit(status):
                    for field in fields:
                        if not field["required"]:
                            continue
                        locator = page.locator("#" + field["id"])
                        if field["role"] == "date":
                            locator.fill("2026-10-25")
                        elif field["role"] == "status":
                            locator.select_option(label=status)
                        elif field["role"] == "title":
                            locator.fill("佐藤花子" if status == "出席" else "鈴木一郎")
                        elif field["type"] == "number":
                            locator.fill("1")
                        else:
                            locator.fill("確認用")
                    page.locator("#saveRecord").click()
                submit("出席")
                submit("欠席")
                summary = page.locator("#summaryValue").inner_text()
                if "50%" not in summary or "欠席1" not in summary:
                    raise AssertionError(f"attendance aggregation failed: {summary}")
                page.reload()
                if "50%" not in page.locator("#summaryValue").inner_text():
                    raise AssertionError("attendance save/reload failed")
            browser.close()


def main():
    model = os.environ.get("VENTURE_LIVE_MODEL", "qwen2.5-coder:7b")
    vision_model = os.environ.get("VENTURE_LIVE_VISION_MODEL", "qwen2.5vl:3b")
    root = Path(os.environ.get("VENTURE_LIVE_DATA_HOME", "live-generation-artifacts")).resolve()
    if root.exists():
        import shutil
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    app.DB = root / "live.db"
    app.OUT = root / "outputs"
    app.OUT.mkdir(parents=True)
    app.init()
    app.execute("UPDATE autonomous_control SET enabled=1")
    cfg = dict(app.DEFAULT, model=model, qa_vision_model=vision_model,
               url=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
               ai_context=8192, autoqa_setup=False, max_revisions=2,
               max_active=2, publish=False)
    summaries = []
    failures = []
    for name, rationale in PRODUCTS:
        app.execute(
            "INSERT OR REPLACE INTO autonomous_ideas(name,rationale,attempts,created,updated) VALUES(?,?,?,?,?)",
            (name, json.dumps(rationale, ensure_ascii=False), 1, app.now(), app.now()),
        )
        app.event(0, name + ": live Ollama end-to-end test started")
        business_plan = (
            "無料で試せる日本語ブラウザアプリ。対象者の困りごとを解決する具体的な操作を提供する。"
            "収益性・競合優位・利用者の評価は未検証の仮説と明記し、実績を捏造しない。"
        )
        try:
            page, build_detail, ready = app.build(
                0, name, cfg, business_plan, asset_kind="ライブ生成検証HTML",
                allow_partial=True,
            )
            if not page:
                raise RuntimeError(f"generated page missing: {build_detail}")
            if not ready:
                raise RuntimeError(f"build/review did not pass: {build_detail}")
            verify_domain_specific_flow(name, page)
            passed, qa_detail, stage = app.automated_product_qa(0, name, page, cfg)
            if not passed or stage != "のぼるさん確認待ち":
                raise RuntimeError(f"end-to-end browser QA did not pass ({stage}): {qa_detail}")
            summaries.append({"name": name, "status": "pass", "build": build_detail, "qa": qa_detail,
                              "stage": stage, "characters": len(page)})
            print("LIVE_PRODUCT_PASS " + json.dumps(summaries[-1], ensure_ascii=False), flush=True)
        except Exception as exc:
            result={"name":name,"status":"fail","reason":f"{type(exc).__name__}: {exc}"[:1800]}
            summaries.append(result);failures.append(result)
            print("LIVE_PRODUCT_FAIL " + json.dumps(result, ensure_ascii=False), flush=True)
        (root / "live-progress.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = root / "live-summary.json"
    summary.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE_GENERATION_SUMMARY " + json.dumps(summaries, ensure_ascii=False), flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} of {len(PRODUCTS)} live product builds failed; see live-summary.json")


if __name__ == "__main__":
    main()
