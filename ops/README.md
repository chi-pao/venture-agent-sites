# 3事業の開発管理（司令塔: Claude Code）

最終更新: 2026-11-01 ／ 管理者: のぼるさん ／ 開発の司令塔: Claude Code ／ SNS・画像・動画: ChatGPT

## 対象事業

| 事業 | リポジトリ | 公開先 | 現在の段階 | 詳細 |
|---|---|---|---|---|
| 自律型AI事業開発システム（事業開発AI） | `chi-pao/venture-agent-sites` の `agent/` | のぼるさんのWindows PC（Streamlit, 8501） | 運用中・正常化作業中 | [agent-system.md](businesses/agent-system.md) |
| お買い得物件チェッカー | `chi-pao/-` | https://okaidokucyekka.streamlit.app | 公開中 | [property-checker.md](businesses/property-checker.md) |
| 旅行計画アプリ（旅のペースノート） | `chi-pao/venture-agent-sites` の `agent/review-products/travel.html` と `functions/api/travel/` | https://venture-agent-sites.pages.dev/agent/review-products/travel | 開発確認版・API接続待ち | [travel-planner.md](businesses/travel-planner.md) |

## 役割分担

| 担当 | 行うこと | 行わないこと |
|---|---|---|
| のぼるさん | 事業の継続判断、製品ごとの発信OK、課金・外部アカウント・APIキーの設定、Windows実機の確認 | — |
| Claude Code（司令塔） | 仕様・開発・修正・テスト・GitHub反映・公開管理・リリース。ChatGPTへの発信内容と方針の指示（`ops/chatgpt/`） | のぼるさんのOKなしの発信許可、課金の発生、未検証機能を完成と扱うこと |
| ChatGPT | `ops/chatgpt/` の指示に従ったSNS投稿、画像生成、動画制作、反応の記録 | コード・仕様の変更、承認されていない投稿、指示にない主張 |

## 変更のルール（全事業共通）

1. 作業は `claude/...` ブランチで行い、mainへは必ずプルリクエスト経由で反映する。
2. 修正前に原因を特定し、修正後にテストを実行する。再発防止のテストを追加し、修正前のコードで失敗することを確認する。
3. CI（`venture-builder-qa`、`venture-windows-launcher`）が合格してからマージする。テストを通すために正常な機能やテストを削除しない。
4. 1つのコミットは1つの目的にする。`git revert <コミット>` で個別に元へ戻せるようにする。
5. Windows版への配布は、mainへ反映後に `agent/release.json` を更新するプルリクエストで行う。PCは次回起動時に自動更新し、起動確認に失敗すれば自動で前の版に戻る。
6. 検証できていない機能は「未検証」「接続待ち」と書き、完成とは扱わない。
7. 追加料金が発生する作業（有料API・有料プラン・広告出稿）は、事前にのぼるさんへ確認する。

## 状態の表記

- **検証済み**: 自動テストまたは実機で、具体的な結果を確認した。
- **CI検証済み・実機未確認**: GitHubの環境では確認したが、のぼるさんのPC・本番環境では未確認。
- **未検証**: 実装はあるが、動作を確認していない。
- **接続待ち**: 外部サービスの設定（キー・DB等）が終わるまで動かない。
- **未着手**: 実装していない。

## 進め方の記録
- [Windows実機の確認手順](WINDOWS_CHECK.md)
- ChatGPTへの指示: [ops/chatgpt/README.md](chatgpt/README.md)
