# 旅行アプリの検索・共同編集接続（2026.10.23.5）

開発確認版： https://venture-agent-sites.pages.dev/agent/review-products/travel

画面、Geoapify接続API、Cloudflare D1共同保存を実装。実APIキーは未設定で、実データの検索と本番D1の共同操作は接続後に確認する。発信OKは未取得。完成品として告知しない。

## APIを使い始める手順

1. https://myprojects.geoapify.com/ で登録し、Freeプランのプロジェクトを作る。API Keysにあるキーを使う。公式のFree枠は3,000 credits/day・クレジットカード不要・帰属表示付き商用利用可能（2026-10-23確認）。有料プランに自動で申し込まない。
2. Cloudflareで、以前作成したD1 `venture-travel` を開く。Consoleで次を実行する。既存のデータは削除しない。

```sql
CREATE TABLE IF NOT EXISTS travel_api_limits (
 bucket TEXT PRIMARY KEY,
 count INTEGER NOT NULL
);
```

3. `Workers & Pages → venture-agent-sites → Settings → Variables and Secrets` のProduction環境に以下を設定する。

| 名前 | 値・種類 |
| --- | --- |
| GEOAPIFY_API_KEY | 取得したAPIキー。Secretとして保存 |
| TRAVEL_SEARCH_ENABLED | true。通常の変数 |
| TRAVEL_SHARING_ENABLED | true。通常の変数 |

4. 同じProduction環境のD1 Bindingが `TRAVEL_DB`、対象が以前作成した `venture-travel` であることを確認する。DBをもう一つ作り直す必要はない。基本テーブルが未作成の場合のみ `schema/travel.sql` を実行する。
5. Deploymentsから最新のデプロイを再試行・再デプロイする。変数保存だけで既存デプロイへ反映されたと扱わない。
6. `/api/travel/health` または開発アプリ内の「旅行APIの接続状態を確認」で確認。`databaseBound`、`schemaReady`、`searchSchemaReady`、`sharingEnabled` がtrue、`search` がconfiguredになったら、旅行画面で実際に検索する。
7. 出発地を最初に追加 → 周辺の食事・観光候補を追加 → 徒歩または車の移動を取得 → 滞在・余裕を変更 → 招待リンクを別端末で開く。時刻・施設・出典と取得時刻、読み取り専用・同時更新の競合も確認する。

APIキーをコード・GitHub・このチャットへ貼り付ける必要はない。キーはサーバー側だけで使い、ブラウザへ返さない。登録時のサービス規約・利用枠は本人が確認する。

## 今回できること

- 国内の場所検索、5km以内の観光・食事候補。APIから取得した候補だけを返す。候補の近さと評判・営業中は別。
- 徒歩・車の経路とモデル上の移動時間。到着・滞在・休憩・固定の予約時刻・終了目標を照合。徒歩がゆっくりの場合は25%の余裕を別に加算し、APIの所要時間そのものと区別する。
- 日別の旅程、並べ替え、費用/人の手動入力。未入力費用や移動未取得を0と確定しない。
- 端末内保存、実データCSV、JSONバックアップと復元・キャンセル・不正ファイル拒否。
- 閲覧・編集用の招待を分けた共同保存。招待トークンはURLのフラグメントから読み、APIにはAuthorizationヘッダーで送る。サーバーDBはトークンのハッシュを保持する。
- 変更バージョンによる同時編集の競合検出。409時に編集中のデータを保持し、回復用にも保存。共有先への保存は明示操作。

## まだ満たしていない要件

電車・バスの時刻表・運賃・乗換、施設営業時間の自動確認、リアルタイム交通・天候、予約そのもの、同行者ごとの希望投票・個別権限解除は未対応。徒歩・車で代用して対応済みとはしない。滞在45分・食事60分はアプリの変更可能な初期目安で、施設の推奨値ではない。

## 試験時の上限

共有新規20件/日・合計1000件・最終更新から90日保存。計画32KB以内。検索はクライアント10件/分、全体で1呼出しにつき保守的に2クレジットを予約し最大1,000予約クレジット/日。失敗分も予約を戻さない。Geoapify側の利用枠や同じキーの他用途とは別管理。外部側で制限されたら結果を捏造せずエラー表示する。任意のURLへAPIキーを付けて送信する構造ではない。

## 検証

- `node tests/travel/test-sharing.mjs`
- `node tests/travel/test-search.mjs`
- PlaywrightとChromiumを用意後、`python tests/travel/test-browser.py`

ブラウザ検証は1280px/390px、実SQLiteの共同保存、閲覧権限、同時更新、数値計算、CSV・JSON・再読込を実行。検索先の応答は検証用フィクスチャであり、Geoapify実キーの稼働・日本の検索精度を実証したものではない。利用者の評価・競合に対する優位性・収益性も未検証。

公式資料：
https://www.geoapify.com/pricing/
https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/
https://apidocs.geoapify.com/docs/places/
https://apidocs.geoapify.com/docs/routing/
https://developers.cloudflare.com/pages/functions/bindings/#d1-databases


## 2026-10-24: travel journal visual review and competitor references

Official reference pages checked:
- nicody https://nicody.jp/ : place search, reorder, invite flow; map and itinerary switching.
- Wanderlog https://wanderlog.com/ : itinerary and map in one view, reduce tool switching.
- tabiori https://tabiori.com/ : family/friend shared itinerary, collaborative planning and printable records.

Applied: clear start/itinerary anchors, vivid teal/coral/yellow journal styling, decorative original SVG illustration clearly labelled as an illustration, chronological event cards, trip companion/pace/buffer summary, visible search feedback, mobile single-column route action, keyboard focus outlines and reduced-motion support. Existing storage/CSV/restore/shared-plan permissions remain in use. No competitor artwork or branding copied.

Differentiation hypothesis: explicitly plan rest, slower walking allowance and desired finish time for groups with different paces. This is not a verified unique feature or measured superiority. No new claim of maps, public transit, opening hours, booking, real-time chat, or automatic route optimization.

Comparison acceptance task: create the same 1-day 4-place trip for 3 family members, set a fixed-time booking, add breaks, compare late/finish warnings, reorder places and send a read-only invite. Measure successful completion, time, confusion points and willingness to reuse with actual target users. Record missing features and failures before declaring an advantage.

Validation: desktop 1280px and mobile 390px browser workflow, reload, CSV, JSON restore/cancel/invalid restore, two-browser shared editing/version conflict, read-only invitation passed with provider fixtures. Both layouts visually reviewed with Japanese fonts. Actual production Geoapify search currently returns a connection error; it is not counted as a passed search test or launch-ready.
