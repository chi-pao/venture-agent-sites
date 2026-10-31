# Windows実機の確認手順（のぼるさんのPC）

GitHubのWindows環境（`venture-windows-launcher`）では、`update-and-start.cmd`からの更新・起動確認・自動復旧・二重起動防止・再起動・`--rollback`を自動で試験している。
ただし、それはGitHubが用意したWindowsであり、**のぼるさんのPC（Pythonの版・Streamlitの版・Ollama・実データ）での確認は未実施**。下の手順で確認するまで「Windows実機: 未検証」と扱う。

## 1回だけ必要な準備
1. https://github.com/chi-pao/venture-agent-sites/blob/main/agent/update-and-start.cmd を開き、右上の「Download raw file」で保存する。
2. `C:\AI事業開発\update-and-start.cmd` を、保存したファイルで置き換える（古いファイルは別名で残してよい）。
   - 置き換えないと、自動復旧のない古い起動プログラムのまま動く。

## 確認（約10分）
| # | 操作 | 期待する表示・結果 | 結果 |
|---|---|---|---|
| 1 | 動いている黒い画面でCtrl+Cを押して終了 | 黒い画面が閉じる、またはプロンプトに戻る | |
| 2 | `update-and-start.cmd` をダブルクリック | `Update installed; backup: ...` の後に `Checking that the new version starts...` と `Startup check passed` | |
| 3 | ブラウザで http://localhost:8501 を開く | 上部の「表示版」が release.json の版（例: 2026.10.31.1）になっている | |
| 4 | 「自動開発の設定」の表示 | 起動直後は OFF。以前ONのまま閉じていた場合は「中断されていました」と表示される | |
| 5 | 「継続運転を開始」→ 1分待つ →「安全に停止」 | 「最終動作」の時刻が進み、停止後はOFF | |
| 6 | 動かしたまま、もう一度 `update-and-start.cmd` をダブルクリック | 2つ目の黒い画面に `Already running` と出て止まる | |
| 7 | 1の方法で終了し、再度ダブルクリック | `Already up to date` と出て、同じ版で起動する | |
| 8 | 終了後、黒い画面（コマンドプロンプト）で `C:\AI事業開発` に移動し `update-and-start.cmd --rollback` | `Previous code restored` と出て、1つ前の版で起動する | |
| 9 | 8の後、終了してから普通にダブルクリック | 最新版に戻る（`Update installed`） | |

結果の列に ○/× と、×の場合は黒い画面の最後の20行をコピーしてClaude Codeに渡す。

## 困ったとき
- `Startup check could not run` と出た: Streamlitが古い可能性。版を確認: `py -m streamlit version`。起動自体は続行される。
- `Rolled back to the previous version` と出た: 新しい版が起動確認に失敗し、自動で前の版に戻った。表示された理由をClaude Codeに渡す。データは消えていない。
- `Port 8501 is in use`: 別の黒い画面で動いている。そちらを閉じてから再実行。
