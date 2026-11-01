# Windows実機の確認手順（のぼるさんのPC）

GitHubのWindows環境（`venture-windows-launcher`）では、`update-and-start.cmd`からの更新・起動確認・自動復旧・二重起動防止・再起動・`--rollback`を自動で試験している。
ただし、それはGitHubが用意したWindowsであり、のぼるさんのPCでの確認は別に行う。

## 実機での確認結果（2026-11-01、のぼるさんのPC）
| # | 結果 | 黒い画面・画面の表示 |
|---|---|---|
| 1〜2 | ○ | 古い起動を止めて再起動。`Update installed`（旧`.cmd`のため起動確認なし） |
| 準備 | ○ | `.cmd`を置き換え。`findstr a20b8ec` で新しい起動プログラムの固定を確認 |
| 3 | ○ | 表示版 2026.11.01.2 |
| 4 | ○ | 自動開発の設定: OFF（中断表示なし＝前回もOFF） |
| 5 | 保留 | 自動運転はまだ開始しない方針のため未実施 |
| 6 | ○ | 2つ目の起動で `Already running` |
| 7 | ○ | `Already up to date` で再起動 |
| 8 | ○ | `--rollback` で `Previous code restored. Data was not overwritten.`（表示版の番号は未記録） |
| 9 | ○ | `Update installed` → `Checking that the new version starts...` → `Startup check passed`（約4秒） |

結論: 更新・起動確認・二重起動防止・再起動・手動ロールバックは**実機確認済み**。継続運転（5）は未確認。起動確認が**失敗した場合の自動復旧**は実機では起きていない（GitHubのWindows環境で試験済み）。

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
