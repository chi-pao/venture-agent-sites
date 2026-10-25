"""Live Ollama + Chromium verification of distinct end-to-end app builds.

This is intentionally separate from mocked unit tests. It asks the configured
model to define each product, research design references, create a screen,
inspect it, and execute real browser QA. Any incomplete candidate fails the job.
"""
import json
import os
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
        page, build_detail, ready = app.build(
            0, name, cfg, business_plan, asset_kind="ライブ生成検証HTML",
            allow_partial=False,
        )
        if not page:
            raise RuntimeError(f"{name}: generated page missing: {build_detail}")
        if not ready:
            raise RuntimeError(f"{name}: build/review did not pass: {build_detail}")
        passed, qa_detail, stage = app.automated_product_qa(0, name, page, cfg)
        if not passed or stage != "のぼるさん確認待ち":
            raise RuntimeError(f"{name}: end-to-end browser QA did not pass ({stage}): {qa_detail}")
        summaries.append({"name": name, "build": build_detail, "qa": qa_detail,
                          "stage": stage, "characters": len(page)})
        print("LIVE_PRODUCT_PASS " + json.dumps(summaries[-1], ensure_ascii=False))
    summary = root / "live-summary.json"
    summary.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LIVE_GENERATION_SUMMARY " + json.dumps(summaries, ensure_ascii=False))


if __name__ == "__main__":
    main()
