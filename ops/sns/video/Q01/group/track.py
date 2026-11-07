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
WIDE = (768, 520, 1000)

def frames(f):
    w, h = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', f], capture_output=True, text=True).stdout.strip().split(','))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-r', str(FPS), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    return [Image.fromarray(x) for x in np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)]

cache = {}
def clip(path):
    if path not in cache: cache[path] = frames(path)
    return cache[path]

def mask(w, h):
    m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).ellipse((w*.12, h*.06, w*.88, h*.94), fill=255)
    return m.filter(ImageFilter.GaussianBlur(w*.06))
M = {k: mask(b[2]-b[0], b[3]-b[1]) for k, b in B.items()}

def pingpong(lst, i):
    n = len(lst); p = i % (2*n-2) if n > 1 else 0
    return lst[p if p < n else 2*n-2-p]

ease = lambda x: (lambda y: y*y*(3-2*y))(min(1, max(0, x)))

def cam_for(s):
    if s['who'] in CENTER and not s.get('count'):
        cx, cy = CENTER[s['who']]; return (cx, cy+60, 640)
    return WIDE

def group_frame(t, s, i):
    im = base.copy()
    for k, b in B.items():
        if s['who'] == k and not s.get('count') and os.path.exists(G + f"clips/{s['clip']}.mp4"):
            fr = clip(G + f"clips/{s['clip']}.mp4"); fr = fr[min(int((t-s['t0'])*FPS), len(fr)-1)]
        else:
            fr = pingpong(clip(G + f'clips/idle-{k}.mp4'), i + 17*list(B).index(k))
        im.paste(fr.resize((b[2]-b[0], b[3]-b[1]), Image.LANCZOS), tuple(b[:2]), M[k])
    return im

def view(im, cx, cy, cw, shake=0):
    cx += shake; cw = min(cw, 1024); cx = min(max(cx, cw/2), 1536-cw/2); cy = min(max(cy, cw/2), 1024-cw/2)
    return im.transform((OUT, OUT), Image.EXTENT, (cx-cw/2, cy-cw/2, cx+cw/2, cy+cw/2), Image.BICUBIC)

def host_frame(t, s):
    fr = clip(V3 + f"clips/{s['clip']}.mp4"); k = (t - s['t0']) / s['len']
    f = fr[min(int((t-s['t0'])*FPS), len(fr)-1)]
    w = f.size[0]; cw = w*(1 - 0.08*ease(k)); c = w/2
    return f.transform((OUT, OUT), Image.EXTENT, (c-cw/2, c-cw/2*1.0, c+cw/2, c+cw/2), Image.BICUBIC)

def render(t, i):
    idx = max(j for j, s in enumerate(segs) if s['t0'] <= t + 1e-9); s = segs[idx]
    if s['who'] == 'host':
        return host_frame(t, s)
    # camera: ease from previous family/wide camera to this one
    prev = WIDE
    for p in reversed(segs[:idx]):
        if p['who'] != 'host': prev = cam_for(p); break
    cur = cam_for(s); k = ease((t - s['t0']) / 0.7)
    cx, cy, cw = [a + (b-a)*k for a, b in zip(prev, cur)]
    if s.get('count'): cw -= 40*(t - s['t0'])
    shake = 0
    if s['panel'] in ('a1', 'a2') and t - s['t0'] < 0.4: shake = 14*np.sin((t-s['t0'])*60)*(1-(t-s['t0'])/0.4)
    return view(group_frame(t, s, i), cx, cy, cw, shake)

def blended(t, i):
    """場面が司会⇔家族で切り替わる所は0.3秒かけて重ねる。"""
    a = render(t, i)
    for s in segs:
        d = t - s['t0']
        if 0 <= d < 0.3:
            j = segs.index(s)
            if j and (segs[j-1]['who'] == 'host') != (s['who'] == 'host'):
                b = render(s['t0'] - 0.001, i)
                return Image.blend(b, a, ease(d/0.3))
    return a

N = int(T*FPS)
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OUT}x{OUT}', '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', G + 'track25.mp4'], stdin=subprocess.PIPE)
for i in range(N):
    p.stdin.write(blended(i/FPS, i).tobytes())
p.stdin.close(); p.wait(); print('track ok', N)
