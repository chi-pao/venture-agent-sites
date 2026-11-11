# -*- coding: utf-8 -*-
"""事業スタジオ：AIが収益化できそうなアプリを考え、審査し、ある程度の品質まで自動で作る。
最後に、オーナー（のぼるさん）が「続ける・ブラッシュアップ・やめる」を決める。

使い方（studio フォルダーで。studio.cmd でも同じ）:
  py studio.py doctor                       準備ができているか確かめる
  py studio.py run                          ①企画→②市場・競合→③審査→⑤開発→⑥品質→⑦公開→⑧SNS案 →【最終確認】
  py studio.py auto                         定期実行用（順番待ちの開発を進め、間隔が空いたら新しく企画）
  py studio.py list                         一覧（data/BOARD.md にも書き出す）
  py studio.py show <番号>                  最終確認の資料を表示
  py studio.py decide <番号> continue       続ける（事業として独立。SNS案を承認待ちで依頼一覧へ）
  py studio.py decide <番号> brushup --note "直す点"   ブラッシュアップ（直して、もう一度最終確認へ）
  py studio.py decide <番号> kill --note "理由"        やめる（理由は次の企画に生かす）
  py studio.py sns                          ⑧「のぼるの挑戦記」の今週の投稿案を作る
  py studio.py affiliate                    ⑩楽天アフィリエイトのテーマ・商品まとめページ・投稿案を作る
  py studio.py metrics <番号> --visits N --signups N --revenue 円   ⑨実際の数字を記録
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import affiliate as A  # noqa: E402
import departments as D  # noqa: E402
import publish as P  # noqa: E402
import sns as S  # noqa: E402
from engine import Engine, EngineError  # noqa: E402
from store import STAGES, Store, next_action, notify, now  # noqa: E402

RESEARCH_TOOLS = ["WebSearch", "WebFetch"]
FILE_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]
RUN_TOOLS = ["Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)", "Bash(py:*)", "Bash(python:*)",
             "Bash(pip:*)", "Bash(git init:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(ls:*)"]
QUEUED = "queued"  # 審査を通り、開発の順番待ち
STAGES.setdefault(QUEUED, "開発の順番待ち")


# ------------------------------------------------------------------ 準備
def load_config(path=None):
    path = Path(path) if path else HERE / "config.json"
    if not path.exists():
        shutil.copy(HERE / "config.example.json", path)
        print(f"設定ファイルを作りました: {path}（必要なら書き換えてください）")
    cfg = json.loads((HERE / "config.example.json").read_text(encoding="utf-8"))
    cfg.update(json.loads(path.read_text(encoding="utf-8")))  # 新しい項目は見本の値を使う
    cfg["_data"] = str((path.parent / cfg.get("data_dir", "data")).resolve())
    return cfg


def total_score(idea):
    s = idea.get("scores") or {}
    vals = [int(s.get(k, 0) or 0) for k in ("pain", "willingness_to_pay", "reach", "buildability", "timing")]
    return sum(max(0, min(5, v)) for v in vals) * 4  # 100点満点


def spec_text(rec):
    i, m, r = rec["idea"], rec.get("market") or {}, rec.get("review") or {}
    lines = [f"# {i['title']}", "", i.get("one_liner", ""), "",
             f"- 使う人: {i.get('target_user')}", f"- 払う人: {i.get('payer')}",
             f"- 困りごと: {i.get('pain')}", f"- 解決: {i.get('solution')}",
             f"- 収益: {i.get('monetization')}（価格の仮説: {i.get('price_hypothesis')}）",
             "", "## 勝てる違い（市場・競合部）"] + [f"- {x}" for x in m.get("differentiation", [])]
    lines += ["", "## 最初の版に入れる機能（審査部）"] + [f"- {x}" for x in r.get("mvp_scope", [])]
    lines += ["", "## 入れないもの"] + [f"- {x}" for x in r.get("out_of_scope", [])]
    lines += ["", "## 法律・規約の注意"] + [f"- {x.get('risk')}（{x.get('law_or_rule')}）→ {x.get('mitigation')}"
                                       for x in r.get("legal", []) if isinstance(x, dict)]
    for fb in rec.get("feedback", []):
        lines += ["", f"## オーナーからの指摘（{fb['at']}）", fb["note"]]
    return "\n".join(lines)


# ------------------------------------------------------------------ ①②③
def plan_ideas(cfg, store, eng, count=None):
    count = count or cfg["ideas_per_run"]
    print(f"①企画部: 案を{count}件考えています（Web検索あり。十数分かかることがあります）…")
    work = Path(cfg["_data"]) / "work"
    res = eng.ask_json("企画部", D.ideation_prompt(count, store.learning_text(), store.past_titles(),
                                                  cfg["owner_assets"]),
                       D.IDEATION_REQUIRED, tools=RESEARCH_TOOLS, cwd=work, max_turns=cfg["max_turns"]["research"])
    recs = []
    for idea in res["ideas"]:
        if isinstance(idea, dict) and idea.get("title"):
            rec = {"id": store.new_id(idea["title"]), "idea": idea, "score": total_score(idea), "history": []}
            store.set_stage(rec, "idea", f"企画の点数 {rec['score']}")
            recs.append(rec)
    recs.sort(key=lambda r: r["score"], reverse=True)
    picked = [r for r in recs if r["score"] >= cfg["min_total_score"]][:cfg["market_checks"]]
    for r in recs:
        if r not in picked:
            store.set_stage(r, "market_no_go", "企画の点数が足りない、または上位に入らなかった")
    passed = []
    for rec in picked:
        title = rec["idea"]["title"]
        try:
            print(f"②市場・競合部: 「{title}」を調べています…")
            market = eng.ask_json("市場・競合部", D.market_prompt(rec["idea"]), D.MARKET_REQUIRED,
                                  tools=RESEARCH_TOOLS, cwd=work, max_turns=cfg["max_turns"]["research"])
            rec["market"] = market
            go = str(market["verdict"]).upper().replace("-", "_") == "GO" and \
                float(market["win_probability"]) >= cfg["min_win_probability"]
            if not go:
                store.set_stage(rec, "market_no_go", market.get("reason", ""))
                continue
            print(f"③審査部: 「{title}」を審査しています…")
            review = eng.ask_json("審査部", D.review_prompt(rec["idea"], market), D.REVIEW_REQUIRED,
                                  tools=RESEARCH_TOOLS, cwd=work, max_turns=cfg["max_turns"]["research"])
            rec["review"] = review
            if str(review["verdict"]).upper() != "PASS":
                store.set_stage(rec, "review_fail", review.get("reason", ""))
                continue
            store.set_stage(rec, QUEUED, "3部門を通過。自動で開発に進む")
            passed.append(rec)
        except EngineError as e:
            store.set_stage(rec, "error", str(e))
            print(f"  失敗: {e}")
    return recs, passed


# ------------------------------------------------------------------ ⑤⑥⑦⑧
def develop(cfg, store, eng, rec):
    build_dir = store.folder(rec["id"]) / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    spec = spec_text(rec)
    (build_dir / "SPEC.md").write_text(spec, encoding="utf-8")
    feedback = rec["feedback"][-1]["note"] if rec.get("feedback") else ""
    rounds = 0
    while True:
        print("⑤開発部: 作っています（1時間ほどかかることがあります）…")
        build = eng.ask_json("開発部", D.build_prompt(spec, feedback, cfg.get("signup_url", "")), D.BUILD_REQUIRED,
                             tools=FILE_TOOLS + RUN_TOOLS, cwd=build_dir,
                             max_turns=cfg["max_turns"]["build"], permission_mode="acceptEdits")
        print("⑥品質部: 開発部とは別に検査しています…")
        qa = eng.ask_json("品質部", D.qa_prompt(spec, build), D.QA_REQUIRED,
                          tools=FILE_TOOLS + RUN_TOOLS, cwd=build_dir,
                          max_turns=cfg["max_turns"]["qa"], permission_mode="acceptEdits")
        ok = "要修正" not in str(qa["verdict"])
        if ok or rounds >= cfg["auto_fix_rounds"]:
            return build, qa, ok
        rounds += 1
        feedback = "品質部の指摘（すべて直す）:\n" + "\n".join(f"- {x}" for x in qa["blocking_issues"])
        print(f"品質部が要修正と判断したので、開発部が直します（{rounds}回目）…")


def owner_package(rec):
    """【最終確認】で見る資料。"""
    i, m, r = rec["idea"], rec.get("market") or {}, rec.get("review") or {}
    b, q, s = rec.get("build") or {}, rec.get("qa") or {}, rec.get("sns") or {}
    ue = r.get("unit_economics") or {}
    out = [f"# 最終確認 {rec['id']}：{i['title']}", "", f"**一言**: {i.get('one_liner')}", "",
           "## 1. 見てみる"]
    if rec.get("preview_url"):
        out.append(f"- スマホでも開けます: {rec['preview_url']}（{rec.get('preview_note')}）")
    else:
        out.append(f"- 確認用ページ: なし（{rec.get('preview_note', '')}）")
    out += [f"- パソコンで動かす: data/ideas/{rec['id']}/build/ で `{b.get('how_to_run')}`", "",
            "## 2. なぜ収益化できそうか", "| 項目 | 内容 |", "|---|---|",
            f"| 使う人 / 払う人 | {i.get('target_user')} / {i.get('payer')} |",
            f"| 困りごと | {i.get('pain')} |",
            f"| 収益の取り方 | {i.get('monetization')}（{i.get('price_hypothesis')}） |",
            f"| 企画の点数 | {rec.get('score')} / 100 |",
            f"| 勝てる見込み | {m.get('win_probability')}%（{m.get('growth_outlook')}） |",
            f"| 月10万円に必要な有料利用者 | {ue.get('needed_paying_users_for_100k_yen')}（仮説） |",
            f"| 最初の100人 | {(r.get('acquisition') or {}).get('first_100_plan') or i.get('first_100_users')} |",
            "", "困りごとの根拠:"]
    out += [f"- 「{e.get('quote')}」 {e.get('url')}" for e in i.get("evidence", [])]
    out += ["", "競合:"]
    out += [f"- {c.get('name')}（{c.get('price')}）弱み: {c.get('weakness')} {c.get('url')}"
            for c in m.get("competitors", [])]
    out += ["", "勝てる違い:"] + [f"- {x}" for x in m.get("differentiation", [])]
    out += ["", "## 3. 心配な点（審査部の反対意見）"] + [f"- {x}" for x in r.get("devils_advocate", [])]
    out += ["", "## 4. できたこと / まだのこと"]
    out += [f"- ✅ {x}" for x in b.get("features_done", [])] + [f"- ⏳ {x}" for x in b.get("not_done", [])]
    out += ["", f"## 5. 品質部の検査（結論: {q.get('verdict')}）", "| 項目 | 結果 | 確かめ方 |", "|---|---|---|"]
    out += [f"| {c.get('item')} | {c.get('result')} | {c.get('evidence')} |" for c in q.get("checks", [])]
    out += ["", "残っている問題:"]
    out += [f"- {x}" for x in q.get("blocking_issues", [])] or ["- なし"]
    out += ["", f"## 6. 続ける場合の SNS（{len(s.get('posts', []))} 件の投稿案。続けると決めたら承認待ちで依頼一覧に入ります）"]
    out += [f"- {p.get('channel')}：{p.get('title')}" for p in s.get("posts", [])]
    out += ["", "## 7. やめる基準（続けた場合）"] + [f"- {x}" for x in r.get("kill_criteria", [])]
    out += ["", "## 8. 決める",
            f"- 続ける（事業として独立させる）: `py studio.py decide {rec['id']} continue`",
            f"- ブラッシュアップ: `py studio.py decide {rec['id']} brushup --note \"直す点\"`",
            f"- やめる: `py studio.py decide {rec['id']} kill --note \"理由\"`"]
    return "\n".join(out)


def build_and_package(cfg, store, eng, rec):
    store.set_stage(rec, "building", "開発部が作業中")
    store.write_board()
    try:
        build, qa, ok = develop(cfg, store, eng, rec)
        rec["build"], rec["qa"] = build, qa
        print("⑦公開部: 確認用ページを用意しています…")
        static = P.find_static(store.folder(rec["id"]) / "build", build.get("static_dir", ""))
        rec["preview_url"], rec["preview_note"] = P.publish(cfg, Path(cfg["_data"]) / "work", rec["id"], static)
        print("⑧SNS運用部: 続ける場合の投稿案を作っています…")
        subject = spec_text(rec) + f"\n\nアプリのURL: {rec['preview_url'] or '未公開'}"
        rec["sns"] = eng.ask_json("SNS運用部", D.sns_prompt("launch", subject, cfg["owner_assets"], cfg["sns_rules"],
                                                          S.existing_titles(cfg)),
                                  D.SNS_REQUIRED, tools=RESEARCH_TOOLS, cwd=Path(cfg["_data"]) / "work",
                                  max_turns=cfg["max_turns"]["research"])
    except EngineError as e:
        store.set_stage(rec, "error", str(e))
        store.write_board()
        print(f"失敗: {e}")
        return False
    (store.folder(rec["id"]) / "最終確認.md").write_text(owner_package(rec), encoding="utf-8")
    store.set_stage(rec, "owner_check" if ok else "needs_fix",
                    "最終確認の資料ができた" if ok else "自動の手直しでも品質の基準に届かなかった")
    store.write_board()
    head = "【最終確認】見てほしいアプリができました" if ok else "【確認】品質の基準に届かなかったアプリがあります"
    notify(cfg, cfg["_data"], f"{head}：{rec['idea']['title']}",
           f"資料: studio/data/ideas/{rec['id']}/最終確認.md\n"
           f"確認用ページ: {rec['preview_url'] or 'なし'}（{rec['preview_note']}）\n"
           f"決め方: `py studio.py decide {rec['id']} continue / brushup / kill`")
    return True


def process_queue(cfg, store, eng):
    queued = [r for r in store.all() if r["stage"] in (QUEUED, "brushup")]
    queued.sort(key=lambda r: (r["stage"] != "brushup", -r.get("score", 0)))  # 直しを先に
    for rec in queued[:cfg["max_builds_per_run"]]:
        build_and_package(cfg, store, eng, rec)
    left = len(queued) - min(len(queued), cfg["max_builds_per_run"])
    if left:
        print(f"開発の順番待ちが {left} 件あります（次の run / auto で進みます）。")


def cmd_run(cfg, store, eng, args):
    recs, passed = plan_ideas(cfg, store, eng, args.count)
    store.write_board()
    _mark("last_plan")
    if not passed:
        notify(cfg, cfg["_data"], "今回は審査を通った案がありません",
               "見送りの理由は studio/data/BOARD.md にあります。次の企画に学びとして渡します。")
    process_queue(cfg, store, eng)
    print(f"（今回の Claude Code の利用量の目安: {eng.total_cost:.2f} ドル相当。契約の範囲内なら追加の請求はありません）")


def _state_path():
    return Path(_CFG["_data"]) / "auto.json"


def _mark(key):
    p = _state_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data[key] = datetime.now().isoformat(timespec="minutes")
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _due(key, days):
    p = _state_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return key not in data or datetime.fromisoformat(data[key]) + timedelta(days=days) <= datetime.now()


def cmd_auto(cfg, store, eng, args):
    """定期実行用。あなたの判断待ちが多いときは新しく作らない。"""
    waiting = [r for r in store.all() if r["stage"] in ("owner_check", "needs_fix")]
    if any(r["stage"] in (QUEUED, "brushup") for r in store.all()):
        process_queue(cfg, store, eng)
    elif len(waiting) >= cfg["max_waiting_for_owner"]:
        print(f"あなたの判断待ちが {len(waiting)} 件あるので、新しい企画はお休みします。")
    elif _due("last_plan", cfg["plan_every_days"]):
        cmd_run(cfg, store, eng, argparse.Namespace(count=None))
    if cfg.get("weekly_sns") and _due("last_sns", 7):
        cmd_sns(cfg, store, eng, args)
    if cfg.get("weekly_affiliate") and _due("last_affiliate", 7):
        cmd_affiliate(cfg, store, eng, args)
    store.write_board()


# ------------------------------------------------------------------ 最終確認の判断
def business_file(rec):
    i, r = rec["idea"], rec.get("review") or {}
    return "\n".join([
        f"# {i['title']}", "", f"状態: 続ける（{now()} のぼるさんが決定）。事業スタジオ {rec['id']} から独立。", "",
        "| 項目 | 内容 |", "|---|---|",
        f"| 使う人 / 払う人 | {i.get('target_user')} / {i.get('payer')} |",
        f"| 収益の取り方 | {i.get('monetization')}（{i.get('price_hypothesis')}・仮説） |",
        f"| 確認用ページ | {rec.get('preview_url') or '未公開'} |",
        f"| コード | studio/data/ideas/{rec['id']}/build/（自分のリポジトリへ移す） |",
        "", "## やめる基準"] + [f"- {x}" for x in r.get("kill_criteria", [])] + [
        "", "## 次にやること（担当）",
        "- [ ] コードを専用のリポジトリに移す（Claude Code）",
        "- [ ] 事前登録・問い合わせの受け口を決める（のぼるさん・要承認）",
        "- [ ] SNS の投稿案を確認して OK を出す（のぼるさん）→ ChatGPT → Metricool",
        "- [ ] 本番の公開先と支払い（Stripe 本番）を決める（のぼるさん・要承認）",
        "- [ ] 毎週の数字を `py studio.py metrics` で記録（数字の記録担当）"]) + "\n"


def cmd_decide(cfg, store, eng, args):
    rec = store.load(args.id)
    if rec["stage"] not in ("owner_check", "needs_fix"):
        raise SystemExit(f"この案は今「{STAGES.get(rec['stage'])}」なので、まだ判断する段階ではありません。")
    rec.setdefault("decisions", []).append({"choice": args.choice, "note": args.note or "", "at": now()})
    if args.choice == "brushup":
        if not args.note:
            raise SystemExit("ブラッシュアップでは --note \"直す点\" を書いてください。")
        rec.setdefault("feedback", []).append({"note": args.note, "at": now()})
        store.set_stage(rec, "brushup", args.note)
        store.write_board()
        if args.later:
            print("次の run / auto で直します。")
            return
        build_and_package(cfg, store, eng, rec)
        return
    if args.choice == "kill":
        store.set_stage(rec, "killed", args.note or "")
        store.write_board()
        store.learning_text()
        print("やめました。理由は次の企画部への学びに入ります。")
        return
    # 続ける
    folder = S.ROOT / "ops" / "businesses"
    folder.mkdir(parents=True, exist_ok=True)
    biz = folder / f"studio-{rec['id']}.md"
    if not cfg.get("mock"):
        biz.write_text(business_file(rec), encoding="utf-8")
    added, dropped = S.add_posts(cfg, f"ST-{rec['id']}", rec["idea"]["title"], (rec.get("sns") or {}).get("posts", []),
                                 rec.get("preview_url") or cfg.get("challenge_url", ""), f"studio_{rec['id']}")
    store.set_stage(rec, "continuing", args.note or "")
    store.write_board()
    msg = (f"事業ファイル: ops/businesses/{biz.name}\nSNS の投稿案 {added} 件を「承認待ち」で ops/tasks/queue.json に入れました。")
    if dropped:
        msg += "\n決まりに合わず外した投稿案:\n" + "\n".join(f"- {d}" for d in dropped)
    msg += "\n次は Claude Code に「studio の変更を GitHub に反映して」と頼んでください（PR で反映）。"
    notify(cfg, cfg["_data"], f"続けると決めました：{rec['idea']['title']}", msg)


# ------------------------------------------------------------------ ⑧ 挑戦記の週の投稿 ⑨ 数字
def cmd_sns(cfg, store, eng, args):
    store.write_board()
    board = (Path(cfg["_data"]) / "BOARD.md").read_text(encoding="utf-8")
    subject = "# 今週の事業スタジオの一覧\n" + board + "\n\n# 過去の学び\n" + store.learning_text()
    print("⑧SNS運用部: 「のぼるの挑戦記」の今週の投稿案を作っています…")
    res = eng.ask_json("SNS運用部", D.sns_prompt("weekly", subject, cfg["owner_assets"], cfg["sns_rules"],
                                                S.existing_titles(cfg)),
                       D.SNS_REQUIRED, tools=[], cwd=Path(cfg["_data"]) / "work", max_turns=10)
    tag = datetime.now().strftime("%Y%m%d")
    added, dropped = S.add_posts(cfg, f"CH-{tag}", "のぼるの挑戦記", res["posts"], cfg.get("challenge_url", ""),
                                 f"challenge_{tag}")
    _mark("last_sns")
    msg = f"{added} 件を「承認待ち」で ops/tasks/queue.json に入れました。OK を出すと今の流れ（ChatGPT → Metricool）で予約されます。"
    if dropped:
        msg += "\n決まりに合わず外した投稿案:\n" + "\n".join(f"- {d}" for d in dropped)
    notify(cfg, cfg["_data"], "「のぼるの挑戦記」の今週の投稿案ができました", msg)


def cmd_affiliate(cfg, store, eng, args):
    hist_path = Path(cfg["_data"]) / "affiliate.json"
    past = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else []
    print("⑩物販・アフィリエイト部: 今あるSNSで売れそうなテーマを考えています…")
    res = eng.ask_json("物販・アフィリエイト部", D.affiliate_prompt(cfg["owner_assets"], store.learning_text(),
                                                            [p["title"] for p in past]),
                       D.AFFILIATE_REQUIRED, tools=RESEARCH_TOOLS, cwd=Path(cfg["_data"]) / "work",
                       max_turns=cfg["max_turns"]["research"])
    picks_root = Path(cfg["_data"]) if cfg.get("mock") else S.ROOT
    lines = []
    for n, theme in enumerate(res["themes"][:cfg["affiliate_themes"]], 1):
        entry = {"title": theme.get("title", ""), "at": now(), "theme": theme}
        past.append(entry)
        items = []
        if cfg.get("mock"):
            items = eng._mock("楽天商品")["items"]
        elif cfg.get("rakuten_app_id"):
            for kw in theme.get("search_keywords", [])[:2]:
                try:
                    items += A.search(cfg, kw)
                except A.RakutenError as e:
                    lines.append(f"- {entry['title']}: {e}")
                    break
            seen, uniq = set(), []
            for it in items:
                if it["url"] not in seen:
                    seen.add(it["url"]); uniq.append(it)
            items = A.pick(uniq, cfg["affiliate_min_reviews"])
        if not items:
            entry["status"] = "商品は未選定（楽天のアプリIDが未設定、または条件に合う商品なし）"
            lines.append(f"- {entry['title']}: {entry['status']}。探すキーワード: {'、'.join(theme.get('search_keywords', []))}")
            continue
        slug, fetched = A.write_page(picks_root, theme, items)
        page_url = f"https://{cfg['pages_host']}/picks/{slug}/"
        facts = [f"{it['name'][:40]}：{it['price']:,}円（{fetched}時点・楽天市場）" for it in items]
        facts += ["価格・在庫は変わることがあります", "レビュー件数の多い順に並べています（おすすめの順位ではありません）"]
        subject = json.dumps(theme, ensure_ascii=False, indent=1) + "\n\n# 使ってよい事実\n" + "\n".join(facts)
        print(f"⑧SNS運用部: 「{entry['title']}」の投稿案を作っています…")
        posts = eng.ask_json("SNS運用部", D.sns_prompt("affiliate", subject, cfg["owner_assets"], cfg["sns_rules"],
                                                      S.existing_titles(cfg)),
                             D.SNS_REQUIRED, tools=[], cwd=Path(cfg["_data"]) / "work", max_turns=10)["posts"]
        for p in posts:
            p["facts"] = facts  # 事実は楽天から取った値だけに限る（AIが足した数字は使わない）
        added, dropped = S.add_posts(cfg, f"AF-{slug[:8]}-{n}", "楽天アフィリエイト", posts, page_url, f"af_{slug}",
                                     extra={"affiliate": True, "pr_label": True})
        entry.update(status="まとめページと投稿案を作成", page=f"picks/{slug}/index.html", posts=added)
        lines.append(f"- {entry['title']}: まとめページ picks/{slug}/（{len(items)}商品）、投稿案 {added} 件を承認待ちで追加")
        lines += [f"    外した投稿案: {d}" for d in dropped]
    hist_path.write_text(json.dumps(past, ensure_ascii=False, indent=1), encoding="utf-8")
    _mark("last_affiliate")
    notify(cfg, cfg["_data"], "楽天アフィリエイトの企画ができました",
           "\n".join(lines) + "\n\nまとめページは GitHub に反映すると公開されます（Claude Code に「studio の変更を反映して」と頼む）。"
           "\n投稿は今までどおり、あなたの OK のあと ChatGPT → Metricool で予約されます。")


def cmd_metrics(cfg, store, eng, args):
    rec = store.load(args.id)
    rec.setdefault("metrics", []).append({"at": now(), "visits": args.visits, "signups": args.signups,
                                          "revenue_yen": args.revenue})
    store.save(rec)
    store.learning_text()
    print("記録しました（企画部への学びにも入ります）。")


# ------------------------------------------------------------------ 表示・点検
def cmd_list(cfg, store, eng, args):
    store.write_board()
    print((Path(cfg["_data"]) / "BOARD.md").read_text(encoding="utf-8"))


def cmd_show(cfg, store, eng, args):
    rec = store.load(args.id)
    print(owner_package(rec) if rec.get("build") else
          f"{rec['idea']['title']}：{STAGES.get(rec['stage'])}\n" +
          "\n".join(f"- {h['at']} {h['stage']} {h.get('note', '')}" for h in rec["history"]))


def cmd_doctor(cfg, store, eng, args):
    try:
        print("Claude Code:", eng.claude_cmd())
    except EngineError as e:
        print("✗", e)
    print("データの場所:", cfg["_data"])
    print("SNS の依頼一覧:", S.queue_path(cfg))
    print("確認用ページの公開:", "オン" if cfg.get("publish_previews") else "オフ", f"（{cfg['github_repo']} の preview/ ブランチ）")
    print("楽天の商品検索:", "設定あり" if cfg.get("rakuten_app_id") else "未設定（テーマと探すキーワードだけ作ります）",
          "／アフィリエイトID:", "設定あり" if cfg.get("rakuten_affiliate_id") else "未設定")
    print("Discord 通知:", "設定あり" if cfg.get("discord_webhook_url") else "未設定（data/INBOX.md にだけ残ります）")
    print("練習モード:", "オン" if eng.mock else "オフ")


_CFG = {}


def main(argv=None):
    p = argparse.ArgumentParser(description="事業スタジオ")
    p.add_argument("--config")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("doctor", "auto", "list", "sns", "affiliate"):
        sub.add_parser(name)
    r = sub.add_parser("run"); r.add_argument("--count", type=int)
    s = sub.add_parser("show"); s.add_argument("id")
    d = sub.add_parser("decide"); d.add_argument("id"); d.add_argument("choice", choices=["continue", "brushup", "kill"])
    d.add_argument("--note"); d.add_argument("--later", action="store_true", help="ブラッシュアップを次の自動実行に回す")
    m = sub.add_parser("metrics"); m.add_argument("id"); m.add_argument("--visits", type=int)
    m.add_argument("--signups", type=int); m.add_argument("--revenue", type=int)
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    _CFG.clear(); _CFG.update(cfg)
    store = Store(cfg["_data"])
    eng = Engine(cfg, Path(cfg["_data"]) / "logs" / "claude.jsonl")
    {"doctor": cmd_doctor, "run": cmd_run, "auto": cmd_auto, "list": cmd_list, "show": cmd_show,
     "decide": cmd_decide, "sns": cmd_sns, "affiliate": cmd_affiliate, "metrics": cmd_metrics}[args.cmd](cfg, store, eng, args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
