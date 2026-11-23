#!/usr/bin/env bash
# データ用の非公開リポジトリに、今の記録を保存して送る。何も変わっていなければ何もしない。
# 使い方: save_data.sh <データのフォルダー> "<ひとこと>"
set -u
dir="$1"; msg="${2:-スタジオの記録}"
cd "$dir" || exit 0
git add -A >/dev/null 2>&1
if git diff --cached --quiet; then
  exit 0
fi
git -c user.name=venture-studio -c user.email=venture-studio@users.noreply.github.com \
  commit -q -m "$msg $(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M')" || exit 0
for i in 1 2 3; do
  if git push -q origin HEAD:main 2>/dev/null; then exit 0; fi
  # 手元（オーナーの判断など）で先に変わっていたら、取り込んでから送り直す（同じ所がぶつかったらクラウド側を優先）
  git pull -q --rebase -X theirs origin main 2>/dev/null || { git rebase --abort 2>/dev/null; break; }
done
echo "データの保存に失敗しました（次の保存でもう一度送ります）"
exit 0
