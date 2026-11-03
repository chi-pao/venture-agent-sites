#!/usr/bin/env bash
# ElectricLogo（React Bits, JS-CSS 版）を、React を使っていないこのサイト用に1ファイルへまとめる。
# 依存: react@18.3.1 react-dom@18.3.1 ogl@^1.0.11（部品の指定）と esbuild。CSS は style.css に入れてあるので取り込まない。
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
cd "$work"
npm init -y >/dev/null
npm install --no-audit --no-fund react@18.3.1 react-dom@18.3.1 ogl@1.0.11 esbuild@0.24.2 >/dev/null
cp "$here"/checker-site/src/electric-logo/* .
npx esbuild mount.jsx --bundle --format=esm --minify --loader:.css=empty --jsx=automatic \
  --define:process.env.NODE_ENV='"production"' --outfile="$here/checker-site/vendor/electric-logo.js"
echo "built checker-site/vendor/electric-logo.js"
