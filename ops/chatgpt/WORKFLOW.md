# Claude Code の指示で ChatGPT が画像・動画を作る流れ

方針（のぼるさん 2026-11-03）: SNS 運用の画像・動画の制作は ChatGPT（チャッピー）の得意分野を生かし、Claude Code の指示のもとで行う。

## 役割
| 作業 | 担当 |
|---|---|
| 何を作るか（企画・型・台本・使ってよい事実） | Claude Code（`sns-strategist` / `creative-producer`） |
| イラスト・キャラクター・動画（絵・動き・音声案）・投稿文の言い回し案 | **ChatGPT** |
| 数字が正確でなければならない画像（取引データのグラフ・実際の査定結果） | Claude Code が自動で作る（`ops/sns/`） |
| 事実・PR 表記・規約の確認 | Claude Code（`qa-reviewer`） |
| 承認 | のぼるさん |
| Metricool への予約 | ChatGPT（承認済みのものだけ） |

## 流れ（毎週）
1. **月曜** Claude Code が `ops/chatgpt/outbox/` に制作依頼書を置く（1件1ファイル。依頼ID・作るもの・サイズ・使ってよい事実・守ること・返し方）。`ops/tasks/queue.json` に「承認待ち」で登録。
2. **のぼるさん** が内容を見て「OK」→ Claude Code が `queue.json` の状態を「承認済み」にする（依頼書の先頭にも「承認済み」と書く）。
3. **ChatGPT のタスク**（平日に自動で動く）が GitHub の `ops/chatgpt/outbox/` を読み、**「承認済み」の依頼書だけ** を制作して、Metricool に予約する。
4. ChatGPT は結果（作った画像・動画の説明、予約日時、予約ID）を返す。のぼるさんがその返事を Claude Code に送る（または Metricool のスクショ）。
5. **金曜** Claude Code が数字を記録し（`ops/sns/EXPERIMENTS.md`）、翌週の依頼に反映する。

## ChatGPT のタスクに一度だけ設定する指示（のぼるさんがコピーして貼る）
```
あなたは「お買い得物件チェッカー」（https://okaidoku-checker.pages.dev/）のSNS制作担当です。
平日に動いたら、次を行ってください。
1. GitHub の chi-pao/venture-agent-sites リポジトリの ops/chatgpt/outbox/ を読み、先頭に「承認済み」と書かれていて、まだ「制作済み」になっていない依頼書だけを選ぶ。
2. 依頼書のとおりに画像・動画・投稿文を作る。依頼書の「使ってよい事実」以外の数字や効果を書かない。広告を含むときは「PR」を入れる。実在の人物・他社のロゴは使わない。AIで作った画像・動画には「AIで作成」の表示を付ける。
3. 依頼書の予約日時で Metricool（ブランドID 7545667）に予約する。リンクは依頼書のURLをそのまま使う（旧URL okaidoku-checker.rightharp65.chatgpt.site は使わない）。
4. 最後に、依頼ID・作ったもの・予約日時・予約IDを一覧で返す。承認済みの依頼がなければ「本日の制作なし」と返す。
```
（GitHub への書き込みは ChatGPT からは行わない。制作済みの記録は Claude Code がのぼるさんの報告をもとに付ける）
