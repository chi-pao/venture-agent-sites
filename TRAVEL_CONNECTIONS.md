# 旅行アプリの接続準備

状態: 共同保存APIの実装準備版。画面への接続・Cloudflare上での確認・利用者の発信OKは未完了。

## 今必要な接続

| 機能 | 接続 | 現状 |
| --- | --- | --- |
| 同行者と同じ旅程を保存・更新 | Cloudflare Pages Functions + D1 | コード準備。D1の作成・紐付け・SQL実行が必要 |
| 経路・出発/到着・所要時間 | 経路データAPI | 未接続。Google Routesは請求設定が必要。自動有効化しない |
| 観光・食事候補と営業時間 | 施設検索API | 未接続。Google Placesは請求設定が必要。自動有効化しない |
| 滞在時間・休憩・行程再計算 | アプリ内の計算と利用者の希望 | 取得情報と目安を区別して実装する |

## D1接続（Cloudflareの既存アカウント内）

1. Storage & databases → D1 SQL database → Create database。名前は `venture-travel`。Free枠で作成する。
2. データベースのConsoleで `schema/travel.sql` を実行する。
3. Workers & Pages → `venture-agent-sites` → Settings → Bindings → D1 database。
   Binding名 `TRAVEL_DB`、データベース `venture-travel` を指定する。
4. 試験用のデプロイ後、`GET /api/travel/health` で `databaseBound` と `schemaReady` がtrueであることを確認する。

`TRAVEL_SHARING_ENABLED=true` は共同保存を試験する段階で設定する。それまでは書込みを受け付けない。検索APIの契約・請求設定や本番サイトの機能差し替えはこの準備には含めない。

## 共同保存の動作

- `POST /api/travel/trips` に `{plan}` を送り、計画ID・閲覧用・編集用の招待情報を取得する。
- `GET /api/travel/trips/{id}` は招待情報をAuthorizationヘッダーで送る。招待情報をURLクエリやログに入れない。
- `PUT /api/travel/trips/{id}` は編集用の招待情報と `{version,plan}` を送る。
- バージョンが古ければ409を返す。画面側は編集中の内容を保持し、最新の計画との調整を促す。自動上書きしない。
- 招待情報を知る同行者が操作できる方式。会員ごとの本人確認・権限剥奪は未対応。招待情報を第三者に渡さないことを共有画面に説明する。
- 最終更新から90日間保存。試験段階は新規20件/日・保存1000件まで。1件32KB以内。Free枠が無制限という意味ではない。
- APIキーや招待情報の平文はDBに保存しない。招待情報はハッシュを保存する。入力内容はDBに保存するので画面側で予約番号など不要な情報を集めない。

## 発信前に必要な確認

1. 二つの端末で同じ予定を確認・更新する。
2. 同時編集で片方の変更が消えず、競合が表示される。
3. 閲覧専用の招待で編集できず、招待情報なしで旅程が見えない。
4. 接続エラー・保存上限のとき、端末上の編集中データが消えない。
5. 検索・行程・共有を画面へ接続し、スマホで試し、利用者からOKを得る。

公式確認先: https://developers.cloudflare.com/d1/platform/pricing/
https://developers.cloudflare.com/pages/functions/bindings/#d1-databases
https://developers.google.com/maps/documentation/routes/usage-and-billing
https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
