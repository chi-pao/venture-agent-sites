# クラウドの自動投稿（Metricool を使わない）

2026-11-26 のぼるさん「投稿予約したけど、無料の枠が終わってたみたいで投稿されなかった　クラウド経由で枠にとらわれず自動投稿する仕組みを作って欲しい」
2026-11-27 のぼるさん「インスタ以外の投稿は、その方向で進めてください。」（YouTube は公開で投稿して確かめる、TikTok は審査の前は下書きでスマホに届ける。Instagram は今回は作らない）

## しくみ
- GitHub の自動実行（`.github/workflows/sns-autopost.yml`）が15分ごとに `ops/sns/autopost/posts.json` を見る。パソコンが止まっていても動く。お金はかからない。
- 「approved」（のぼるさんの OK）があって、時間を過ぎた物を出す（本体 `tools/sns_autopost/post.py`）。3日より古い物は出さない。
- **YouTube**: 公開で上げる。上げたあとに状態を読み返し、公開になっていなければお知らせする（その回は手で上げ直す）。
- **TikTok**: 審査の前なので「下書き」として、のぼるさんのスマホの TikTok に届ける。お知らせに説明文がつくので、貼って「投稿」を押す。
- 出した記録は、非公開の置き場所（venture-studio-data の `autopost/log.json` と `INBOX.md`）。Discord の設定があれば Discord にも届く。記録がある SNS には二度と出さない。
- 合いことばは、手元で `connect.py` を動かしたときに、かぎをかけて非公開の置き場所（`autopost/tokens.enc`）にしまう。画面にも記録にも出ない。かぎはノボログと同じ物なので、GitHub の秘密欄に新しく入れる物は無い。
- 動画は、このリポジトリの `ops/sns/video/<番号>/` に置いた物を使う（予約は PR で posts.json に足す）。

---

# のぼるさんの手順（これだけ）

## 0. 変更に OK を出す
GitHub の PR を開いて OK（マージ）してください。

## 1. YouTube をつなぐ（1回だけ・10分ほど）
Google の画面は英語のこともあります。下のとおりに押せば大丈夫です。

1. https://console.cloud.google.com/projectcreate を開き、YouTube のチャンネルの Google アカウントでログインします。
   「プロジェクト名」に `noboru-autopost` と書いて「作成」。
2. https://console.cloud.google.com/apis/library/youtube.googleapis.com を開いて「有効にする」。
3. https://console.cloud.google.com/auth/branding を開いて「開始」。
   - アプリ名: `noboru-autopost`、サポートのメール: ご自分のメールを選ぶ → 次へ
   - 対象: 「外部」→ 次へ
   - 連絡先のメール: ご自分のメール → 次へ → 同意にチェック → 「作成」
4. https://console.cloud.google.com/auth/audience を開いて「アプリを公開」→「確認」。
   **（ここが大事です。「テスト中」のままだと、7日でつながりが切れます）**
5. https://console.cloud.google.com/auth/clients を開いて「クライアントを作成」。
   - アプリケーションの種類: 「デスクトップ アプリ」、名前はそのまま →「作成」
   - 出てきた画面で「JSON をダウンロード」を押す（ダウンロードフォルダーに入ります）。
6. Windows の「PowerShell」を開いて、次の3行を1行ずつ打って Enter。
   ```
   cd C:\claudecode\venture-agent-sites
   git pull
   py tools\sns_autopost\connect.py youtube
   ```
   ブラウザが開くので、チャンネルのアカウントを選びます。
   「このアプリは Google で確認されていません」と出たら、「詳細」→「noboru-autopost（安全ではないページ）に移動」→「続行」を押します（自分で作ったアプリなので大丈夫です）。
   黒い画面に「YouTube とつながりました（チャンネル: ○○）」と出たら終わりです。
7. Claude に「YouTube つないだ」と伝えてください。2秒の試しの動画を「限定公開」で上げて、すぐ消す確認をこちらでします。

## 2. TikTok（審査があるので最後に・こちらで申請の文を用意します）
TikTok はアプリの登録と審査が必要です。申し込みの文やページは Claude が用意するので、準備ができたらお知らせします。
流れだけ先に書いておきます。
1. https://developers.tiktok.com に TikTok のアカウントでログイン →「Manage apps」→ アプリを作る（文は Claude が用意）。
2. 「Login Kit」（Desktop、リダイレクトの住所 `http://localhost:8723/callback/`）と「Content Posting API」（下書きの送り方だけ）を足して、審査に出す。
3. 通ったら、PowerShell で `py tools\sns_autopost\connect.py tiktok` → 画面の「Client key」「Client secret」を貼る（貼っても文字は見えません）→ ブラウザで「許可」。

## 3.（任意）Discord にお知らせを届ける
Discord の、お知らせを受けたいチャンネルの「設定」→「連携サービス」→「ウェブフック」→「新しいウェブフック」→「ウェブフック URL をコピー」。
https://github.com/chi-pao/venture-agent-sites/settings/secrets/actions/new を開き、名前に `STUDIO_DISCORD_WEBHOOK`、下の欄にコピーした URL を貼って「Add secret」。
（無くても、お知らせは非公開の置き場所の INBOX.md に残ります）

---

## 確かめ方（Claude 用）
- GitHub の「Actions」→「SNS autopost (checker)」→「Run workflow」。練習にチェックのままなら、つながりの確認だけ。
- 「YouTube の試し」にチェックすると、2秒の動画を限定公開で上げ、状態を確かめて、すぐ消す。
- 手元でつながりを見る: `py tools\sns_autopost\connect.py status`
- テスト: `python -m unittest tools/sns_autopost/test_post.py`

## 合いことばの期限
- YouTube: 「本番」にしてあれば切れない（6か月まったく使わない時だけ切れる）。
- TikTok: 2時間ごとにクラウドが自動で延長。180日で切れる前に（14日前から）お知らせが出るので、`connect.py tiktok` をもう一度。

## Metricool との関係
- 自動投稿に移した物は、Metricool の予約を消す（二重に出さないため）。
