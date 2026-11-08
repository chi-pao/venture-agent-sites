"""家族そろいの場面＋司会者のアップを、1秒25コマでなめらかにつなぐ映像（992×992）を作る。"""
import json, subprocess, numpy as np, os
from PIL import Image, ImageFilter, ImageDraw
G = os.path.dirname(os.path.abspath(__file__)) + '/'
V3 = G + '../v3/'
FPS, OUT = 25, 992
tl = json.load(open(V3 + 'tl.json'))
T = tl['total']; segs = tl['tl']
B = json.load(open(G + 'boxes.json'))
base = Image.open(G + '../fam.png').convert('RGB')
CENTER = {'kenji': (330, 330), 'miho': (610, 380), 'sota': (930, 380), 'hana': (1270, 430)}
WIDE = (768, 768, 1536)
BLUR = base.resize((1536, 1536)).filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v*0.6))
REACT = {'07': 'joy', '08': 'surp', '14': 'surp'}
RIMG = {k: Image.open(G + k + '.png').convert('RGB') for k in ('joy', 'surp')}
RX = {'kenji': 700, 'miho': 1400, 'sota': 2000, 'hana': 2700}
def kind(s): return 'host' if s['who'] == 'host' else ('react' if s.get('clip') in REACT else 'group')
def react_frame(t, s):
    im = RIMG[REACT[s['clip']]]; d = t - s['t0']; W = im.size[0]
    cx0 = W/2; cx1 = RX.get(s['who'], W/2)
    cx = cx1; cw = 1024 - 50*ease(d/1.5)
    cy = 512
    cx = min(max(cx, cw/2), W-cw/2); cy = min(max(cy, cw/2), 1024-cw/2)
    return im.transform((OUT, OUT), Image.EXTENT, (cx-cw/2, cy-cw/2, cx+cw/2, cy+cw/2), Image.BICUBIC)

def frames(f):
    w, h = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', f], capture_output=True, text=True).stdout.strip().split(','))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-r', str(FPS), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return [Image.fromarray(x) for x in np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)]

cache = {}
import wave
ENV = {}
def env(n):
    if n not in ENV:
        w = wave.open(V3 + f'{n}.wav'); sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
        hop = sr // FPS; e = np.array([np.sqrt(np.mean(a[i:i+hop]**2)) if len(a[i:i+hop]) else 0 for i in range(0, len(a), hop)])
        e = e / (e.max() or 1); e = np.convolve(e, np.ones(3)/3, 'same'); ENV[n] = e
    return ENV[n]
def clip(path):
    if path not in cache: cache[path] = frames(path)
    return cache[path]

def mask(w, h):
    m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((w*.1, h*.04, w*.9, h*.96), radius=int(w*.2), fill=255)
    return m.filter(ImageFilter.GaussianBlur(w*.05))
M = {k: mask(b[2]-b[0], b[3]-b[1]) for k, b in B.items()}

def pingpong(lst, i):
    n = len(lst); p = i % (2*n-2) if n > 1 else 0
    return lst[p if p < n else 2*n-2-p]

ease = lambda x: (lambda y: y*y*(3-2*y))(min(1, max(0, x)))

def cam_for(s):
    if s['who'] in CENTER and not s.get('count'):
        cx, cy = CENTER[s['who']]; return (768 + (cx-768)*0.5, 768, 1180)
    return WIDE

def group_frame(t, s, i):
    im = base.copy()
    for k, b in B.items():
        if s['who'] == k and not s.get('count') and os.path.exists(G + f"clips/{s['clip']}.mp4"):
            fr = clip(G + f"clips/{s['clip']}.mp4"); fr = fr[min(int((t-s['t0'])*FPS), len(fr)-1)]
        else:
            fr = pingpong(clip(G + f'clips/idle-{k}.mp4'), i + 17*list(B).index(k))
        fr = fr.resize((b[2]-b[0], b[3]-b[1]), Image.LANCZOS)
        ph = list(B).index(k)*1.7
        if s['who'] == k and not s.get('count'):
            e = env(s['clip']); j = min(int((t-s['t0'])*FPS), len(e)-1); lv = e[j] if j >= 0 else 0
            ang = 1.6*lv*np.sin(t*7+ph); dy = 6*lv
        else:
            ang = 0.5*np.sin(t*1.3+ph); dy = 2.5*np.sin(t*1.1+ph)
        fr = fr.rotate(ang, resample=Image.BICUBIC, center=(fr.size[0]/2, fr.size[1]*0.95), translate=(0, dy), fillcolor=None)
        im.paste(fr, tuple(b[:2]), M[k])
    return im

def view(im, cx, cy, cw, shake=0):
    c = BLUR.copy(); c.paste(im, (0, 256)); im = c
    cx = min(max(cx, cw/2), 1536-cw/2); cy = min(max(cy, cw/2), 1536-cw/2)
    return im.transform((OUT, OUT), Image.EXTENT, (cx-cw/2, cy-cw/2, cx+cw/2, cy+cw/2), Image.BICUBIC)

def host_frame(t, s):
    fr = clip(V3 + f"clips/{s['clip']}.mp4"); k = (t - s['t0']) / s['len']
    f = fr[min(int((t-s['t0'])*FPS), len(fr)-1)]
    w = f.size[0]; cw = w*(1 - 0.04*ease(k)); c = w/2
    return f.transform((OUT, OUT), Image.EXTENT, (c-cw/2, c-cw/2*1.0, c+cw/2, c+cw/2), Image.BICUBIC)

def render(t, i):
    idx = max(j for j, s in enumerate(segs) if s['t0'] <= t + 1e-9); s = segs[idx]
    if s['who'] == 'host':
        return host_frame(t, s)
    if kind(s) == 'react':
        return react_frame(t, s)
    # camera: ease from previous family/wide camera to this one
    prev = WIDE
    for p in reversed(segs[:idx]):
        if kind(p) == 'group': prev = cam_for(p); break
    cur = cam_for(s); k = ease((t - s['t0']) / 1.5)
    cx, cy, cw = [a + (b-a)*k for a, b in zip(prev, cur)]
    if s.get('count'): cw -= 30*(t - s['t0'])
    shake = 0
    pass
    return view(group_frame(t, s, i), cx, cy, cw, shake)

def blended(t, i):
    """場面が司会⇔家族で切り替わる所は0.3秒かけて重ねる。"""
    a = render(t, i)
    for s in segs:
        d = t - s['t0']
        if 0 <= d < 0.45:
            j = segs.index(s)
            if j and kind(segs[j-1]) != kind(s):
                b = render(s['t0'] - 0.001, i)
                return Image.blend(b, a, ease(d/0.45))
    return a

N = int(T*FPS)
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OUT}x{OUT}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', G + 'track25.mp4'], stdin=subprocess.PIPE)
for i in range(N):
    p.stdin.write(blended(i/FPS, i).tobytes())
p.stdin.close(); p.wait(); print('track ok', N)
