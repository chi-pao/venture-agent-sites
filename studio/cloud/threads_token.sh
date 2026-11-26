#!/usr/bin/env bash
# ノボログの合いことば（Threads のトークン）を、クラウドの中だけで開け閉めする。中身は画面に出さない。
#   open : studio-data/noborog/token.enc → $THREADS_SECRETS_DIR/threads_token.txt（state.json も持ってくる）
#   close: 延長されていたら、かぎをかけ直して token.enc と state.json を書きもどす
# 鍵は環境変数 KEY（GitHub の秘密欄 THREADS_TOKEN_KEY）。手元の threads_cloud.py と同じ形でかぎをかける。
set -eu
mode="$1"
dir="$THREADS_DATA_DIR"; sec="$THREADS_SECRETS_DIR"
mkdir -p "$sec"; chmod 700 "$sec"
keyfile="$sec/key"; printf '%s' "${KEY:?合いことばの鍵（THREADS_TOKEN_KEY）がありません}" > "$keyfile"
args=(enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$keyfile")
if [ "$mode" = open ]; then
  [ -f "$dir/token.enc" ] || { echo "合いことばがまだ置かれていません（手元で py threads.py sync --token）"; exit 1; }
  openssl "${args[@]}" -d -in "$dir/token.enc" -out "$sec/threads_token.txt"
  cp "$dir/state.json" "$sec/threads_state.json" 2>/dev/null || true
  sha256sum "$sec/threads_token.txt" | cut -c1-64 > "$sec/before"
else
  [ -f "$sec/threads_token.txt" ] || exit 0
  if [ "$(sha256sum "$sec/threads_token.txt" | cut -c1-64)" != "$(cat "$sec/before" 2>/dev/null)" ]; then
    openssl "${args[@]}" -in "$sec/threads_token.txt" -out "$dir/token.enc"
    echo "合いことばを延長したので、かぎをかけて保存しました"
  fi
  cp "$sec/threads_state.json" "$dir/state.json" 2>/dev/null || true
fi
rm -f "$keyfile"
