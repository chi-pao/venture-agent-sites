# -*- coding: utf-8 -*-
"""8つの部門の指示書（プロンプト）と、答えの形。

どの部門にも共通の決まり（COMMON_RULES）を渡す。これは ops/ の決まりを引き継いだもの。
"""
import json

COMMON_RULES = """
# 全部門の決まり（必ず守る）
- 返事も書く文章もすべて日本語。
- 出典URLと確認日のない数字（市場規模・料金・利用者数・成約率）を書かない。確かめられなければ「未確認」。推測は「仮説」と書く。
- 競合や利用者の声を根拠にするときは、実際に開いたページの文をそのまま短く引用する（quote）。作った引用は禁止。
- 有料サービス・広告出稿・有料APIの契約を前提にしない。必要なら「要承認」と書く。
- 景品表示法（ステマ規制・PR表記・不当表示）、個人情報保護法、各ストアやSNSの規約に触れる点はリスクと対策を書く。
- 実在の人物・他社のロゴや画面を使わない。
- AIの判断は仮説であり、最終判断は人（オーナー）が行う。あなたは承認できない。
"""


def _j(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- ①企画部
IDEATION_REQUIRED = {"ideas": list}


def ideation_prompt(count, learning, past_titles, owner_assets):
    return f"""あなたは「企画部」です。AIとClaude Codeで1人でも作れて、収益化できそうなアプリ・Webサービスの案を{count}件考えます。
{COMMON_RULES}
# 進め方
1. Web検索で「お金を払ってでも解決したい困りごと」を探す。おすすめの探し先: アプリストアや比較サイトの低評価レビュー、Yahoo!知恵袋・Reddit・X の不満、求人や業務委託で繰り返し頼まれている作業、法改正・制度変更・新しい技術で生まれた需要。
2. 汎用の台帳・メモ・AIチャットの焼き直しは避け、業種・場面・帳票に絞る。無料の代わり（Excel・既存の無料アプリ）で足りるものは点数を下げる。
3. 「最初の100人にどう届けるか」を必ず書く。オーナーがすでに持っている発信の場（下記）に合う案は加点してよい。
4. 1つの案につき、困りごとの根拠を最低2件、実際のページの引用付きで集める。

# オーナーが持っている資産
{owner_assets}

# 過去の学び（却下・中止・実際の数字。ここから学ぶ）
{learning or "（まだなし）"}

# 過去に出した案（同じ案・言い換えは出さない）
{chr(10).join("- " + t for t in past_titles) or "（なし）"}

# 答えの形
最後に次の JSON を ```json で囲んで出す。scores は1〜5の整数。
{_j({"ideas": [{
    "title": "短い名前", "one_liner": "一言の説明", "target_user": "使う人（業種・立場まで具体的に）",
    "payer": "お金を払う人", "pain": "困りごと", "evidence": [{"url": "https://...", "quote": "ページの文の引用", "checked": "2026-11-11"}],
    "solution": "何をどう解決するか", "monetization": "収益の取り方（月額・買い切り・成果報酬・広告など）",
    "price_hypothesis": "価格の仮説", "free_alternatives": "無料の代わりと、それでも払う理由",
    "first_100_users": "最初の100人への届け方", "why_now": "なぜ今か",
    "build_scope": "最初に作る範囲（2週間以内）",
    "scores": {"pain": 3, "willingness_to_pay": 3, "reach": 3, "buildability": 3, "timing": 3}
}]})}
"""


# ---------------------------------------------------------------- ②市場・競合部
MARKET_REQUIRED = {"competitors": list, "differentiation": list, "win_probability": (int, float),
                   "growth_outlook": str, "verdict": str, "reason": str}


def market_prompt(idea):
    return f"""あなたは「市場・競合部」です。企画部とは別の立場で、この案が「勝てるか」「これから伸びるか」を判断します。企画部の言い分をうのみにしないでください。
{COMMON_RULES}
# 対象の案
{_j(idea)}

# 進め方
1. 同じ・似たアプリやサービスを最低5件探す（国内を優先、海外の有力なものも）。料金ページ・機能・レビューを実際に開いて確かめる。
2. 利用者の不満（低評価レビュー・口コミ）を引用付きで集める。そこに差別化の余地があるか。
3. 市場がこれから伸びるか（検索の動き・制度・技術・ニュース）。根拠のない「成長市場」は書かない。
4. 1人＋AIで作る小さな製品が、大手や無料の代わりに勝てる具体的な理由があるか。なければ NO_GO。

# 答えの形（```json で囲む）
{_j({
    "competitors": [{"name": "", "url": "", "price": "確認した料金（未確認なら未確認）", "strength": "", "weakness": "", "quote": "根拠の引用"}],
    "user_complaints": [{"url": "", "quote": ""}],
    "differentiation": ["勝てる具体的な違い"], "threats": ["負ける理由になりそうなこと"],
    "growth_outlook": "伸びる / 横ばい / 縮む（根拠つき）", "win_probability": 40,
    "verdict": "GO または NO_GO", "reason": "判断の理由（3〜5文）"
})}
"""


# ---------------------------------------------------------------- ③審査部
REVIEW_REQUIRED = {"verdict": str, "reason": str, "devils_advocate": list, "unit_economics": dict,
                   "mvp_scope": list, "kill_criteria": list, "validation": dict, "legal": list}


def review_prompt(idea, market):
    return f"""あなたは「審査部」です。反対の立場（悪魔の代弁者）から、この案を AI が作り始めてよいかを厳しく審査します。
PASS にすると、開発部がすぐに作り始めます。迷ったら FAIL にしてください。続けるかどうかの最終判断はオーナーが完成品を見て行います。
{COMMON_RULES}
# 案
{_j(idea)}
# 市場・競合部の報告
{_j(market)}

# 確かめること
1. 技術: Claude Code で2週間以内に、動く最初の版（Web/PWA）が作れるか。外部APIや審査が必要なものは何か。
2. 法律・規約: 関係する法律（景品表示法、特定商取引法、個人情報保護法、業法など）、ストア・決済・SNSの規約。
3. 採算: 価格・月の費用・月10万円に必要な有料利用者数。すべて仮説と明記。
4. 集客: 最初の100人を広告費0円で集める具体策があるか。
5. 作る前の需要検証: LP と事前登録で何日・何件集まれば合格か（現実的な数で）。
6. やめる基準: どうなったら撤退するか（期間と数字）。

# 答えの形（```json で囲む）
{_j({
    "devils_advocate": ["この案がうまくいかない理由"],
    "technical": {"feasible": True, "notes": "", "external_dependencies": []},
    "legal": [{"risk": "", "law_or_rule": "", "mitigation": ""}],
    "unit_economics": {"price": "", "monthly_cost": "", "needed_paying_users_for_100k_yen": "", "assumptions": ""},
    "acquisition": {"first_100_plan": "", "channels": []},
    "mvp_scope": ["最初の版に入れる機能"], "out_of_scope": ["入れないもの"],
    "validation": {"method": "LP＋事前登録など", "days": 14, "target_signups": 30, "success_metric": ""},
    "kill_criteria": ["撤退の基準"],
    "verdict": "PASS または FAIL", "conditions": ["PASS の条件・注意点"], "reason": "判断の理由"
})}
"""


# ---------------------------------------------------------------- ⑤開発部
BUILD_REQUIRED = {"stack": str, "how_to_run": str, "features_done": list, "not_done": list}


def build_prompt(spec_text, feedback="", signup_url=""):
    signup = signup_url or "未定。リンク先を \"#SIGNUP_URL\" にしておく"
    extra = f"\n# オーナーからの直してほしい点（最優先）\n{feedback}\n" if feedback else ""
    return f"""あなたは「開発部」です。この作業フォルダーに、SPEC.md の最初の版（MVP）を作ってください。
- 技術は任せる。迷ったら Vite + React + TypeScript の Web/PWA（スマホ幅でも使える）。サーバーが必要なら最小限に。
- 支払いが必要なら Stripe のテストモード前提で組み、キーは .env.example に名前だけ書く（本物のキーは入れない）。
- 主な流れの自動テストを書いて通す。README.md に動かし方（Windows で）を書く。
- 利用規約・プライバシーポリシーのひな形ページ（要確認と明記）を入れる。
- 収益化の形まで作る: 紹介ページ（誰の・何の困りごとを・どう解決するか）、料金ページ（価格は仮説と明記）、
  事前登録または問い合わせの入口（受け口のURL: {signup}）。
- `npm run build` などで、サーバーなしで開ける画面（dist/ など。index.html を含む）を出せるようにする。
  サーバーが必要な機能は、画面だけでも見られるように練習用のデータで動く形にし、「接続待ち」と書く。
- 作れなかったもの・外部接続が必要なものは「未完成」「接続待ち」と正直に書く。完成と偽らない。
{COMMON_RULES}{extra}
# 仕様（SPEC.md と同じ）
{spec_text}

# 答えの形（作業が終わったら ```json で囲む）
{_j({"stack": "", "how_to_run": "動かすコマンド", "static_dir": "サーバーなしで開ける画面のフォルダー（例: dist）",
     "features_done": [], "not_done": [], "tests": "テストの結果", "known_issues": []})}
"""


# ---------------------------------------------------------------- ⑥品質部
QA_REQUIRED = {"checks": list, "blocking_issues": list, "verdict": str}

QUALITY_BASELINE = """- 対象者が最初の画面で「何をすれば何が得られるか」が分かる
- 主な作業を最初から最後まで実際に操作できる（具体的な入力と正解の照合）
- PC幅1280px とスマホ幅390px で表示が崩れない・横にはみ出さない
- 保存→再読み込みでデータが残る（保存する製品の場合）
- 書き出し・復元がある場合は実ファイルで確かめる。不正な入力・不正なファイルで記録が壊れない
- 未接続の機能を使えるように書いていない。広告・アフィリエイトに PR 表記がある
- 利用規約・プライバシーポリシーのひな形がある
- 自動テストが通る"""


def qa_prompt(spec_text, build):
    return f"""あなたは「品質部」です。開発部とは別の立場で、この作業フォルダーの製品を検査します。開発部の自己申告をうのみにせず、実際にテストやビルドを動かして確かめてください。
コードは直さないでください（直すのは開発部）。結果を QA_REPORT.md に書きます。
{COMMON_RULES}
# 品質の基準（以前からの基準を引き継ぐ）
{QUALITY_BASELINE}
# 仕様
{spec_text}
# 開発部の報告
{_j(build)}

# 答えの形（```json で囲む）。result は「合格」「不合格」「未確認」のどれか。確かめられなかったものは未確認。
{_j({"checks": [{"item": "", "result": "合格", "evidence": "確かめた方法と結果"}],
     "blocking_issues": ["オーナーに見せる前に直すべき点"], "verdict": "レビュー可 または 要修正"})}
"""




# ---------------------------------------------------------------- ⑧SNS運用部
SNS_CHANNELS = ("Threads", "Instagram", "TikTok", "YouTube", "X", "note")
SNS_REQUIRED = {"posts": list}
SNS_PURPOSES = {
    "validate": "需要検証の告知。「開発中・事前登録受付中」と正直に書き、登録を呼びかける。2週間で4〜6本。",
    "launch": "公開後4週間の集客。役に立つ投稿を中心に、アプリの宣伝は控えめに。4週間で8本。",
    "weekly": "YouTube「のぼるの挑戦記」の軸。AIが今週考えた案・審査で落ちた理由・オーナーが却下した理由・作ったアプリ・売上（0円も正直に）を、見る人が参加したくなる形で伝える。今週分3〜4本。",
}


def sns_prompt(purpose, subject_text, owner_assets, sns_rules, existing_titles):
    return f"""あなたは「SNS運用部」です。今あるSNSアカウントを使って、投稿案を作ります。
投稿はすべて「承認待ち」で、オーナーがOKしたものだけを ChatGPT が画像・動画にして Metricool で予約します（今の流れのまま）。
{COMMON_RULES}
# 今回の目的
{SNS_PURPOSES[purpose]}
# SNSの決まり（今の運用から引き継ぐ）
{sns_rules}
# 使えるアカウント（今あるもの）
{owner_assets}
# 題材
{subject_text}
# 最近の投稿の題名（同じものを出さない）
{chr(10).join("- " + t for t in existing_titles[-30:]) or "（なし）"}

# 書き方
- channel は {" / ".join(SNS_CHANNELS)} のどれか。
- facts には「投稿で使ってよい事実」だけを書く（題材に書いてあることだけ）。angle や title に数字を入れるなら、その数字を facts にも入れる。
- text は投稿文の下書き。asset_brief は ChatGPT への画像・動画の指示（文字や数字は絵に描かせない）。

# 答えの形（```json で囲む）
{_j({"posts": [{"channel": "Threads", "title": "短い題名", "format": "型（例: 値段クイズ・作る過程・使い方30秒）",
                "angle": "切り口", "facts": ["使ってよい事実"], "text": "投稿文", "asset_brief": "画像・動画の指示",
                "week": 1}],
     "kpis": [{"name": "", "target_4w": "", "how_to_measure": ""}],
     "launch_checklist": ["公開前に必要なこと"]})}
"""


SNS_PURPOSES["affiliate"] = ("楽天アフィリエイトの商品紹介。すべての投稿の文頭に「PR」を入れる。価格は「取得日時点」と書く。"
                             "効果・効能の断定、ランキングや「最安」の主張、薬機法・健康増進法に触れる表現をしない。"
                             "売り込みより「選び方」「比べ方」「使う場面」が伝わる投稿にする。テーマごとに2〜3本。")


# ---------------------------------------------------------------- ⑩物販・アフィリエイト部
AFFILIATE_REQUIRED = {"themes": list}


def affiliate_prompt(owner_assets, learning, past_themes):
    return f"""あなたは「物販・アフィリエイト部」です。オーナーが今持っている SNS（YouTube・Threads・TikTok・Instagram など）を使い、
楽天アフィリエイトで商品を紹介して売れそうなテーマを3つ考えます。
{COMMON_RULES}
# 考え方
1. 今いる見る人（下の資産）に合うもの。例: お買い得物件チェッカーを見る人＝家を買う人・売る人 → 引っ越し・家具・防災・収納・住まいの手入れ。
   「のぼるの挑戦記」を見る人 → AI・副業・パソコン作業の道具。
2. 短い動画や画像1枚で良さが伝わり、比べ方を教えられるもの（例: 「〇〇の選び方3つ」「買う前に測るところ」）。
3. Web検索で、今の季節・行事・話題（引っ越しシーズン、年末、防災の日など）と需要の根拠を引用付きで集める。
4. 報酬率は推測しない（楽天の料率ページやショップの設定で確かめるまで「未確認」）。
5. 避けるもの: 健康食品・化粧品・医薬品の効果の訴求、金融商品、成人向け、転売品が多いもの、根拠のない「最安」。

# オーナーの資産
{owner_assets}
# 過去の学び
{learning or "（なし）"}
# 過去のテーマ（同じものを出さない）
{chr(10).join("- " + t for t in past_themes[-30:]) or "（なし）"}

# 答えの形（```json で囲む）
{_j({"themes": [{"title": "テーマ名", "audience": "誰に", "why_sells": "売れそうな理由（根拠の引用つき）",
                 "evidence": [{"url": "", "quote": ""}], "search_keywords": ["楽天で探すキーワード"],
                 "channels": ["YouTube", "Threads"], "format": "投稿の型", "season": "時期",
                 "risks": ["規約・法律の注意"]}]})}
"""
