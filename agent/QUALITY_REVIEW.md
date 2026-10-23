# 2026.10.22.10 製品改善と確認の基準

HTMLの静的検査、汎用ブラウザ操作検査、生成AIによるコード採点だけでは、ユーザーの確認待ちには進めません。対象者と使い方、主要作業、PC画面、390px幅画面、保存と再読込、CSV・JSON復元、不正入力、必要な接続を制作側で検証した記録が必要です。記録はHTMLのSHA256と要件のSHA256に結び付け、内容や要件が変われば無効になります。制作側の検証とユーザーの発信OKは別で、SNS・本公開には引き続き該当版へのユーザーOKが必要です。

## 今回作り直したもの

- ClassNote：個人講師・小規模スクール向け。名簿、授業、5種類の出欠、集計と出席率、保存、CSV、JSONバックアップと復元。Zoomの自動取得・複数端末共有はありません。
- Workday：在宅勤務・フリーランスの個人向け。日別の働ける時間、作業見積り、超過表示、優先度と状態、予定日変更、作業実績、差分、保存、CSV、JSON復元。勤務監視・チーム同期はありません。

改善候補は `agent/product-candidates.json` に記録したコミットとSHA256で取り込みます。既存の試作品・履歴は保持し、`projects/` の公開版は変更しません。独自の修正依頼が残っている場合は消さず、照合・追加修正が必要な開発途中版として取り込みます。AIまたはユーザーが中止・保留した案は通常の開発から外し、理由・履歴は残します。ユーザーの明示的な継続指定で再開できます。

## 確認したこと

- 78件のPython検証：版と要件の変更による検証無効化、自己採点では発信不可、AIの中止、取り込みの改変検出・重複防止・再開・修正依頼の保持、既存更新・プレビュー・継続判断を含む。
- Streamlit画面テスト：新バージョン、2件の改善版リンク、発信OKのフォーム、通常一覧から中止案が外れること、画面例外がないこと。
- Chrome実操作：出欠の登録・集計・保存と再表示、勤務可能150分・見積180分・実績45分の差分、CSV実ファイル、最新版でのJSON復元。PCおよび390px幅の画面を目視。
- DOM操作テスト：出力からJSON復元、復元キャンセル、不正バックアップ拒否、重複、日付切替、数値検証、HTMLを実行しない表示、CSV式の保護、壊れた保存記録の保護。

スマホ実機・iOS・実利用者の評価・収益性は別途検証します。旅行アプリの実経路・周辺施設検索、共同編集は未完成であり、完成候補にはしていません。

## 自動化の範囲

継続運転はAIの事業選別、設計、コード生成と修正、コード検査を継続します。Ollamaのコード採点は実画面を目視した証拠になりません。制作側の実操作・見た目検証が未完了の版は、その状態を表示して確認候補から分けます。今回の2件はCodexで実操作を検証した候補です。新しく生成されるすべての製品について、同じ視覚検証が自動で完了する仕組みまでは実装していません。

DOM検証スクリプトは `agent/review-products/verify-products.cjs`。Node.jsとjsdomを用意して同ディレクトリで実行します。これはブラウザの目視検証を代替しません。


## 2026.10.23.2 分野別の開発・経験参照基盤

- 分野は不動産、業務効率・事業者向け、学習・教育、旅行・暮らし、家族・健康、動画・コンテンツ、その他。自動分類はユーザーが変更でき、その指定を再起動で上書きしません。名称と管理IDの対応はSQLiteの `venture_projects` と出力先の `project-index.json` で管理します。
- 新しい成果物は `venture_outputs/sectors/<分野>/projects/<管理ID>/` 内の `01_plans`、`02_builds`、`03_marketing`、`04_reviews`、`05_notes` に保存。既存ファイルは移動・削除せず、DBに保存済みのパスで参照し続けます。共通レポートと動画の草稿は `shared` に分離します。
- 全アプリの品質基準を `knowledge/common/quality-baseline.json` に、実測事例の索引を `knowledge/<分野>/measured-index.json` に分離。個別開発のプロンプトと経験による企画補正は該当分野を参照し、他分野の効果をそのアプリの実績と混同しません。実測がなければ未測定です。
- 同一の判断材料は評価結果を再利用。反応、売上、観察期間、要件、事業仮説、集客状況、設定や日付が変われば再評価します。同じ実測を繰り返し読み直しても新しい学習事例にはしません。頻出するDB照会には索引を追加しました。
- 整理や高速化を理由に、対象者、使いやすさ、用途に合うデザイン、実用的な機能、制作側の実操作・見た目検証、ユーザーによる版ごとの発信OKを省略しません。初回に何をすれば何が得られるかを示す設計条件もプロンプトに明記します。
- 収益化の次段階は製品検証、実利用、具体的な価格・支払意思、売上と費用・返金の確認を区別して表示します。利益や成功を保証する判断ではありません。

検証：既存の品質・更新・継続判断を含む85件のテストが合格。新しい分野の振り分け、ユーザー指定の保持、旧成果物の読み出し、評価の再利用と失効、分野ごとの知識参照、品質条件と変更依頼の保持を確認。Streamlit画面テストで分野絞り込み・改善版リンク・変更依頼の保存を確認しました。

高速化の対象は重複する評価と参照作業です。ローカルAIのモデル本体を再訓練する機能ではなく、生成時間が何倍になるという測定結果もありません。見た目の制作側検証がすべて自動完了する仕組みは、引き続き未実装です。


## 2026.10.23.3 自動操作・画像検証と競合比較

この版以降の自動検証は、生成コードの自己採点の後に、独立したChromiumで実操作と画面画像を検査します。ブラウザだけで完結する製品が対象です。検索API・共同保存が必要な製品の未接続部分を、単一HTMLで完成したとは扱いません。

- PC幅1280pxとスマホ幅390pxで、仕様から作った具体的な入力・正解の照合、入力差分、保存後の再読込、CSV実ファイルの値、JSON取得→データ変更→復元キャンセル→再選択と復元、不正入力・不正JSONで保存が変わらないことを実行。横はみ出し、文字と操作部品の寸法、JavaScriptエラーも検査します。
- 4枚の初期・結果画面を画像入力対応のOllamaモデルに送り、対象者、デザイン、読みやすさ、スマホ操作、実用的な結果表示を検査。コード採点やスクリーンショットの存在だけでは画像判定を代用しません。既定は qwen2.5vl:3b。初回はPlaywright・Chromium・画像モデルを自動準備します。サイドバーで自動準備のON/OFFとモデル名を設定できます。
- 操作失敗・画面不足は修正理由として次の生成へ返します。検証環境の不足・計画の不正・モデル接続失敗は準備や再試行と表示し、需要不足・中止と区別します。以前の「制作側検証待ち」も既存HTMLを再利用して自動検証へ進めます。合格した確認版は保持します。
- 検証記録はHTML・仕様・JSONレポート・4枚の画像のSHA256に結び付きます。内容や要件・記録が変われば再確認。運転停止・中止・要件変更を検出した場合は合格にしません。同じHTMLを再検証するときは候補ファイルを重複追加しません。
- 全分野共通で、同じ対象者の同じ作業を競合・代替と比較する基準を開発・コード検査に渡します。自動検証前に固定の公式参照候補から本文を取得し、引用一致を検証した比較設計を保存します。直接競合が不足する場合は調査不足と明示します。本文取得日は記録し、比較設計は7日で再調査します。
- 比較設計には対象者の作業、選ぶ理由の仮説、その機能の完成条件、同じ作業の入力条件、完了率・時間・迷い・ミス・再利用意向の測り方、継続・見直し条件を含めます。公式本文は機能の根拠であり、実測の優位性を証明しません。未記載の機能が存在しないとも断定しません。「使いたい」反応や競合より良いという結果は実利用で別に確かめます。
- 旅行はNicody、Wanderlog、tabioriを比較先候補とし、同行者のペースと休憩・帰宅時刻、予約を維持した雨・遅延時の再計画、幹事の合意形成の手間を改善仮説とします。これらが独自・優位だと実証されたわけではありません。旅行の検索・共同編集は引き続き未完成です。

検証：既存を含む106件のPythonテストが合格。Chromiumで授業管理・在宅ワーク管理のPC/スマホ各5シナリオを実行し、最終変更後も自動検証関連21件を再実行して合格。期待値の不一致で合格にならないこと、低い画像スコアが修正へ戻ること、停止中に合格しないこと、実画像バイトをAPIへ送る構造、引用不一致の拒否、レポート・画像改変時の失効、従来の検証待ちの再開を確認。Streamlitで表示版・分類・改善版リンク・変更依頼を確認しました。

画像モデルの応答と接続はテストで模擬しています。この環境ではOllama実モデルによる画像推論とWindowsでの初回自動取得を実行していません。ユーザーPCでの初回運転時に確認します。画像モデルの採点は品質保証や利用者評価の代わりではなく、粗い試作を修正へ戻すための検査です。実利用・競合に対する優位性・収益性・iOS実機の検証は別です。


## 2026.10.23.4 確認一覧の絞り込みと開発枠の自動拡張

- 通常の確認一覧・アプリカードは、実操作等の品質検証がある確認候補とOK済み運用版だけ。制作途中、一次選別待ち、AI・ユーザーの中止保留は通常一覧から外します。「開発途中・選別待ち・中止保留の履歴も見る」と状態フィルターで任意に参照できます。途中版への修正依頼後は検証が失効し、通常の確認候補から外れます。
- AIが中止保留した案は追加開発から除外し、理由・ファイルは履歴として保持。古い中止保留案について、反応の入力画面を開いて評価用の初期行が作られた際に、既存判断が既定の育成状態へ上書きされる問題を修正しました。明示的なユーザー継続指定は優先します。
- 開発枠の目安を12件以上へ変更し、旧設定が4件でも固定上限で新候補の開始を拒みません。目安を超えたときも調査・選別を通った候補は1件ずつ着手できます。確認待ち・公開済み・接続準備や検証環境の待機は枠から外します。既存の改善巡回、探索の間隔、選別基準、無課金の設定、版ごとの発信OKは維持します。無制限に同時実行する処理ではなく順番に処理します。

検証：表示・枠・中止判断・要件保持・品質ゲート・継続処理を含む73件のテストが合格。画面テストで通常一覧から中止案が外れ、履歴ONで戻ること、品質検証済みの改善版だけがリンクされること、変更依頼後の検証失効と一覧からの除外を確認しました。ユーザーPCへの適用と実運転は未確認です。


## 2026.10.23.5 局所修正・検査通過版の保持・旅行APIの接続版

- 既存HTMLを毎回全文生成する方式から、現在のコードに一意に一致するold/newの局所修正へ変更。最大8箇所、曖昧な一致・無変更・大幅な削除は拒否し、元の候補を保持します。モデルが出した修正案はデータとして適用し、任意のコマンドとして実行しません。
- 確認済み版や制作検査通過版を別に保持。既存のID、保存・CSV・JSON機能を消す変更を拒否します。これは完全な回帰検証の代替ではなく、新しい版は従来どおり実操作・画像検証が必要です。ユーザー要件が変わっても過去の動く版は修正の土台に使いますが、新要件への合格を付与しません。
- 同一エラー2回で全て打ち切る処理を廃止。原因と変更箇所を再診断し、検査通過版があれば戻して別の局所修正を試します。無効な差分も次回の再診断へ渡します。1サイクルの回数制限と停止指示を保ち、修正中は3時間ではなく3分以降に次の巡回で再試行します。他のアプリも巡回します。
- 不合格理由は試作品だけでなく品質改善候補・自動検査レポートからも参照。大きなHTMLは先頭24,000文字だけを切る処理をやめ、エラーの参照語・スクリプト・保存などの関連部分を位置付きで渡します。文字AIのコンテキストを明示的に16,384に設定します。新規作成の出力枠は9,000トークンです。実際の速度・推論能力はローカルのPCとモデルに依存します。
- 競合調査は内部判断用で、アプリに他社比較ボタンや架空の比較機能を新設しない旨を生成・修正指示に明記しました。
- 旅行の接続版を `agent/review-products/travel.html`、APIを `functions/api/travel/[[path]].js`、D1スキーマを `schema/travel.sql` に実装。開発アプリ内に接続版へのリンクとAPIキー・D1・環境変数の設定パネルを追加。
- 旅行はGeoapifyの場所・周辺施設検索、徒歩/車の経路APIに接続するコードを準備。秘密キーはサーバー側のみ。回数上限をD1で管理します。移動、滞在、休憩、ゆっくり歩く余裕、予約時刻との衝突、終了目標を計算。保存・CSV/JSONと、閲覧/編集の招待を分けた共同保存、バージョン競合時の編集保持を実装しました。APIや共同保存は環境変数を設定するまで有効になりません。

検証：既存を含むPython140件の検証が合格。局所置換の一意性、既存機能の削除拒否、同一エラー時の再診断、無効差分の元コード保持、チェックポイントと発信OKの分離、短い再試行を含みます。画面テストで表示版.5、旅行接続パネル、既存確認版リンク、変更依頼を確認。旅行のNode API検証、PC1280px/スマホ390pxのブラウザ操作、実SQLiteを使った2ブラウザ共同編集・409時の入力保持、閲覧専用、保存再読込、CSV、JSON復元・キャンセル・不正ファイルを確認。日本語フォントを用いて初期画面と操作結果の配置を目視しました。

旅行の外部検索はテスト用のプロバイダー応答で検証しており、実APIキーの取得・日本の検索精度・本番D1の実動作は未確認です。ユーザーが無料APIキーを取得し、CloudflareへSecretと環境変数・検索回数テーブルを設定してから実データで確認します。具体手順は `agent/TRAVEL_CONNECTIONS.md`。電車・バスの時刻表、施設営業時間の自動確認、天候・交通の実況、希望投票などは未対応で、旅行の元の完成条件全体を通過したとは扱いません。発信OK、実利用の優位性、収益性も未確認です。

ローカルOllama実モデルで全アプリが完成まで到達することは実証していません。今回変更したのは不具合を直す処理と具体的な旅行接続版であり、完成の保証ではありません。


## 2026.10.24.1 — common product design standard and connection follow-up

This release changes the autonomous system itself, not only the manually refined travel UI.

- All product specifications now carry the user-requested minimum quality: clear audience/value/start action, task-specific visual design, readable hierarchy, mobile input, useful result and recovery. The 2026-10-24 travel journal is a quality reference, not a mandatory style template.
- Before building or repairing, collect a cached competitor brief. At least two distinct actual official text sources must back design patterns, adaptations, concrete improvements and acceptance actions. Generated quotes must match retrieved text. Work-time, classroom and data-cleanup tasks have relevant official reference candidates in addition to sector defaults.
- The research currently reads a bounded known official reference list. It does not perform unlimited competitor discovery, sign into other products, operate their apps, or capture competitor screenshots. Official-text design inferences are labelled as such. Direct-competitor and missing-information gaps remain explicit; measured superiority is never inferred from these sources.
- Feed design principles and connection progress to initial generation and incremental repairs. A design repair can change composition, color and hierarchy while preserving functional IDs, data and other working features. A research failure permits independent development but cannot grant owner-review readiness.
- Tighten source critique and actual PC/mobile image review. Invalidate old quality policies and old-baseline imported candidate proofs rather than automatically treating them as current. No self-score or connection note grants publication permission.
- Travel scope includes a unified destination/transport/along-route and destination attractions/food flow, reasons and route detour time, complete schedule recalculation, reservations, rest/end warnings, shared mobile itinerary and data recovery. Transit is a separate real data dependency. These are requirements, not a claim that the live travel app implements them all.
- Dashboard top displays active apps with declared API/server dependencies, current follow-up status and next action. Stopped/held apps are filtered out. Travel includes Geoapify/Cloudflare links and a health-reading button. A configured health response is not a successful search or shared-edit test. Users can record follow-up/evidence; requirement changes require recheck while preserving prior notes. Unknown providers remain developer research, not an instruction for the user to register somewhere.
- This is workflow enforcement, not proof that a local model will autonomously reach the desired quality on every product. Actual Windows/Ollama generation and its results remain to be observed. Connected backend functions and credentials still require implementation and real integration tests; the static HTML builder cannot complete arbitrary backend services by itself. Live Geoapify search remains a known separate connection issue.

Validation: hash/syntax/backups/rollback and quality/proof regression tests, real Chromium product operation tests, plus Streamlit dashboard smoke checks with an active connected travel app. AI visual assessments and model responses use fixtures in the tests; no claim of actual local model quality. Portable focused regression tests: `python -m unittest discover -s agent/tests -p test_system_baseline.py` (requires Streamlit).


## 2026.10.24.2 — make a usable product before the owner's monetization decision

User clarification: API credentials/connections may require the owner's setup. The requested baseline is autonomous competitor-informed design, useful core functionality, understandable workflows, design refinement and verification, followed by the owner's monetization decision on an actual product. It is not a requirement to automate every external account setup or guarantee every business succeeds.

Implementation:
- Add a cached product blueprint before generation and incremental repair. It specifies the user's scene, first action, use-reason hypothesis, task-specific visual direction, screen sections with actions/results, concrete core flows covering every acceptance condition, and implementations/improvements linked to at least two retrieved comparison sources. A missing coverage or invented comparison source is rejected.
- Bind the blueprint to requirements and competitor research revision. A new owner request invalidates it. Feed it to the builder before the long generic instructions and to incremental repair prompts. Automatic final proof now also requires this blueprint, actual full browser workflows and visual checks.
- Fix a gap in connected drafts: they previously skipped all visual quality inspection. Now inspect actual 1280px and 390px initial screens and pass images to the vision judge; deficient layouts/visuals return to repair within the revision budget. No fixture APIs or fake successful searches are supplied. These initial-screen reports never grant functional completion, owner-review readiness, profitability proof or publication permission.
- Retry unfinished connected-screen development after 180 seconds instead of the previous 1800-second backoff. This is retry eligibility, not a guaranteed completion time or parallel execution promise. Environment readiness and initial downloads may still take time.
- Show up to three recent development/inspection entries separately from the verified-app gallery. Attach scene, things to try, competitor adaptations, differentiation, monetization and acquisition hypotheses to verified candidates so the owner can assess a concrete app. User interest, superiority, willingness to pay and actual profit remain unmeasured until tested.
- Travel requirements now explicitly separate origin/destination target arrival date/time from day-end time, allow activity interests including hiking/fishing/entertainment, require feasible detour/activity/rest calculations, interest-matched route/destination suggestions, source-backed popularity claims, shared itinerary and recovery. Unknown timings cannot be labelled feasible. These requirements are not a claim that the live travel UI already implements those features.

Validation: 156-test regression suite passed, including actual Chromium desktop/mobile core workflows and a new connected-screen screenshot path; 38 portable regression cases (including inherited baseline tests) passed. The populated Streamlit .2 dashboard rendered progress and API follow-up without exceptions. Model generation and vision scores are fixtures in automated tests; the actual Windows/Ollama system producing the desired quality remains to be observed. Comparison sources remain the bounded official reference catalogue described above; competitor live-app operation/screenshots are not automated here. Full API-dependent functional completion still needs real integration checks. The production Geoapify transport error was separately fixed in a5cbea0478871d3ab528e6533c0aecdfc66d7ae2 with live search/food/walking-route verification recorded in TRAVEL_CONNECTIONS.md.


## 2026.10.24.3 — simplify development visibility and open the actual saved page

- The default dashboard shows the app, declared outcome, latest development stage/current work, continuation judgement with measured-evidence status, recorded problem and next improvement together. These values come from the local database; cycle counts are moved to advanced details and never stand in for product progress. The board refreshes every 20 seconds.
- Select an app and use one prominent button to open its latest existing saved HTML, including unfinished drafts. Missing newest files fall back to an existing saved version. The save date and unfinished/old-prototype labels remain explicit; viewing a draft never grants quality acceptance or publication permission.
- Stopped/held apps are removed from the active list and retained in a collapsed table with reasons and reopening conditions. Explicit owner continuation still overrides an AI stop. No records/files are deleted.
- API requirements, connection state and next operation appear below the same board. Pending and confirmed apps both remain in this inventory, with pending first. Unknown providers remain development research, not a demand for the user to create an account. No declared dependency means no known API requirement, not proof that every app works without an API.
- Historical galleries, eight operational tabs, counters and long settings are lazy opt-in advanced controls. Existing operation, configuration, SNS approval and change-request functions are preserved. No product-quality policies are weakened and this release does not itself polish the generated products.

Validation: 50 portable regression cases (including inherited baseline cases) and 34 existing preview/visibility/screening tests passed. A populated Streamlit AppTest verified the default has no operational tabs or model settings, required status/problem/improvement columns, both pending and confirmed API rows, archived stop reasons, all eight tabs and settings when opened, no widget exceptions, and an actual localhost preview serving the selected saved HTML without creating release approval. Reproduce the UI check with `python agent/tests/check_dashboard.py` (requires Streamlit). Actual Windows runtime data and local model progress are not available in this development environment; the board displays those after the user's normal update/restart.


## 2026.10.24.4 — recover structured model answers that blocked planning

The user's running dashboard showed ten displayed products in design/repair waiting with JSONDecodeError (Extra data or Expecting value). This is evidence of blocked planning, not evidence of product polish or lack of demand. The local model's raw answers and current database are not accessible here.

- Product-spec generation previously used json.loads on the whole response with only a narrow code-fence strip. Replace this with the common structured-response path, also used for competitor briefs, blueprints, source critique, browser-test plans and incremental edits. Request Ollama JSON mode only for these calls; HTML/prose calls keep their existing format. The per-call flag does not persist or mutate the saved settings.
- Read one complete object despite leading/trailing prose, code fences or a completed leading thinking block. Preserve nested structures and quoted braces. Do not salvage partial nested objects from truncated JSON, guess missing fields, merge candidates or accept duplicate keys/non-JSON numeric constants.
- Retry malformed responses once with the original requirements, an explicit single-object instruction and a bounded larger output budget. Missing fields and all existing product/spec/quality validators still reject inadequate plans. Persistent failures remain retries, never owner-ready or public. Existing design-wait rows use the existing development retry path; no data reset is required.
- Explain response-format failures in the dashboard as a development blocker with the next repair action, rather than displaying them as a market verdict. Bump display version only; quality gates and release approval remain unchanged.

Validation: 57 portable baseline/structured-response tests passed; 74 continuation, automatic-QA (including Chromium workflows), incremental-repair and production-gate regressions passed. Streamlit AppTest rendered the .4 dashboard, pending/confirmed connection inventory, archive reasons, advanced settings and actual saved-page preview without creating approval. Model outputs in these tests are fixtures; recovery on the user's actual Windows/Ollama responses and subsequent product completion must be confirmed after update. This patch does not claim the affected apps are now complete.


## 2026.10.24.5 — resume recorded pre-HTML work and expose planning failures

The user supplied completed cycles #1262/#1263 containing only the start and no-new-candidates messages. These show scheduling but do not prove successful development or identify the failing app. An exception in ensure_product_spec occurred before the development-start event, then was written only to product_development_state and silently returned. This could produce exactly that sparse job history; it is not proof that the same error occurred in those particular cycles.

- Log the selected app before spec generation/loading and log planning/repair exception class and message in the same job history, while preserving the retry state and quality gates.
- Include apps with a persisted development record even if their HTML-attempt counter is zero. Previously that queue excluded them despite the dashboard showing their development state. Bare untouched candidates are still excluded; owner/AI stop/hold decisions and explicit continuation retain existing behavior.
- Put the executing release version into the cycle-start record, tied to the dashboard version constant. Clarify that no-new-candidates means no new opportunity, not that existing product development succeeded or SNS posting occurred.

Validation: 59 portable tests passed, including real job-history records for a planning failure and resumption of a saved zero-HTML-attempt development row without granting product approval. 32 continuation/screening/owner-decision regressions passed. Populated Streamlit AppTest for version .5, actual saved-page preview, API inventory, archive and advanced controls passed. No access to the user's Windows database or Ollama runtime; actual successful design/build remains to be confirmed from a subsequent version-tagged cycle.


## 2026.10.24.6 — repair incomplete product specifications before building

Actual .5 cycles #1267–#1269 selected different products, parsed a model answer, then failed product-spec validation because workflow, must_have or acceptance was not a list of at least three nonempty strings. No prototype generation was reached. The earlier formatting retry did not cover semantic/schema validation; .5 only made this failure visible.

- Extract pure product-spec validation from persistence. Report which field is absent, has the wrong type, contains invalid entries or has fewer than three items. Keep the same requirements and connected-mode protection; also require dependency entries to be nonempty strings. Invalid specs are never persisted.
- Provide the required product JSON Schema in both the local Ollama format parameter and the prompt (required keys, string/list types, minItems=3, mode enum). This follows https://docs.ollama.com/capabilities/structured-outputs; it is a per-request setting, not a saved user config change. Generic text/HTML generation still has no structured format, and other JSON tasks keep JSON mode.
- Run the pure validator within the structured-generation loop. Return actual errors and the previous parsed object to the model along with the original app requirements and schema. Allow at most three total calls for validated product-spec generation; no automatic list padding, fabricated requirements, lowered acceptance criteria or fake quality approval. Save only a valid spec, then continue to the existing research/build/QA path in that same cycle. Persistently inadequate designs remain explicit retries.

Validation: 63 portable baseline/structured-response tests passed, including missing/wrong-type lists, actual error feedback, required schema transport, bounded repeated failure with no stored spec, and repaired spec reaching a mocked build in the same development cycle without granting quality acceptance. 54 continuation/screening/production-gate/owner-decision tests passed. Populated .6 Streamlit UI check passed. These model/build responses are test fixtures; actual Windows/Ollama design repair and a usable completed product have not been demonstrated by these tests. The supplied cycle logs remain the source of truth for local progress after update.


## 2026.10.24.7 — keep layout failures in the repair loop and validate proposed edits

Actual .6 cycle #1270 passed product-spec generation, applied a code edit, downloaded the vision model and reached a real 1280px layout check. The small controls inputValue/calculate caused a ValueError which escaped the partial-build loop, skipping remaining revisions. It did not reach the subsequent vision-image evaluation. Competitor quote verification also remained incomplete. Cycle #1271 executed three revision attempts but retained a JavaScript error and produced invalid edit anchors/formats; its unconditional connected-work summary misleadingly said the app was improved.

- Catch product-layout ValueError within the partial-build loop and feed the measured defect into subsequent revisions. Environment/network/invalid vision-response failures keep their separate preparation/retry path. Do not lower control-size/overflow/text checks, invent API responses, or turn a connected draft into owner-ready approval.
- Validate a proposed literal edit against the exact current source inside the bounded structured-response loop. Return failed anchor counts/format errors to the model with the original code/problem and retry, instead of immediately consuming another full build revision. Enforce edit objects, 1–8 edits, unique literal anchors, length/removal checks and preservation of unchanged source on invalid proposals. Preserve the unresolved browser failure in later edit-error notes rather than replacing it with only a patch-format error.
- Validate complete competitor comparison content inside the same bounded model-feedback mechanism: quotes must still exactly match one of the actually retrieved sources and both comparisons/design references remain required. Mismatched quotes receive source-specific feedback; persistent invented evidence is not cached. This is not automated real competitor-app operation or proof of superiority.
- Connected-development job summaries now distinguish layout checks passed/API functions unverified from improvement still incomplete. Failed edits no longer produce a successful-improvement claim.

Validation: 68 portable baseline/structured-response cases and 36 incremental/continuation/screening regressions passed. A separate real Chromium integration test detected 20px controls, returned the smallControls defect into a second repair, accepted the resulting 44px controls at desktop/mobile widths and kept the draft unapproved. Model code edits and visual scoring use fixtures; this does not prove the Windows model can generate the right repairs. Streamlit .7 UI/inventory/preview check passed. Actual apps in #1270/#1271 remain unfinished; the release improves recovery and truthful reporting, not their completed-product status.


## 2026.10.24.8 — diagnose actual uploaded stubs and stop preserving an unusable foundation

The supplied 02359_html.html is a one-field doubling sample under a customer-engagement title. With numeric inputs 12/87 it returns 24/174; the smoke test's text inputs both return NaN. Its special-case branch also assigns to a const. The supplied 02361_html.html contains orphan HTML tags inside JavaScript (Unexpected token '<'); after correcting that syntax in an isolated test copy, CSV export assigns repeatedly to a const and throws. These files are not usable business products. Their originals are retained as regression fixtures; no corrected stub is presented as a finished service.

Changes to the autonomous system:
- Identify the specific known generic inputValue/入力値/parseInt-or-Number-times-2 legacy pattern when doubling is not the requested product purpose. Retain the old source, bypass small edits to that unapproved foundation, and generate a new candidate from the actual product requirements. Explicit doubling/learning tools are exempt from this narrow detector. The same stub is rejected if regenerated; this is not a comprehensive semantic product-quality classifier. Existing release/QA gates still apply.
- After repeated unsuccessful literal patches and with no checked checkpoint available, switch to generating a separate new candidate within the remaining revision budget or on the next cycle. Never delete old assets or bypass final verification. A checked checkpoint continues to protect useful existing code.
- Supply deterministic bounded exact-text excerpts from retrieved references with IDs. The model selects source_ref; the program resolves its exact text/URL and then runs the existing quote, two-source and design-validation checks. Unknown IDs or mismatched URLs are rejected. Older explicit-quote responses still undergo exact verification. Excerpt selection is bounded sampling, not exhaustive competitor research or evidence of measured superiority.
- Fix smoke-test inputs: honor numeric min/max/step, fill required date/time fields and select/checkbox/radio controls. Previously priority 1..5 received 12 and required date stayed empty, which could wrongly label a valid submit as nonresponsive. The smoke check remains limited and does not replace the specification-driven full workflow tests. Report result NaN/Infinity as invalid numeric handling, rather than diagnosing it as fixed text.

Validation: 74 portable baseline/structured-response cases and 36 incremental/continuation/screening regressions passed. Actual Chromium reproduced both supplied failures, the special-branch const error and the CSV const error in a syntax-corrected in-memory control copy. A control copy with those two project-code errors corrected passed bounded-number/date smoke interaction; this is test evidence, not a production app release. Valid and invented reference IDs, repeated-edit strategy switching, legacy-stub rejection, explicit doubling exemption, old-file retention and no product approval were checked. The .8 Streamlit dashboard/inventory/preview check passed. Reproduce browser regression with `python agent/tests/check_legacy_products.py` after installing Streamlit, Playwright and Chromium. Actual Windows/Ollama generation of a useful replacement remains unproven; the next local generated candidate must be assessed on its actual functions and screen quality.
