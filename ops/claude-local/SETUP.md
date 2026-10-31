# Claude Code と事業開発AIの連携（段階A・B、追加費用なし）

## 段階A: 診断ファイル（2026.11.01.2 以降）
事業開発AIの状態・直近のエラー・比較テストの証拠（生成された画面・失敗時の画面画像）を1つのzipにまとめる。
**DB本体・環境変数・APIキー・保存済みSNS資格情報は含まれない**（秘密情報らしい項目は `***` に置換）。

作り方（どちらでも同じ内容）
- 画面: 「詳細・履歴・運用を開く」→「実行履歴と成果物」→「Claude Code用の診断ファイルを作成」→「診断ファイルを保存」
- 黒い画面: `C:\AI事業開発` で `py code\current.py --export-diagnostics` → `C:\AI事業開発\diagnostics\` に保存される

渡し方: Claude Code（クラウド）のチャットにzipを添付する。GitHubには上げない。

## 段階B: Windows PCで Claude Code を動かす
クラウドの Claude Code はPCのフォルダを読めない（フォルダ共有はMac・Linuxのみ）。PCのデータを直接調べたいときは、PC上で Claude Code を動かす。

1. **Claude Code を入れる**（どちらか）
   - Claude デスクトップアプリ: https://claude.ai/download からインストールし、いつものClaudeアカウントでログイン。Claude Code の画面でフォルダ `C:\AI事業開発` を選ぶ。
   - コマンド版: PowerShellで `irm https://claude.ai/install.ps1 | iex` を実行し、`cd C:\AI事業開発` → `claude` でログイン。
   - **追加費用を出さないため、`ANTHROPIC_API_KEY` は設定しない**（設定するとAPIの従量課金になる）。現在のClaudeプランの利用枠で動く。
2. **Git for Windows**（未導入なら）: https://git-scm.com/download/win 。コード修正をGitHubのプルリクエストで出すときに使う。
3. **安全設定を置く**（GitHubから2つのファイルを保存）
   - `ops/claude-local/CLAUDE.md` → `C:\AI事業開発\CLAUDE.md`
   - `ops/claude-local/settings.json` → `C:\AI事業開発\.claude\settings.json`（`.claude` フォルダを作る）
   - これで、DB・`code\`・`backups\` の変更、自動運転・分野探索・Streamlit起動のコマンドが禁止され、読む・診断を作る操作だけが許可される。
4. **最初の依頼の例**: 「CLAUDE.mdに従って、診断ファイルを作り、制作AIの比較テストが失敗した原因を調べて報告して。何も変更しないで。」

確認状況: 設定ファイルの内容はGitHub上でレビュー済みだが、**Windows実機で禁止ルールが効くことは未確認**。初回に「DBを編集して」と頼み、拒否されることを確かめる。

## 段階C（未着手・費用の判断が必要）
事業開発AIの制作・修正に Claude を直接使う段階。プラン利用枠の消費または従量課金が発生しうるため、のぼるさんの判断後に設計する。
