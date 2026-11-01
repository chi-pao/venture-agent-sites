# お買い得物件チェッカーの引っ越し（ChatGPT Sites → GitHub + Cloudflare Pages）

決定: 2026-11-01 のぼるさん（案A）。目的: Claude Code がサイトの修正・テスト・公開を直接行えるようにする。

## 現在の状態
| 項目 | 状態 |
|---|---|
| 公開中の本番 | https://okaidoku-checker.rightharp65.chatgpt.site/ （変更していない） |
| コピー | `checker-site/`（`tools/mirror_site.py` を GitHub Actions で実行して取得。一覧と sha256 は `checker-site/MIRROR_REPORT.md`） |
| モデル | 6ファイルすべて `models/catalog.json` の bytes・sha256 と一致 |
| 動作確認 | 実Chromium（PC 1280px・スマホ 390px）で入力例→査定: 参考査定価格・判定・価格差・PR表記の表示、JavaScriptエラー0件（`tests/test_checker_site.py`、CIで常時実行） |
| 試験公開 | Cloudflare Pages のブランチプレビュー `…venture-agent-sites.pages.dev/checker-site/`（本番URLとは別） |

## 分かったこと（コードで確認）
- 査定（Web Worker）とスクショの文字読み取り（Tesseract）はブラウザ内で実行。入力内容・画像を外部に送る処理はない。外部への送信は Metricool の閲覧計測だけ。
- 中古戸建てモデルの更新は `learning.mjs` が `https://raw.githubusercontent.com/chi-pao/-/main/` の `site-models/manifest.json` を読んで取り込む。chi-pao/- の自動学習が本番に影響する。
- 広告は A8.net のリンク3本。

## 切り替え時に必ず変えるもの（チェックリスト）
- [x] 公開URLの方針（2026-11-01 のぼるさん決定）: **当面は無料URL**（Cloudflare Pages）。収益化の見込みが立った時点で専用ドメイン（年1,500〜4,000円程度）を取得し、そちらへ移す。専用ドメインへの移行時は、この下の項目（canonical・計測・提携先URL）をもう一度行う。
- [ ] 無料URLの形を決める: `venture-agent-sites.pages.dev/checker-site/`（設定不要）か、専用プロジェクト `okaidoku-checker.pages.dev`（Cloudflareで5分程度の設定が必要。URLが短く、事業開発AI側と分かれる）。
- [ ] `index.html` の canonical・og:url・構造化データ（`#website`・`#app`）・OGP画像のURL（`social/launch-20261021.png` は未取得）を新URLに変更。
- [ ] `analytics.mjs` の計測対象ホスト、`app.mjs` の共有用URLを新URLに変更（このままでは新URLで計測・共有が旧URLを指す）。
- [ ] `index.html` 末尾の旧ホスト専用スクリプト（`/cdn-cgi/challenge-platform/...`）を削除。
- [ ] Metricool・A8.net・Instagram プロフィールのURLを新URLに変更（のぼるさん）。A8.net は掲載サイトURLの変更・追加が必要な場合がある。
- [ ] 旧URLから新URLへの案内（ChatGPT Sites 側にリンクを1行追加する依頼書を作る）。
- [ ] 切り替え後、新旧で同じ入力の査定結果が一致することを確認。

## 切り替えまでの扱い
- 本番は旧URLのまま。改修は `checker-site/` で行い、テストとプレビューで確認してから切り替える。
- ChatGPT Sites 側を修正した場合は、`mirror-checker-site` を再実行してコピーを更新する（差分は MIRROR_REPORT の sha256 で分かる）。
