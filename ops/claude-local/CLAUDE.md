# C:\AI事業開発 で動く Claude Code への指示

このファイルは `C:\AI事業開発\CLAUDE.md` に置く。ここは事業開発AIの**実データのフォルダ**で、Gitリポジトリではない。

## 役割
- Claude Code: 3事業（事業開発AI・お買い得物件チェッカー・旅行計画アプリ）の開発・修正・検証・GitHub管理の司令塔。このPCでは**調査と検証**を担当する。
- ChatGPT: Claude Codeの指示（GitHubの `ops/chatgpt/`）に基づくSNS投稿・画像・動画。
- 事業開発AI: 事業候補の探索・評価・実績管理。

## このフォルダの構成
| 場所 | 中身 | 扱い |
|---|---|---|
| `venture_agent_integrated.db` | 事業・設定・履歴（SQLite） | **読むだけ**。調べるときは `backups\` か一時フォルダへコピーしてから開く |
| `code\current.py` | 動いている本体（GitHubの `agent/venture_agent_integrated.py` と同じ） | **編集しない**。修正はGitHubのプルリクエストで行い、`release.json` で配布する |
| `code\launcher.py`, `update-and-start.cmd` | 更新・起動・自動復旧 | 編集しない |
| `venture_outputs\` | 生成したアプリ・比較テストの証拠（`shared\model-benchmarks\<run_id>\`） | 読むだけ |
| `venture_agent_autonomous\` | 運転の状態・ログ | 読むだけ |
| `backups\` | 更新前のDBと旧コード | 削除しない |
| `diagnostics\` | 診断ファイル（zip） | 作成してよい |

## してよいこと
- ファイル・ログ・生成物を読む。DBはコピーを読む。
- 診断ファイルを作る: `py code\current.py --export-diagnostics`（DB本体・APIキー等は含まれない）
- 状態を見る: `py code\current.py --research-status`、`ollama list`、`py -m streamlit version`
- コードの修正が必要なら、別フォルダ（例 `C:\AI事業開発-repo`）に `git clone https://github.com/chi-pao/venture-agent-sites` し、`claude/...` ブランチで修正 → テスト → プルリクエスト。mainへ直接pushしない。

## してはいけないこと
- 自動運転・分野探索・比較テストの開始（画面のボタン、`--research`、`streamlit run` を含む）。のぼるさんの指示がある場合だけ。
- DB・`code\`・`backups\` の変更や削除。
- DB・ログ・生成物・APIキーをGitHubやチャットへアップロードすること（診断zipは可）。
- 追加料金が発生する操作（有料API・`ANTHROPIC_API_KEY` の設定・有料プラン）。必要なら先にのぼるさんへ確認する。
- 検証していない機能を「完成」「動作確認済み」と報告すること。

## 報告の形
1. 調べたファイルと見たこと（事実）
2. 原因の判断（確定 / 推定 を分ける）
3. 修正方針（GitHubのどのファイルを、どう変えるか）
4. のぼるさんに必要な操作
