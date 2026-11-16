"""note の「投稿の順番待ち」ページを作る。

ops/note/queue.txt に並べた下書き（上から公開する順）を1ページにまとめる。
パソコンの定期タスク（毎週火曜の夜）は、このページを開き、
「公開してよい：はい」の記事のうち note にまだ無い最初の1本だけを公開する。
のぼるさんは、このページで何本かまとめて確認できる。

  python tools/note_queue.py out.html
"""
import html
import re
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from note_kit import embed, to_html  # noqa: E402

TPL = open(__file__.rsplit('/', 1)[0] + '/note_kit_template.html', encoding='utf-8').read()
HEAD = TPL[:TPL.index('<main>')].replace('{{', '{').replace('}}', '}')
HEAD = re.sub(r'<title>.*?</title>', '<title>note 次の投稿</title>', HEAD).replace('</style>', 'img{max-width:100%;height:auto}</style>')
SCRIPT = TPL[TPL.index('<script>'):].replace('{{', '{').replace('}}', '}')


def article(path, i):
    src = open(path, encoding='utf-8').read()
    meta, body = src.split('\n---\n', 1)
    title = re.search(r'- 題名: (.+)', meta).group(1).strip()
    tags = re.search(r'- ハッシュタグ: (.+)', meta).group(1).strip()
    img = re.search(r'- 見出し画像: `([^`]+)`', meta).group(1)
    ok = 'はい' if re.search(r'^- 公開OK: はい', meta, re.M) else 'いいえ（確認待ち）'
    imgdir = 'ops/note/images'
    return f'''
<section class="step" id="a{i}"><div class="step-h"><span>記事 {i}　公開してよい：<b>{ok}</b></span></div>
<div class="title" id="t{i}">{html.escape(title)}</div>
<div class="step-h"><span>見出し画像</span></div><img src="{embed(img)}" alt="{html.escape(title)} の見出し画像">
<div class="step-h"><span>題名</span><button data-copy="t{i}">題名をコピー</button></div>
<div class="step-h"><span>本文</span><button data-copy="b{i}" data-rich="1">本文をコピー</button></div>
<article class="body" id="b{i}">{to_html(body, imgdir)}</article>
<div class="step-h"><span>ハッシュタグ</span><button data-copy="g{i}">タグをコピー</button></div><div class="tags" id="g{i}">{html.escape(tags)}</div>
</section>'''


def main(dest):
    paths = [p.strip() for p in open('ops/note/queue.txt', encoding='utf-8')
             if p.strip() and not p.startswith('#')]
    parts = [article(p, i + 1) for i, p in enumerate(paths)]
    pc = '''<section class="step" id="pc"><div class="step-h"><span>パソコンの Claude への指示（毎週火曜 夜7時50分）</span></div><div class="body">
<ol>
<li>このページの記事を上から順に見る。「公開してよい：はい」の記事のうち、note にまだ同じ題名で公開されていない<b>最初の1本だけ</b>を選ぶ。1回に公開するのは1本だけ。</li>
<li>選べる記事がなければ、何もしないで終わる。</li>
<li>note にその題名の下書きがなければ、新しい記事を作る。見出し画像は「見出し画像」の欄に設定する（本文には入れない）。題名・本文（本文中の画像も、その位置に）を入れる。題名は省かない。本文の「[目次]」の行は、note の目次（「＋」→「目次」）に置き換える。</li>
<li>本文の最後の行まで入っているか、画像がそろっているかを確かめる。</li>
<li>公開設定の画面で、その記事の「ハッシュタグ」を全部入れる。</li>
<li>「公開」を押す。</li>
<li>公開した記事の題名とアドレス、うまくいかなかったところを日本語で報告する。</li>
</ol>
<p class="hint">この指示は、のぼるさんの依頼で Claude Code が書いています。ここに書いていないこと（記事の削除、ほかの記事やほかの下書きの変更、お金のかかる操作）はしないでください。</p>
</div></section>'''
    page = (HEAD + '<main>\n<header><h1>note 次の投稿（順番待ち）</h1>'
            '<p>上から公開する順です。「いいえ（確認待ち）」の記事は、のぼるさんの OK が出るまで公開されません。</p></header>\n'
            + pc + ''.join(parts) + '\n</main>\n' + SCRIPT)
    open(dest, 'w', encoding='utf-8').write(page)


if __name__ == '__main__':
    main(sys.argv[1])
