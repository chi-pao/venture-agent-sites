# 第1話の動画 投稿セット（Instagram・Threads は予約の依頼済み: `ops/chatgpt/outbox/EP01-4-POST.md`。TikTok はアカウントを作って Metricool につないだ（のぼるさん 2026-11-04〜05）。予約の依頼: `ops/chatgpt/outbox/EP01-6-TIKTOK.md`。YouTube ショートも予約の依頼済み: `ops/chatgpt/outbox/EP01-5-YOUTUBE.md`、チャンネル https://www.youtube.com/channel/UCOF93syki7TeiCDSXQuvMSQ ）

- 動画: `ops/sns/video/EP01-v3.mp4`（縦 1080×1920・32.6秒・声と音楽つき）
- 投稿する人: のぼるさん（Claude Code は SNS に投稿できないため）
- おすすめの時間: 平日 18:00（ほかの投稿と同じ）
- 型の記録: `ops/sns/EXPERIMENTS.md` の型「character」（ケンジ一家のイラスト＋ひとこと）の初回として記録する

## 投稿の前に確かめること
1. 動画を最後まで再生して、声と音楽の聞こえ方を確かめる
2. 各 SNS の「AI で作成」の表示をオンにする（登場人物も声も AI で作ったものなので）
   - どの SNS も、投稿・アップロードの画面の中（「詳細設定」や「その他」の中のことが多い）に「AI」と書かれた項目がある。場所はアプリの版で変わるので、見つからなければ画面の写真を Claude Code に送る
3. 動画に出てくる査定結果（2,011万円・割高の可能性）は 2026-11-03 のモデルで出した数字。モデルを更新していたら、チェッカーで同じ入力をして数字が変わっていないか確かめる
4. プロフィールのリンクを、下の「プロフィールのリンク」に変えておく

## プロフィールのリンク（SNS ごとに変えて、どこから来たかを測る）
Instagram・YouTube ショートは、説明欄の URL を押せないことが多いので、プロフィールのリンクから来てもらう。
- Instagram: `https://okaidoku-checker.pages.dev/?utm_source=instagram&utm_medium=social&utm_campaign=ep01&utm_content=character`
- YouTube: `https://okaidoku-checker.pages.dev/?utm_source=youtube&utm_medium=social&utm_campaign=ep01&utm_content=character`

## Instagram リール
```
家を買おうか考え始めたら、まず「この値段、相場と比べてどう？」を確かめてみませんか。

お買い得物件チェッカーは、物件ページのスクショを貼るだけで、参考査定価格と販売価格の差をチェックできます。無料・登録不要。

※登場人物・物件は架空です。査定は参考値で、売買価格を保証するものではありません。
▶ プロフィールのリンクから

音声: AivisSpeech (fumifumi)
BGM: 昼下がり気分 / KK (OpenTracks・旧DOVA-SYNDROME)

#マイホーム #中古住宅 #家探し #住宅購入 #子育て世帯
```

## YouTube ショート
タイトル:
```
この家、高いの？安いの？ 2,480万円の中古戸建てを確かめてみた #shorts
```
説明:
```
家を買おうか考え始めたら、まず「この値段、相場と比べてどう？」を確かめてみませんか。
お買い得物件チェッカーは、物件ページのスクショを貼るだけで、参考査定価格と販売価格の差をチェックできます。無料・登録不要。

https://okaidoku-checker.pages.dev/?utm_source=youtube&utm_medium=social&utm_campaign=ep01&utm_content=character

※登場人物・物件は架空です。査定は参考値で、売買価格を保証するものではありません。

音声: AivisSpeech (fumifumi)
BGM: 昼下がり気分 / KK (OpenTracks・旧DOVA-SYNDROME)

#マイホーム #中古住宅 #家探し #住宅購入
```

## 投稿したあと
- 48時間後に、表示・いいね・保存・プロフィールのリンクのクリック数を `ops/sns/EXPERIMENTS.md` の「結果」の表に書く
- YouTube で著作権の申し立てが来たら、曲のサイトの説明（https://opentracks.com/help/articles/youtube/ ）に従って異議を申し立てる。この曲や動画を Content ID に登録してはいけない
