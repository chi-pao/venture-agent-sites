# クラウドの自動投稿（Metricool を使わない）

2026-11-26 のぼるさん「投稿予約したけど、無料の枠が終わってたみたいで投稿されなかった　クラウド経由で枠にとらわれず自動投稿する仕組みを作って欲しい　もう一度試してください」

## しくみ
- GitHub の自動実行（`.github/workflows/sns-autopost.yml`）が15分ごとに `ops/sns/autopost/posts.json` を見る。
- 「approved」（のぼるさんの OK）があって、時間を過ぎた物を、各 SNS に直接出す（本体 `tools/sns_autopost/post.py`）。
- 出した記録は `ops/sns/autopost/log.json`。記録がある SNS には二度と出さない。3日より古い物は出さない。
- 画像・動画は、このリポジトリの公開の場所（main ブランチ）から読む。
- 合いことば（トークン）は GitHub の秘密欄だけに置く。入れる場所: https://github.com/chi-pao/venture-agent-sites/settings/secrets/actions/new
  （上の欄＝名前、下の欄＝合いことば、下の緑のボタンで保存）
- お金はかからない（公開のリポジトリの自動実行は無料）。

## SNS ごとの準備（1つずつ進める）
| 順 | SNS | 秘密欄の名前 | 準備 | 注意 |
|---|---|---|---|---|
| 1 | Threads | THREADS_TOKEN | Meta の開発者のページで「アプリ」を作り、Threads の合いことばを出す | 合いことばは60日で切れる。50日ごとに作り直す |
| 2 | Instagram | INSTAGRAM_TOKEN | 1 と同じアプリに Instagram を足す。アカウントは「プロ」（ビジネスかクリエイター）にする | 60日で切れる |
| 3 | Bluesky | BLUESKY_HANDLE と BLUESKY_APP_PASSWORD | Bluesky の設定で「アプリパスワード」を作る（いちばん簡単） | 切れない |
| 4 | YouTube | YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN | Google の開発者のページで準備 | 審査が済むまで、出した動画は「非公開」になる。審査（無料）を申し込む |
| 5 | TikTok | （まだ） | TikTok の開発者の審査が要る | 審査が済むまで「自分だけ見られる」投稿しかできない。それまでは手で出す |

## 確かめ方
GitHub の「Actions」→「SNS autopost (checker)」→「Run workflow」で、練習にチェックを入れたまま動かすと、
つながったかどうかだけが表示される（投稿はしない）。

## Metricool との関係
- 自動投稿に移した物は、Metricool の予約を消す（二重に出さないため）。
