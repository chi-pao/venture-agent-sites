"""Turn approved tasks in ops/tasks/queue.json into instruction sheets for ChatGPT.

Claude Code (SNS lead) writes tasks; the owner approves them by setting status to 承認済み;
this tool checks every task against the publishing rules and writes one self-contained
Markdown sheet per approved task to ops/chatgpt/outbox/. ChatGPT reads the sheet, makes the
draft/image/storyboard, and the owner posts. Nothing here posts, pays, or calls a paid API.

Usage:
  python tools/chatgpt_packets.py --check            # validate the queue (exit 1 on any error)
  python tools/chatgpt_packets.py --render           # check, then write sheets for approved tasks
  python tools/chatgpt_packets.py --utm URL SOURCE CAMPAIGN   # print a URL with UTM tags
"""
import argparse
import json
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / 'ops' / 'tasks' / 'queue.json'
OUTBOX = ROOT / 'ops' / 'chatgpt' / 'outbox'
KINDS = {'sns_post_draft': 'SNS投稿文', 'image_asset': '画像', 'video_script': '動画の絵コンテ',
         'sns_post_schedule': 'SNS予約投稿（画像・文）', 'video_post_schedule': '動画の予約投稿'}
# 予約投稿の依頼書は手書き（ops/chatgpt/outbox/）なので、--render では上書きしない
RENDERED_KINDS = ('sns_post_draft', 'image_asset', 'video_script')
STATUSES = ('承認待ち', '承認済み', '予約済み', '投稿済み', '取消')
CHANNEL_LIMITS = {'X': 140, 'Threads': 500, 'Instagram': 2200, 'TikTok': 2200, 'YouTube': 1000, 'note': 3000}
SECRET = re.compile(r'(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|sk-[A-Za-z0-9]{16,}|[sr]k_(live|test)_|Bearer\s+\S{8,}|api_?key|password)', re.I)
CLAIM = re.compile(r'\d[\d,.]*\s*(人|名|件|%|％|倍|万|億|円|位)')
RULES = (
    '投稿・公開はのぼるさんが行う。あなたは下書き・素材を作るだけ。',
    '「使ってよい事実」以外の事実・数字（利用者数・満足度・効果・実績・順位・金額）を作らない。',
    '参考価格は「目安」。「必ず得する」「損しない」など断定・保証の表現をしない。',
    '広告・アフィリエイトを含む場合は文頭に「PR」と書く。',
    '実在の人物・他社のロゴ・他サービスの画面を使わない。アプリの画面は渡された実際のスクリーンショット・録画だけを使う。',
    'リンクは指定のURLをそのまま使う（短縮・変更しない）。',
)


def utm(url, source, campaign, medium='social'):
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update(utm_source=source, utm_medium=medium, utm_campaign=campaign)
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def load(path=QUEUE):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('tasks'), list):
        raise ValueError('queue.json は {"version": 1, "tasks": [...]} の形式にしてください')
    return data


def check_task(task):
    """Return a list of problems for one task (empty list = OK)."""
    errors = []
    if not isinstance(task, dict):
        return ['タスクが辞書形式ではありません']
    tid = str(task.get('id', ''))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,63}', tid):
        errors.append('id は英数字・-_. の3〜64文字')
    kind = task.get('kind')
    if kind not in KINDS:
        errors.append('kind は ' + ' / '.join(KINDS) + ' のいずれか')
    if task.get('status') not in STATUSES:
        errors.append('status は ' + ' / '.join(STATUSES) + ' のいずれか')
    payload = task.get('payload')
    if not isinstance(payload, dict):
        return errors + ['payload が辞書形式ではありません']
    if SECRET.search(json.dumps(task, ensure_ascii=False)):
        errors.append('認証情報らしき文字列が含まれています')
    facts = payload.get('facts', [])
    if kind in ('sns_post_draft', 'video_script'):
        if not isinstance(facts, list) or not facts or not all(isinstance(f, str) and f.strip() for f in facts):
            errors.append('facts（使ってよい事実）を1件以上の文字列で指定してください')
    for field in ('angle', 'title', 'headline', 'prompt'):
        value = str(payload.get(field, '') if field != 'title' else task.get('title', ''))
        found = CLAIM.search(value)
        if found and not any(found.group(0).strip() in str(f) for f in facts or []):
            errors.append(field + ' に事実（facts）にない数字があります: ' + found.group(0))
    url = payload.get('url')
    if url:
        parsed = urllib.parse.urlsplit(str(url))
        query = dict(urllib.parse.parse_qsl(parsed.query))
        if parsed.scheme != 'https':
            errors.append('url は https で指定してください')
        if kind == 'sns_post_draft' and not {'utm_source', 'utm_medium', 'utm_campaign'} <= set(query):
            errors.append('url に utm_source / utm_medium / utm_campaign を付けてください（--utm で作成できます）')
    if payload.get('affiliate') and payload.get('pr_label') is not True:
        errors.append('広告・アフィリエイトを含むタスクは pr_label: true が必要です')
    if kind == 'sns_post_draft':
        channel = payload.get('channel')
        if channel not in CHANNEL_LIMITS:
            errors.append('channel は ' + ' / '.join(CHANNEL_LIMITS) + ' のいずれか')
        else:
            limit = int(payload.get('max_chars', CHANNEL_LIMITS[channel]))
            if not 20 <= limit <= CHANNEL_LIMITS[channel]:
                errors.append('max_chars は 20〜' + str(CHANNEL_LIMITS[channel]) + '（' + channel + '）')
    if kind == 'image_asset' and len(str(payload.get('prompt', '')).strip()) < 5:
        errors.append('prompt（画像の指示）を5文字以上で指定してください')
    return errors


def check_queue(data):
    problems = {}
    seen = set()
    for task in data['tasks']:
        tid = str(task.get('id', '?')) if isinstance(task, dict) else '?'
        errors = check_task(task)
        if tid in seen:
            errors.append('id が重複しています')
        seen.add(tid)
        if errors:
            problems[tid] = errors
    return problems


def render(task):
    p = task['payload']
    lines = ['# ChatGPTへの依頼: ' + task['title'], '',
             f'- 依頼ID: `{task["id"]}`', f'- 種類: {KINDS[task["kind"]]}', f'- 事業: {p.get("business", "")}',
             '- 発行: Claude Code（司令塔） / 承認: のぼるさん', '', '## 守ること']
    lines += ['- ' + rule for rule in RULES]
    lines += ['', '## 依頼内容']
    if task['kind'] == 'sns_post_draft':
        lines += [f'- SNS: {p["channel"]}（{p.get("max_chars", CHANNEL_LIMITS[p["channel"]])}文字以内）',
                  f'- 切り口: {p.get("angle", "")}', f'- 投稿の型: {p.get("format", "自由")}']
        if p.get('url'):
            lines.append(f'- 入れるリンク（変更しない）: {p["url"]}')
        if p.get('affiliate'):
            lines.append('- 広告・アフィリエイトを含む: 文頭に「PR」')
        lines += ['- 案を3つ作り、それぞれの文字数を書く。']
    elif task['kind'] == 'image_asset':
        lines += [f'- 画像の指示: {p["prompt"]}', f'- サイズ: {p.get("size", "1080x1080")}',
                  f'- 入れる文字: {p.get("headline", "")} / {p.get("subline", "")}',
                  '- 生成画像であることが分かる場合は、投稿時に「AI生成画像」と表示する。']
    else:
        lines += [f'- 長さ: {p.get("duration_sec", 30)}秒 / {p.get("scenes", 4)}場面（縦型）',
                  '- 各場面に「秒数・画面・字幕」を書く。画面はアプリの実際の録画を使う前提。']
    if task['kind'] != 'image_asset':
        lines += ['', '## 使ってよい事実（これ以外は書かない）'] + ['- ' + f for f in p.get('facts', [])]
    lines += ['', '## 返却の形式（このまま埋めて、のぼるさん経由でClaude Codeへ）', '```',
              f'依頼ID: {task["id"]}', '成果物: （投稿文の案3つ / 画像ファイル / 絵コンテ）',
              '守ること6項目の自己確認: （各項目 ○/×）', '投稿した場合のURLと日時: （未投稿なら「未投稿」）',
              '24時間後の実数（表示・いいね・返信・リンククリック。分からない項目は「不明」）:', '```', '']
    return '\n'.join(lines)


def render_outbox(data, outbox=OUTBOX):
    outbox = Path(outbox)
    outbox.mkdir(parents=True, exist_ok=True)
    written = []
    for task in data['tasks']:
        if task.get('status') == '承認済み' and task.get('kind') in RENDERED_KINDS:
            path = outbox / (task['id'] + '.md')
            path.write_text(render(task), encoding='utf-8')
            written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--utm', nargs=3, metavar=('URL', 'SOURCE', 'CAMPAIGN'))
    parser.add_argument('--queue', default=str(QUEUE))
    parser.add_argument('--outbox', default=str(OUTBOX))
    args = parser.parse_args(argv)
    if args.utm:
        print(utm(*args.utm))
        return 0
    data = load(args.queue)
    problems = check_queue(data)
    for tid, errors in problems.items():
        for error in errors:
            print(f'NG {tid}: {error}')
    if problems:
        return 1
    print(f'OK: {len(data["tasks"])}件の依頼はルールを満たしています')
    if args.render:
        for path in render_outbox(data, args.outbox):
            print('作成:', path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
