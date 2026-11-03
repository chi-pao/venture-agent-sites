"""note の下書き（ops/note/drafts/*.md）から、コピーして貼るだけの投稿キット（HTML）を作る。

  python tools/note_kit.py ops/note/drafts/2026-11-03-01.md ops/note/images/01-header.png out.html
"""
import base64
import html
import io
import re
import sys

from PIL import Image


def inline(t):
    t = html.escape(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    return re.sub(r'(https://\S+)', r'<a href="\1">\1</a>', t)


def to_html(body):
    out, lst, para = [], None, []

    def flush():
        if para:
            out.append('<p>' + '<br>'.join(inline(x) for x in para) + '</p>')
            para.clear()

    def endlist():
        nonlocal lst
        if lst:
            out.append(f'</{lst}>')
            lst = None
    for line in body.strip().split('\n'):
        if not line.strip():
            flush(); endlist(); continue
        if line.strip() == '---':
            flush(); endlist(); out.append('<hr>'); continue
        if line.startswith('## '):
            flush(); endlist(); out.append('<h2>' + inline(line[3:]) + '</h2>'); continue
        m = re.match(r'^(- |\d+\. )(.*)', line)
        if m:
            flush()
            kind = 'ol' if m.group(1)[0].isdigit() else 'ul'
            if lst != kind:
                endlist(); out.append(f'<{kind}>'); lst = kind
            out.append('<li>' + inline(m.group(2)) + '</li>'); continue
        endlist(); para.append(line)
    flush(); endlist()
    return '\n'.join(out)


def main(draft, image, dest):
    src = open(draft, encoding='utf-8').read()
    meta, body = src.split('\n---\n', 1)
    title = re.search(r'- 題名: (.+)', meta).group(1).strip()
    tags = re.search(r'- ハッシュタグ: (.+)', meta).group(1).strip()
    number = re.search(r'#(\d+)', title)
    buf = io.BytesIO()
    Image.open(image).convert('RGB').save(buf, 'JPEG', quality=85)
    img = base64.b64encode(buf.getvalue()).decode()
    page = TEMPLATE.format(n=number.group(1) if number else '', img=img, title=html.escape(title),
                           article=to_html(body), tags=html.escape(tags))
    open(dest, 'w', encoding='utf-8').write(page)


TEMPLATE = open(__file__.rsplit('/', 1)[0] + '/note_kit_template.html', encoding='utf-8').read()

if __name__ == '__main__':
    main(*sys.argv[1:4])
