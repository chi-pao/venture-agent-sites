"""note 連載の「事実メモ」を作る。下書きはこのメモにある事実だけを使う。

  python tools/note_facts.py --since 2026-10-27 > /tmp/facts.md
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def git_log(since):
    out = subprocess.run(['git', 'log', f'--since={since}', '--no-merges', '--pretty=%ad %s', '--date=short'],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def model_facts():
    catalog = json.loads((ROOT / 'checker-site/models/catalog.json').read_text(encoding='utf-8'))
    lines = []
    for key, m in catalog['models'].items():
        metrics = m.get('metrics') or {}
        line = f"- {m.get('name', key)}: 誤差中央値 {metrics.get('median_ape_pct', '不明')}%"
        if 'within20_pct' in metrics:
            line += f" / ±20%以内 {metrics['within20_pct']}%"
        if m.get('validation'):
            line += f"（{m['validation']['trainedThrough']}までで学習、{m['validation']['holdout']}の取引で検証）"
        lines.append(line)
    return lines


def offer_facts():
    offers = json.loads((ROOT / 'checker-site/offers.json').read_text(encoding='utf-8'))
    return [f"- {o.get('label') or o.get('id')}: {'掲載中' if o.get('enabled') else '準備中（提携待ち）'}" for o in offers.get('offers', [])]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--since', required=True)
    a = p.parse_args()
    area_pages = len([p for p in (ROOT / 'checker-site/area').glob('*/index.html') if p.parent.name.isdigit()])
    parts = ['# 事実メモ', '', f'## この期間の変更（{a.since} 以降、git の記録）', *[f'- {l}' for l in git_log(a.since)],
             '', '## 査定モデルの精度（公開中）', *model_facts(),
             '', '## 広告枠', *offer_facts(),
             '', '## サイト', f'- 地域の相場ページ: 市区町村 {area_pages} ページ', '- URL: https://okaidoku-checker.pages.dev/',
             '', '## 収益・訪問数', '- 記録がある場合だけ ops/metrics/ から転記する。記録がなければ「未記録」と書き、数字を作らない。']
    metrics = sorted((ROOT / 'ops/metrics').glob('*.md')) if (ROOT / 'ops/metrics').exists() else []
    if metrics:
        parts += ['', f'### 最新の記録（{metrics[-1].name}）', metrics[-1].read_text(encoding='utf-8')]
    print('\n'.join(parts))


if __name__ == '__main__':
    main()
