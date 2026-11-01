# お買い得物件チェッカーの引っ越し（ChatGPT Sites → GitHub + Cloudflare Pages）

決定: 2026-11-01 のぼるさん（案A）。目的: Claude Code がサイトの修正・テスト・公開を直接行えるようにする。

## 現在の状態
| 項目 | 状態 |
|---|---|
| 公開中の本番 | https://okaidoku-checker.rightharp65.chatgpt.site/ （変更していない） |
| コピー | `checker-site/`（`tools/mirror_site.py` を GitHub Actions で実行して取得。一覧と sha256 は `checker-site/MIRROR_REPORT.md`） |
| モデル | 6ファイルすべて `models/catalog.json` の bytes・sha256 と一致 |
| 動作確認 | 実Chromium（PC 1280px・スマホ 390px）で入力例→査定: 参考査定価格・判定・価格差・PR表記の表示、JavaScriptエラー0件（`tests/test_checker_site.py`、CIで常時実行） |
| 新しいURL | https://okaidoku-checker.pages.dev （Cloudflare Pages プロジェクト `okaidoku-checker`、main の `checker-site/` を公開。2026-11-01 のぼるさんが作成） |
| 新旧の一致 | 同じ物件（中古戸建て・山口県宇部市際波・1,780万円）で新旧とも参考査定価格 1,049万円（2026-11-01 のぼるさんが両方の画面で確認） |

## 分かったこと（コードで確認）
- 査定（Web Worker）とスクショの文字読み取り（Tesseract）はブラウザ内で実行。入力内容・画像を外部に送る処理はない。外部への送信は Metricool の閲覧計測だけ。
- 中古戸建てモデルの更新は `learning.mjs` が `https://raw.githubusercontent.com/chi-pao/-/main/` の `site-models/manifest.json` を読んで取り込む。chi-pao/- の自動学習が本番に影響する。
- 広告は A8.net のリンク3本。

## 切り替え時に必ず変えるもの（チェックリスト）
- [x] 公開URLの方針（2026-11-01 のぼるさん決定）: **当面は無料URL**（Cloudflare Pages）。収益化の見込みが立った時点で専用ドメイン（年1,500〜4,000円程度）を取得し、そちらへ移す。専用ドメインへの移行時は、この下の項目（canonical・計測・提携先URL）をもう一度行う。
- [x] 無料URLの形: 専用プロジェクト `okaidoku-checker.pages.dev`（2026-11-01 のぼるさん決定・作成）。
- [x] `index.html` の canonical・og:url・構造化データ（`#website`・`#app`）を新URLに変更。OGP画像は `social/launch-20261021.png` を取得できていないため、当面 `app-icon-512.png` を使う。
- [x] `analytics.mjs` の計測対象ホスト、`app.mjs` の共有用URLを新URLに変更。
- [x] `index.html` 末尾の旧ホスト専用スクリプト（`/cdn-cgi/challenge-platform/...`）を削除。旧ホストへの参照が残っていないことは `tests/test_checker_site.py` で常に確認。
- [ ] Metricool・A8.net・Instagram プロフィールのURLを新URLに変更（のぼるさん）。A8.net は掲載サイトURLの変更・追加が必要な場合がある。
- [ ] 旧URLから新URLへの案内（ChatGPT Sites 側にリンクを1行追加する依頼書を作る）。
- [x] 新旧で同じ入力の査定結果が一致することを確認（上の表）。

## これからの扱い
- 正本は `checker-site/`。改修はここで行い、テストとプレビューで確認してから main に入れる（main に入ると okaidoku-checker.pages.dev に自動で公開される）。
- `mirror-checker-site` は再実行しない。再実行すると旧サイトの内容で `checker-site/` が上書きされ、URLの変更や修正が消える。ChatGPT Sites 側は今後変更しない。

## 切り替え後に直したもの
- 都道府県の並び: 番号が0で始まる北海道〜栃木県が最後に並んでいた（JavaScript のオブジェクトは整数に見える番号を先に並べるため）。番号順に並べ直した。
- 査定結果の面積: 坪で入力すると「70.08264462809917㎡」のように長い小数で表示されていた。表示だけ小数2桁までに整えた（査定に使う値は変えていない）。
- 「用途地域」「構造」の重複に見える選択肢（例: 近隣商業／近隣商業地域）は、モデルの学習データの区分そのものなので、査定結果が変わらないことを確かめるまで残す。
