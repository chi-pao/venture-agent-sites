# -*- coding: utf-8 -*-
"""ノボログ：投稿に付ける「写真カード」と「紹介動画」を作り、公開場所に置く。

- 写真カード（紹介しない投稿用）：ノボログの色（黒・白・黄）で、題と要点を大きく見せる画像。自分で作る画像なので文字を入れてよい。
- 紹介動画（紹介の1本目用、10〜15秒）：
    表紙（自分で作った文字の画面）→ 楽天の商品写真（加工しない・文字を重ねない）→ 終わりの画面
  楽天の写真には文字を重ねない、切り抜かない（楽天アフィリエイトの決まり）。写真は余白をつけて全体を見せる。
- 公開場所：GitHub の media/noborog ブランチ → Cloudflare Pages
    https://media-noborog.venture-agent-sites.pages.dev/<ファイル>
  Threads は投稿するときにここから読み込む。置くのは「承認済み」の投稿の分だけ。検索には出ない（robots.txt）。

使い方:
  py threads_media.py make 1117          その日の候補に、カードと動画を作る（公開はしない）
  py threads_media.py upload             承認済みの投稿の画像・動画を公開場所に置く
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import threads as T  # noqa: E402

W, H = 1080, 1350
BG, FG, ACCENT, SUB, PHOTO_BG = (17, 17, 17), (255, 255, 255), (255, 208, 0), (170, 170, 170), (255, 255, 255)
FONT_B = "C:/Windows/Fonts/BIZ-UDGothicB.ttc"
FONT_R = "C:/Windows/Fonts/BIZ-UDGothicR.ttc"
BRANCH = "media/noborog"
HOST = "https://media-noborog.venture-agent-sites.pages.dev"
MEDIA_DIR = T.DATA / "media"
UA = {"User-Agent": "Mozilla/5.0 (compatible; noborog-media)"}


class MediaError(RuntimeError):
    pass


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise MediaError("画像を作る部品（Pillow）がありません: py -m pip install --user pillow") from None
    return Image, ImageDraw, ImageFont


def font(size, bold=True):
    _, _, ImageFont = _pil()
    for path in ([FONT_B, "C:/Windows/Fonts/YuGothB.ttc"] if bold else [FONT_R, "C:/Windows/Fonts/YuGothR.ttc"]):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


NO_HEAD = "。、，．・」』）〕】！？ー～…っゃゅょァィゥェォッャュョ"


EMOJI_RE = re.compile("[🀀-🫿☀-➿⬀-⯿️‍]")


def wrap(draw, text, fnt, width):
    """日本語を、幅に収まるように1文字ずつ折り返す。絵文字はフォントにないので消す（□になるため）。"""
    text = EMOJI_RE.sub("", text).rstrip()
    lines = []
    for para in text.split("\n"):
        line = ""
        for ch in para:
            if draw.textlength(line + ch, font=fnt) > width and line and ch not in NO_HEAD:
                lines.append(line)
                line = ch
            else:
                line += ch
        lines.append(line)
    return lines


def draw_block(draw, xy, text, fnt, width, fill, gap=1.35, max_lines=None):
    x, y = xy
    lines = wrap(draw, text, fnt, width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    step = int(fnt.size * gap)
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += step
    return y


def fit_cover(img, w=W, h=H):
    """自分で作った AI 画像を、枠いっぱいに合わせる（AI 画像なので切り取ってよい）。"""
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s + 0.5), int(img.height * s + 0.5)))
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def shade(img, top=0.25, bottom=0.8):
    """文字が読めるように、上は薄く・下は濃く暗くする。"""
    Image, _, _ = _pil()
    grad = Image.new("L", (1, H))
    for yy in range(H):
        grad.putpixel((0, yy), int(255 * (top + (bottom - top) * yy / H)))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    black.putalpha(grad.resize((W, H)))
    out = img.convert("RGBA")
    out.alpha_composite(black)
    return out


def base(label="", bg=None):
    Image, ImageDraw, _ = _pil()
    if bg is not None:
        img = shade(fit_cover(bg.convert("RGB")), 0.45, 0.75)
    else:
        img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    # 左上のラベル（黄色）
    if label:
        f = font(40)
        tw = d.textlength(label, font=f)
        d.rounded_rectangle((72, 72, 72 + tw + 48, 72 + 72), radius=36, fill=ACCENT)
        d.text((96, 84), label, font=f, fill=BG)
    # 右下のロゴ
    f = font(54)
    d.text((W - 72 - d.textlength("nobo", font=f) - 26, H - 120), "nobo", font=f, fill=FG)
    d.ellipse((W - 72 - 20, H - 120 + 36, W - 72, H - 120 + 56), fill=ACCENT)
    d.text((72, H - 108), "@noborog.life", font=font(32, False), fill=SUB)
    return img, d


# ---------- 写真カード ----------
POINT_RE = re.compile(r"^\s*(?:[・■□▶︎→①-⑳]|\d+[.．、)]|総合\d+位)")


def card_spec(it):
    """カードの中身。AI が出した card（style/label/title/points/options）を使う。なければ1本目の文から作る。"""
    if it.get("card_spec"):
        return it["card_spec"]
    lines = [ln.strip() for ln in it["parts"][0].split("\n") if ln.strip()]
    lines = [re.sub(r"^(おはようございます。?|今日もおつかれさまでした。?)", "", ln).strip() for ln in lines]
    lines = [ln for ln in lines if ln and not ln.startswith("おやすみ")]
    title = re.sub(r"^【[^】]*】", "", lines[0]).strip() if lines else it.get("title", "")
    points = [ln for ln in lines[1:] if POINT_RE.match(ln)]
    kind = it.get("kind", "")
    style = "ranking" if kind == "毎日のおなじみ" else "question" if "？" in title and points else \
        "list" if points else "note"
    label = {"ranking": "今日の楽天メモ", "question": "教えて", "list": "保存用"}.get(style, "ノボログ")
    if style == "ranking":
        points = [re.sub(r"^総合(\d+)位\s*", r"\1位|", p) for p in points]
    if style == "note":
        points = lines[1:4]
    return {"style": style, "label": label, "title": title or it.get("title", ""), "points": points[:6]}


def make_card(it, out, bg=None):
    """写真カード。bg に AI 画像を渡すと、それを背景にして文字をのせる。"""
    spec = card_spec(it)
    style = spec.get("style", "list")
    img, d = base(spec.get("label", "ノボログ"), bg)
    y = 220
    tsize = 64 if style != "note" else 70
    y = draw_block(d, (72, y), spec["title"], font(tsize), W - 144, FG, gap=1.3, max_lines=4)
    d.rectangle((72, y + 20, 72 + 120, y + 28), fill=ACCENT)
    y += 76
    points = spec.get("points") or []
    if style == "ranking":
        for pt in points[:5]:
            rank, _, text = pt.partition("|")
            if not text:
                rank, text = "", pt
            d.rounded_rectangle((72, y, W - 72, y + 150), radius=24, fill=(0, 0, 0, 150))
            d.text((104, y + 38), rank, font=font(60), fill=ACCENT)
            draw_block(d, (300, y + 30), text, font(42, False), W - 72 - 300 - 32, FG, gap=1.3, max_lines=2)
            y += 170
            if y > H - 330:
                break
    elif style == "question":
        for k, pt in enumerate(points[:5], 1):
            text = re.sub(r"^\s*(?:[①-⑳]|\d+[.．、)])\s*", "", pt)
            d.rounded_rectangle((72, y, W - 72, y + 116), radius=58, outline=ACCENT, width=4)
            d.ellipse((96, y + 22, 168, y + 94), fill=ACCENT)
            n = str(k)
            d.text((132 - d.textlength(n, font=font(44)) / 2, y + 32), n, font=font(44), fill=BG)
            draw_block(d, (200, y + 32), text, font(44, False), W - 72 - 200 - 40, FG, max_lines=1)
            y += 140
        draw_block(d, (72, y + 20), "番号だけでも、返信で教えてね", font(40, False), W - 144, SUB)
    elif style == "note":
        for pt in points:
            y = draw_block(d, (72, y), pt, font(44, False), W - 144, SUB, gap=1.5, max_lines=4) + 20
            if y > H - 300:
                break
    else:
        for pt in points:
            if y > H - 300:
                break
            head = re.match(r"^\s*([■□・])", pt)
            text = re.sub(r"^\s*[■□・]\s*", "", pt)
            if head and head.group(1) in "■□":
                d.rectangle((72, y + 14, 92, y + 34), fill=ACCENT)
                y = draw_block(d, (112, y), text, font(48), W - 184, FG, gap=1.35, max_lines=2) + 8
            else:
                y = draw_block(d, (112 if pt.startswith("→") else 72, y), text, font(42, False),
                               W - 184, SUB if pt.startswith("→") else FG, gap=1.4, max_lines=3) + 18
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out


def make_ba_image(it, out, before, after, photo):
    """紹介の1本目の1枚目（使う前と後）：つかみの言葉 → 左「いまは…」右「使うと（イメージ）」の2枚の絵 → 楽天の商品写真。
    AI の絵は「イメージ」と書き、商品の本当の姿は下の楽天の写真で見せる（写真は縮小だけ・文字を重ねない）。"""
    Image, ImageDraw, _ = _pil()
    from PIL import ImageEnhance
    img = ImageEnhance.Brightness(blur_bg(before)).enhance(0.45).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    f = font(34)
    label = "楽天で見つけた物"
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((60, 50, 60 + tw + 40, 50 + 56), radius=28, fill=ACCENT)
    d.text((80, 60), label, font=f, fill=BG)
    d.rounded_rectangle((W - 60 - 82, 50, W - 60, 106), radius=28, fill=(0, 0, 0, 160))
    d.text((W - 60 - 61, 60), "PR", font=f, fill=FG)
    no_emoji = re.compile("[\U00010000-\U0010FFFF\uFE0E\uFE0F\u200D\u2600-\u27BF]")
    lines = [no_emoji.sub("", ln).strip() for ln in it["parts"][0].split("\n") if ln.strip()]
    fh = font(56)
    y = 132
    for ln in [w for ln in lines[:2] for w in wrap(d, ln, fh, W - 120)][:3]:
        d.text((60, y), ln, font=fh, fill=FG, stroke_width=2, stroke_fill=(0, 0, 0, 170))
        y += 74
    # 使う前と後の2枚
    top, ph, pw, gap = y + 22, 400, 465, 30
    for k, (pic, tag, color, ink) in enumerate(((before, "いまは…", (0, 0, 0, 175), FG),
                                                (after, "使うと（イメージ）", ACCENT, BG))):
        x = 60 + k * (pw + gap)
        tile = fit_cover(pic.convert("RGB"), pw, ph)
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=26, fill=255)
        img.paste(tile, (x, top), mask)
        ft = font(32)
        tw = d.textlength(tag, font=ft)
        d.rounded_rectangle((x + 14, top + 14, x + 14 + tw + 32, top + 64), radius=25, fill=color)
        d.text((x + 30, top + 22), tag, font=ft, fill=ink)
    cx, cy = W // 2, top + ph // 2
    d.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=ACCENT)
    d.polygon([(cx - 10, cy - 18), (cx + 16, cy), (cx - 10, cy + 18)], fill=BG)
    y = top + ph + 18
    text = no_emoji.sub("", str(it.get("after_text") or "")).strip()
    if text:
        fa = font(44)
        d.text(((W - d.textlength(text, font=fa)) // 2, y), text, font=fa, fill=ACCENT)
        y += 62
    # 楽天の写真：白い台の上に、加工せず全体を置く
    box = (90, y + 14, W - 90, H - 66)
    bw, bh = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle(box, radius=26, fill=PHOTO_BG)
    scale = min((bw - 30) / photo.width, (bh - 30) / photo.height)
    p = photo.resize((max(1, int(photo.width * scale)), max(1, int(photo.height * scale))))
    img.paste(p, (box[0] + (bw - p.width) // 2, box[1] + (bh - p.height) // 2))
    d.text((92, H - 52), "写真：楽天の商品ページより　絵：AI のイメージ", font=font(26, False), fill=SUB)
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out


def make_hook_image(it, out, bg, photo=None, after=None):
    """紹介の1本目の1枚目：その商品の困りごとの AI の場面（上）＋つかみの言葉＋楽天の商品写真（下の白い台）。
    楽天の写真は縮小だけして全体を見せ、文字は写真の外にだけ置く（楽天アフィリエイトの決まり）。
    写真が取れないときは、AI の場面に言葉をのせただけの画像にする。順位は入れない（出す日には変わるため）。"""
    if photo is None:
        urls = it.get("images") or []
        try:
            photo = fetch_image(urls[0]) if urls else None
        except Exception:
            photo = None
    if photo is not None and after is not None:
        return make_ba_image(it, out, bg, after, photo)
    if photo is None:
        img = fit_cover(bg.convert("RGB")).convert("RGBA")
        img.alpha_composite(hook_overlay(it, rank=False))
        img.convert("RGB").save(out, "JPEG", quality=90)
        return out
    Image, ImageDraw, _ = _pil()
    img = fit_cover(bg.convert("RGB")).convert("RGBA")
    # 上半分の言葉が読めるように、上から下へ暗くする
    grad = Image.new("L", (1, H))
    for yy in range(H):
        grad.putpixel((0, yy), int(70 + 150 * min(1, yy / (H * 0.42))))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shadow.putalpha(grad.resize((W, H)))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img, "RGBA")
    f = font(36)
    label = "楽天で見つけた物"
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((60, 54, 60 + tw + 44, 54 + 60), radius=30, fill=ACCENT)
    d.text((82, 64), label, font=f, fill=BG)
    d.rounded_rectangle((W - 60 - 86, 54, W - 60, 114), radius=30, fill=(0, 0, 0, 160))
    d.text((W - 60 - 64, 64), "PR", font=f, fill=FG)
    no_emoji = re.compile("[\U00010000-\U0010FFFF︎️‍☀-➿]")
    lines = [no_emoji.sub("", ln).strip() for ln in it["parts"][0].split("\n") if ln.strip()]
    fh = font(64)
    hl = [w for ln in lines[:2] for w in wrap(d, ln, fh, W - 120)][:5]
    y = 150
    for ln in hl:
        d.text((60, y), ln, font=fh, fill=FG, stroke_width=2, stroke_fill=(0, 0, 0, 170))
        y += 84
    d.rectangle((60, y + 12, 180, y + 20), fill=ACCENT)
    # 楽天の写真：白い台の上に、加工せず全体を置く
    top = max(y + 50, 560)
    box = (90, top, W - 90, H - 70)
    bw, bh = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle((box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10), radius=30, fill=(0, 0, 0, 90))
    d.rounded_rectangle(box, radius=30, fill=PHOTO_BG)
    scale = min((bw - 40) / photo.width, (bh - 40) / photo.height)
    p = photo.resize((max(1, int(photo.width * scale)), max(1, int(photo.height * scale))))
    img.paste(p, (box[0] + (bw - p.width) // 2, box[1] + (bh - p.height) // 2))
    d.text((92, H - 56), "写真：楽天の商品ページより", font=font(28, False), fill=SUB)
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out


# ---------- 紹介動画 ----------
def fetch_image(url):
    Image, _, _ = _pil()
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def blur_bg(bg):
    """AI 画像をぼかして明るめにした背景（商品写真の後ろに敷く）。"""
    from PIL import ImageFilter, ImageEnhance
    b = fit_cover(bg.convert("RGB")).filter(ImageFilter.GaussianBlur(28))
    return ImageEnhance.Brightness(b).enhance(0.8)


def photo_frame(photo, n, total, bg=None):
    """楽天の写真を、加工せず縮小だけして、白い台の上に全体を置く。文字は写真の外にだけ置く。"""
    Image, ImageDraw, _ = _pil()
    img = blur_bg(bg).convert("RGBA") if bg is not None else Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    box = (70, 150, W - 70, H - 190)
    bw, bh = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle((box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10), radius=32, fill=(0, 0, 0, 70))
    d.rounded_rectangle(box, radius=32, fill=PHOTO_BG)
    scale = min((bw - 48) / photo.width, (bh - 48) / photo.height)
    p = photo.resize((max(1, int(photo.width * scale)), max(1, int(photo.height * scale))))
    img.paste(p, (box[0] + (bw - p.width) // 2, box[1] + (bh - p.height) // 2))
    f = font(34)
    label = f"楽天の商品ページの写真　{n}/{total}"
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((72, 70, 72 + tw + 44, 70 + 60), radius=30, fill=(0, 0, 0, 150))
    d.text((94, 80), label, font=f, fill=FG)
    pr = "PR"
    d.rounded_rectangle((W - 72 - 90, 70, W - 72, 130), radius=30, fill=(0, 0, 0, 150))
    d.text((W - 72 - 66, 80), pr, font=f, fill=FG)
    d.text((72, H - 150), "くわしくは2本目のリンクから", font=font(40), fill=FG)
    return img


def hook_overlay(it, rank=True):
    """AI の場面の上にのせる文字（つかみ・順位・PR）。下ほど暗くして読みやすくする。"""
    Image, ImageDraw, _ = _pil()
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H))
    for yy in range(H):
        a = 0 if yy < H * 0.35 else int(215 * (yy - H * 0.35) / (H * 0.65))
        grad.putpixel((0, yy), a)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shadow.putalpha(grad.resize((W, H)))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img, "RGBA")
    p = it.get("product") or {}
    label = f"楽天 {p.get('genre') or '総合'} {p['rank']}位" if rank and p.get("rank") else "楽天で見つけた物"
    label = re.sub(r"（.*?）", "", label)
    f = font(40)
    tw = d.textlength(label, font=f)
    d.rounded_rectangle((72, 72, 72 + tw + 48, 144), radius=36, fill=ACCENT)
    d.text((96, 84), label, font=f, fill=BG)
    d.rounded_rectangle((W - 72 - 90, 72, W - 72, 144), radius=36, fill=(0, 0, 0, 150))
    d.text((W - 72 - 68, 84), "PR", font=f, fill=FG)
    # 絵文字は字体にないので画像には入れない（文の方には残る）
    no_emoji = re.compile("[\U00010000-\U0010FFFF\uFE0E\uFE0F\u200D\u2600-\u27BF]")
    lines = [re.sub(r"^【|】$", "", no_emoji.sub("", ln).strip()) for ln in it["parts"][0].split("\n") if ln.strip()]
    hl = [w for ln in lines[:2] for w in wrap(d, ln, font(80), W - 144)][:5]
    y = H - 170 - int(80 * 1.3) * len(hl)
    for ln in hl:
        d.text((72, y), ln, font=font(80), fill=FG, stroke_width=2, stroke_fill=(0, 0, 0, 160))
        y += int(80 * 1.3)
    d.rectangle((72, y + 18, 212, y + 28), fill=ACCENT)
    return img


def after_overlay(it):
    """使った後の場面にのせる文字：「使うと（イメージ）」と、変わったことのひとこと。"""
    Image, ImageDraw, _ = _pil()
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("L", (1, H))
    for yy in range(H):
        grad.putpixel((0, yy), 0 if yy < H * 0.5 else int(200 * (yy - H * 0.5) / (H * 0.5)))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shadow.putalpha(grad.resize((W, H)))
    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img, "RGBA")
    f = font(40)
    tag = "使うと（イメージ）"
    tw = d.textlength(tag, font=f)
    d.rounded_rectangle((72, 72, 72 + tw + 48, 144), radius=36, fill=ACCENT)
    d.text((96, 84), tag, font=f, fill=BG)
    d.rounded_rectangle((W - 72 - 90, 72, W - 72, 144), radius=36, fill=(0, 0, 0, 150))
    d.text((W - 72 - 68, 84), "PR", font=f, fill=FG)
    no_emoji = re.compile("[\U00010000-\U0010FFFF\uFE0E\uFE0F\u200D\u2600-\u27BF]")
    text = no_emoji.sub("", str(it.get("after_text") or "")).strip()
    if text:
        hl = wrap(d, text, font(80), W - 144)[:3]
        y = H - 190 - 104 * len(hl)
        for ln in hl:
            d.text((72, y), ln, font=font(80), fill=FG, stroke_width=2, stroke_fill=(0, 0, 0, 160))
            y += 104
        d.rectangle((72, y + 18, 212, y + 28), fill=ACCENT)
    return img


def end_frame(it, bg=None):
    Image, ImageDraw, _ = _pil()
    img = shade(fit_cover(bg.convert("RGB")), 0.55, 0.8) if bg is not None else Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    f = font(40)
    d.rounded_rectangle((72, 72, 72 + 90, 144), radius=36, fill=ACCENT)
    d.text((96, 84), "PR", font=f, fill=BG)
    y = draw_block(d, (72, 420), "くわしくは\n返信（2本目）の\n楽天市場のページへ", font(82), W - 144, FG, gap=1.35)
    d.rectangle((72, y + 30, 212, y + 40), fill=ACCENT)
    draw_block(d, (72, y + 90), "価格・サイズ・届く日は\n商品ページで確かめてね", font(46, False), W - 144, FG)
    f = font(54)
    d.text((W - 72 - d.textlength("nobo", font=f) - 26, H - 120), "nobo", font=f, fill=FG)
    d.ellipse((W - 72 - 20, H - 84, W - 72, H - 64), fill=ACCENT)
    return img


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MediaError("動画を作る道具（ffmpeg）が見つかりません")
    return exe


def _ff(args):
    r = subprocess.run([ffmpeg(), "-y", "-loglevel", "error", *args], capture_output=True, text=True,
                       encoding="utf-8")
    if r.returncode != 0:
        raise MediaError(f"動画を作れませんでした: {r.stderr[:300]}")


def make_video(it, out, clip_frames, bg, photos=4, small=None, after_frames=None):
    """使う前の場面（約3秒・つかみの文字つき）→ 使った後の場面（約3秒・あれば）→ 楽天の商品写真（各1.8秒）→ 終わりの画面。
    clip_frames / after_frames: AI 動画のコマ（PNG の連番）。bg: 使う前の場面の静止画。"""
    urls = (it.get("images") or [])[:photos]
    if not urls:
        raise MediaError("写真がないので動画を作れません")
    fade = 0.4
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1. AI の場面に文字をのせた動画
        hook_overlay(it, rank=False).save(tmp / "hook.png")  # 出す日には順位が変わるので入れない
        first = Path(clip_frames[0])
        _ff(["-framerate", "24", "-i", str(first.parent / "f%04d.png"), "-i", str(tmp / "hook.png"),
             "-filter_complex",
             f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[s];[s][1:v]overlay=0:0,format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(tmp / "a.mp4")])
        dur_a = len(clip_frames) / 24
        segs = [(tmp / "a.mp4", dur_a, False)]
        if after_frames:
            after_overlay(it).save(tmp / "after.png")
            _ff(["-framerate", "24", "-i", str(Path(after_frames[0]).parent / "f%04d.png"), "-i", str(tmp / "after.png"),
                 "-filter_complex",
                 f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[s];[s][1:v]overlay=0:0,format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(tmp / "b.mp4")])
            segs.append((tmp / "b.mp4", len(after_frames) / 24, False))
        # 2. 写真と終わりの画面
        for i, u in enumerate(urls, 1):
            path = tmp / f"p{i}.png"
            photo_frame(fetch_image(u), i, len(urls), bg).save(path)
            segs.append((path, 1.8, True))
        path = tmp / "end.png"
        end_frame(it, bg).save(path)
        segs.append((path, 2.4, True))
        args = []
        for path, dur, still in segs:
            args += (["-loop", "1", "-t", f"{dur}", "-framerate", "30", "-i", str(path)] if still else ["-i", str(path)])
        total = sum(d for _, d, _ in segs) - fade * (len(segs) - 1)
        args += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        chain = [f"[{i}:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p[s{i}]" for i in range(len(segs))]
        last, offset = "[s0]", 0.0
        for i in range(1, len(segs)):
            offset += segs[i - 1][1] - fade
            trans = "slideleft" if 1 < i < len(segs) - 1 else "fade"
            chain.append(f"{last}[s{i}]xfade=transition={trans}:duration={fade}:offset={offset:.2f}[v{i}]")
            last = f"[v{i}]"
        size = f",scale={small[0]}:{small[1]}" if small else ""
        chain.append(f"{last}format=yuv420p{size}[vout]")
        _ff(args + ["-filter_complex", ";".join(chain), "-map", "[vout]", "-map", f"{len(segs)}:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26" if small else "20", "-r", "30",
                    "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", str(out)])
    return out


# ---------- まとめて作る ----------
DEFAULT_SCENE = "a calm, warm Japanese living room in the evening, soft lamp light, winter"


def make_for(items, video=True, ai=None):
    """各投稿に、AI の場面（画像・動画）を使った写真カード／紹介動画を作る。
    ai: threads_ai モジュール（テストでは差しかえる）。"""
    if ai is None:
        import threads_ai as ai
    Image, _, _ = _pil()
    ai.start()
    made = []
    for it in items:
        folder = MEDIA_DIR / it["id"]
        folder.mkdir(parents=True, exist_ok=True)
        try:
            scene = it.get("scene") or DEFAULT_SCENE
            art = it.get("art", "photo")
            ba = bool(it.get("product") and it.get("after"))  # 使う前 → 使った後 を見せる紹介
            seed = zlib.crc32(it["id"].encode()) % 2**32  # 前と後で同じ種を使い、同じ部屋・同じ人に近づける
            bg_path = folder / "scene.png"
            if not bg_path.exists():
                if ba:
                    ai.image(scene, bg_path, art=art, seed=seed)
                else:
                    ai.image(scene, bg_path, art=art)
            bg = Image.open(bg_path).convert("RGB")
            after = None
            if ba:
                after_path = folder / "after.png"
                if not after_path.exists():
                    ai.image(it["after"], after_path, art=art, seed=seed)
                after = Image.open(after_path).convert("RGB")
            if it.get("product"):
                # つかみの画像（使う前と後＋実物写真）はいつも作る。動画がある日は、動画 → この画像 → 商品写真の順に並ぶ
                out = folder / f"{it['id']}-{'ba' if ba else 'hook'}.jpg"  # 前の画像と名前を分ける（古い物が出ないように）
                make_hook_image(it, out, bg, after=after)
                it["card"] = {"local": str(out.relative_to(T.DATA)), "url": None}
                made.append(out.name)
                if (video or it.get("make_video")) and it.get("images"):
                    frames_dir = folder / "clip"
                    frames = sorted(frames_dir.glob("f*.png")) if frames_dir.exists() else []
                    if not frames:
                        frames = ai.video(bg_path, scene, frames_dir, art=art)
                    after_frames = None
                    if ba:
                        adir = folder / "clip_after"
                        after_frames = sorted(adir.glob("f*.png")) if adir.exists() else []
                        if not after_frames:
                            after_frames = ai.video(folder / "after.png", it["after"], adir, art=art)
                    out = folder / f"{it['id']}{'-ba' if ba else ''}.mp4"
                    make_video(it, out, frames, bg, after_frames=after_frames)
                    make_video(it, folder / "preview.mp4", frames, bg, small=(432, 540), after_frames=after_frames)
                    it["video"] = {"local": str(out.relative_to(T.DATA)), "url": None}
                    made.append(out.name)
            else:
                out = folder / f"{it['id']}.jpg"
                make_card(it, out, bg)
                it["card"] = {"local": str(out.relative_to(T.DATA)), "url": None}
                made.append(out.name)
        except Exception as e:  # 1つ失敗しても、ほかは作る
            it.setdefault("problems", []).append(f"画像・動画を作れませんでした: {str(e)[:160]}")
    return made


# ---------- 公開場所に置く ----------
def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")


def upload(items, cfg, wait_checks=20, push=None, check=None):
    """承認済み（まだ出していない）投稿の画像・動画を、まとめて公開場所に置く。"""
    want = []
    for it in items:
        if it["status"] not in ("承認済み", "失敗"):
            continue
        for key in ("video", "card"):
            m = it.get(key)
            if m and m.get("local"):
                want.append((it, key, T.DATA / m["local"]))
    if not want:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "site"
        stage.mkdir()
        (stage / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        (stage / "_headers").write_text("/*\n  X-Robots-Tag: noindex\n", encoding="utf-8")
        for it, key, path in want:
            if not path.exists():
                raise MediaError(f"{it['id']} のファイルがありません: {path.name}")
            shutil.copy(path, stage / path.name)
        (push or _push)(stage, cfg)
    done = []
    for it, key, path in want:
        url = f"{HOST}/{path.name}"
        if (check or _check)(url, wait_checks):
            it[key]["url"] = url
            done.append(url)
        else:
            raise MediaError(f"公開場所で開けません（まだ準備中かもしれません）: {url}")
    return done


def _push(stage, cfg):
    remote = f"https://github.com/{cfg.get('github_repo', 'chi-pao/venture-agent-sites')}.git"
    steps = [["init", "-q"], ["checkout", "-q", "-b", BRANCH], ["add", "-A"],
             ["-c", "user.name=venture-studio", "-c", "user.email=venture-studio@users.noreply.github.com",
              "commit", "-q", "-m", "ノボログの投稿用の画像・動画"],
             ["push", "-q", "--force", remote, f"HEAD:refs/heads/{BRANCH}"]]
    for step in steps:
        r = _git(step, stage)
        if r.returncode != 0:
            raise MediaError(f"GitHub への送信に失敗（{' '.join(step[:2])}）: {r.stderr.strip()[:300]}")


def _check(url, tries):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method="HEAD"), timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(15)
    return False


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make"); p.add_argument("tag"); p.add_argument("--no-video", action="store_true")
    sub.add_parser("upload")
    a = ap.parse_args(argv)
    items = T.load_queue()
    try:
        if a.cmd == "make":
            chosen = [it for it in items if it["id"].startswith(a.tag + "-") and it["status"] == "候補"]
            made = make_for(chosen, video=not a.no_video)
            T.save_queue(items)
            T.log(f"{a.tag} の画像・動画を{len(made)}件作りました")
        else:
            cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
            done = upload(items, cfg)
            T.save_queue(items)
            T.log(f"画像・動画を{len(done)}件、公開場所に置きました")
    except MediaError as e:
        T.log(f"画像・動画：止まりました: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
