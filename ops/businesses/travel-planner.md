# 旅行計画アプリ（旅のペースノート）

開発確認版: https://venture-agent-sites.pages.dev/agent/review-products/travel （noindex）

## 仕様

| 項目 | 内容 |
|---|---|
| 対象 | 友達・カップル・家族の国内旅行。同行者の歩く速さ・休憩・食事・帰宅時刻に無理のない旅程を作る |
| 画面 | `agent/review-products/travel.html`（単一HTML、PC・スマホ対応） |
| API | `functions/api/travel/[[path]].js`（Cloudflare Pages Functions）、DB `schema/travel.sql`（Cloudflare D1） |
| 検索 | Geoapify（OpenStreetMap）: 場所検索、5km以内の観光・食事候補、徒歩・車の経路と所要時間 |
| 共同編集 | 閲覧用・編集用の招待を分けた共有。トークンはハッシュで保存。版番号で同時更新の競合を検出 |
| 端末内 | 保存、CSV出力、JSONバックアップと復元 |
| 上限 | 共有作成20件/日・合計1,000件・90日保存。検索は利用者ごとに10回/分、全体で1日1,000予約クレジット |

## 状態

| 機能 | 状態 |
|---|---|
| 画面・端末内保存・CSV・JSON | テスト済み（`tests/travel/`、ブラウザ検証） |
| 検索・経路API（コード） | テスト済み（検索先の応答は試験用データ） |
| 共同保存API（コード） | テスト済み（SQLiteで代用） |
| 本番の検索 | **接続待ち**: GeoapifyのAPIキー未設定 |
| 本番の共同保存 | **接続待ち**: Cloudflare D1とバインディングの設定・確認が未完了 |
| 電車・バスの時刻・運賃・乗換 | 未着手（徒歩・車で代用して対応済みとはしない） |
| 営業時間の自動確認、天候・混雑 | 未着手 |
| 同行者の希望投票・個別の権限解除 | 未着手 |
| 発信OK | 未取得。完成品として告知しない |

## 開発履歴
- 2026-10-23: 接続版の旅行計画（検索・共同保存・ガイド付き設定）を追加（2026.10.23.5）
- 2026-10-24: Geoapify Workers対応（転送応答でのキー漏えい防止など）
- 2026-10-31: 引き継ぎ時に契約テスト2本が合格することを確認。CIで常時実行するよう追加（PR #14）

## のぼるさんの操作が必要なこと（無料の範囲）
`agent/TRAVEL_CONNECTIONS.md` の手順どおり:
1. Geoapify のFreeプランでAPIキーを取得（クレジットカード不要）。
2. Cloudflare D1 `venture-travel` に `travel_api_limits` テーブルを作成。
3. Cloudflare Pages の Production 環境に `GEOAPIFY_API_KEY`（Secret）、`TRAVEL_SEARCH_ENABLED=true`、`TRAVEL_SHARING_ENABLED=true` を設定し、`TRAVEL_DB` のバインディングを確認して再デプロイ。
4. `/api/travel/health` の結果をClaude Codeに渡す。

## 今後の開発計画
| 優先 | 作業 | 完了条件 |
|---|---|---|
| 1 | 本番接続の確認（上の設定後） | health が全てtrue/configured、実検索・別端末での共同編集・競合表示を確認 |
| 2 | 実利用テスト（数組） | 旅程作成の完了・所要時間・迷った箇所を記録 |
| 3 | 発信OKの判断材料をまとめる | のぼるさんの判断 |
| 4 | 電車・バス対応の調査 | 無料で使える公式データ・APIの有無を確認し、費用が出る場合は事前に相談 |
