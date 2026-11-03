# A8.net の広告をサイトに追加する

## のぼるさんの手順（どちらか）
**A. 私（Claude Code）にコードを送る** — いちばん簡単。

**B. GitHub の画面から追加する**
1. A8.net で承認された案件の「広告リンク作成」→ テキストリンクのコードを全部コピー（`<a href="https://px.a8.net/...">…</a>` と、その下の `<img … 0.gif …>`）。
2. GitHub の chi-pao/venture-agent-sites →「Actions」→ 左の「Checker - add an A8.net offer」→「Run workflow」。
3. 「広告枠」を選び、「コード」に貼り付けて「Run workflow」。地域限定の案件（ノムコム）は「出す都道府県」も入れる。
4. 数分で「広告の追加：〇〇」という PR ができる。Claude Code が確認して本番に反映する。

## 広告枠
| 広告枠 | 案件 | 出す相手 |
|---|---|---|
| sell-rakuuru-house | ラクウル（空き家・中古戸建て） | 売る予定・中古戸建て |
| sell-rakuuru-old | ラクウル（訳アリ） | 売る予定・築45年以上（優先） |
| sell-nomucom | ノムコム | 売る予定・営業エリアの都道府県のみ |
| loan-mogecheck | モゲチェック（借り入れ） | 買う予定 |
| fire-insweb | インズウェブ火災保険 | 買う予定 |
| reno-hikarinobe | ひかリノベ | 買う予定・東京/神奈川/千葉の戸建て・マンション |
| inspection / reform / moving | 住宅診断 / リフォーム / 引越し（案件未定） | — |

## 安全のため
- A8.net のリンク（https://px.a8.net/svt/ejp?a8mat=…）と、同じ a8mat の計測用画像（*.a8.net/0.gif）以外が含まれるコードは受け付けない。
- 表示には必ず「広告・PR」と付く（offers.mjs）。
