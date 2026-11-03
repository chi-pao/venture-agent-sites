"""Turn an A8.net link code into an offer on the checker's result screen.

  python tools/add_offer.py <slot id> <file with the pasted A8.net code> [--text 文言] [--prefectures 東京都,神奈川県]

The slot (e.g. sell-rakuuru-house) must already exist in checker-site/offers.json; it keeps its
audience rules (intent, types, prefectures, minAge, priority). The code must be A8.net's own
text-link or banner code: the link has to go to https://px.a8.net/svt/ejp?a8mat=..., the banner
image must come from *.a8.net, and the 1x1 measurement image must be https://*.a8.net/0.gif?a8mat=...
with the same a8mat. Anything else is refused, so a wrong paste cannot put an arbitrary link on
the site. The slot is switched on.
"""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, parse_qs

OFFERS = Path(__file__).resolve().parent.parent / 'checker-site' / 'offers.json'
PREFS = ['北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県', '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
         '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県', '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
         '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県', '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
         '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県']


class Code(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.imgs = []; self.text = ''; self._in_a = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a':
            self.links.append(a.get('href', '')); self._in_a = True
        elif tag == 'img':
            self.imgs.append((a.get('src', ''), a.get('width'), a.get('height'), self._in_a))

    def handle_endtag(self, tag):
        if tag == 'a':
            self._in_a = False

    def handle_data(self, data):
        if self._in_a:
            self.text += data


def a8mat(url):
    return (parse_qs(urlsplit(url).query).get('a8mat') or [''])[0]


def parse(code):
    p = Code(); p.feed(code)
    links = [h for h in p.links if h]
    if len(set(links)) != 1:
        raise ValueError('リンクが1つのコードを貼ってください（見つかったリンク: %d）' % len(set(links)))
    href = links[0]
    u = urlsplit(href)
    if u.scheme != 'https' or u.netloc != 'px.a8.net' or not u.path.startswith('/svt/ejp') or not a8mat(href):
        raise ValueError('A8.net のリンク（https://px.a8.net/svt/ejp?a8mat=...）ではありません')
    pixel = banner = None
    for src, w, h, inside in p.imgs:
        s = urlsplit(src)
        if s.scheme != 'https' or not s.netloc.endswith('.a8.net'):
            raise ValueError('A8.net 以外の画像が含まれています: ' + src)
        if s.path == '/0.gif':
            if a8mat(src) != a8mat(href):
                raise ValueError('計測用の画像とリンクの a8mat が一致しません')
            pixel = src
        elif inside:
            banner = (src, int(w or 0) or None, int(h or 0) or None)
    if not pixel:
        raise ValueError('計測用の画像（https://www○○.a8.net/0.gif?a8mat=...）が見つかりません。コードを全部貼ってください')
    return href, pixel, banner, re.sub(r'\s+', ' ', p.text).strip()


def apply(offers, slot, code, text=None, prefectures=None):
    href, pixel, banner, anchor = parse(code)
    entry = next((o for o in offers['offers'] if o['id'] == slot), None)
    if entry is None:
        raise ValueError('広告枠が見つかりません: ' + slot)
    entry.update(href=href, pixel=pixel, enabled=True)
    if banner:
        entry.update(kind='banner', img=banner[0], width=banner[1] or 320, height=banner[2] or 50, alt=entry['label'] + '（広告）')
    else:
        words = (text or anchor).strip()
        if not words:
            raise ValueError('テキストリンクの文言がありません。--text で指定してください')
        entry.update(kind='text', text=words)
    if prefectures is not None:
        bad = [p for p in prefectures if p not in PREFS]
        if bad:
            raise ValueError('都道府県名が正しくありません: ' + '、'.join(bad))
        entry['prefectures'] = prefectures
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('slot'); ap.add_argument('code_file')
    ap.add_argument('--text'); ap.add_argument('--prefectures')
    a = ap.parse_args()
    offers = json.loads(OFFERS.read_text(encoding='utf-8'))
    prefs = [p.strip() for p in a.prefectures.split(',') if p.strip()] if a.prefectures else None
    try:
        entry = apply(offers, a.slot, Path(a.code_file).read_text(encoding='utf-8'), a.text, prefs)
    except ValueError as exc:
        print('追加できませんでした:', exc); return 1
    OFFERS.write_text(json.dumps(offers, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('追加しました:', entry['id'], entry['label'], entry.get('text') or entry.get('img'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
