import json,subprocess,numpy as np,sys
from PIL import Image,ImageFilter,ImageDraw
G='/tmp/claude-0/-home-user-venture-agent-sites/68731e5c-3a0a-5d00-8f66-f41a7327d5b4/scratchpad/g/'
B=json.load(open(G+'boxes.json'));base=Image.open(G+'../fam.png').convert('RGB')
def frames(f):
    w=h=None
    info=subprocess.run(['ffprobe','-v','error','-select_streams','v','-show_entries','stream=width,height','-of','csv=p=0',f],capture_output=True,text=True).stdout.strip().split(',')
    w,h=map(int,info);raw=subprocess.run(['ffmpeg','-v','error','-i',f,'-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True).stdout
    a=np.frombuffer(raw,np.uint8).reshape(-1,h,w,3);return [Image.fromarray(x) for x in a]
F={k:frames(G+k+'.mp4') for k in B}
def mask(w,h):
    m=Image.new('L',(w,h),0);d=ImageDraw.Draw(m);d.ellipse((w*.12,h*.06,w*.88,h*.94),fill=255);return m.filter(ImageFilter.GaussianBlur(w*.06))
M={k:mask(b[2]-b[0],b[3]-b[1]) for k,b in B.items()}
def pick(lst,i):  # ping-pong loop
    n=len(lst);p=i%(2*n-2) if n>1 else 0;return lst[p if p<n else 2*n-2-p]
dur=float(sys.argv[1]);N=int(dur*25);OUT=1080
p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{OUT}x{OUT}','-r','25','-i','-','-i',G+'../v3/05.wav','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-af','apad','-t',str(dur),G+'test.mp4'],stdin=subprocess.PIPE)
for i in range(N):
    im=base.copy()
    for k,b in B.items():
        fr=(F[k][min(i,len(F[k])-1)] if k=='kenji' else pick(F[k],i)).resize((b[2]-b[0],b[3]-b[1]),Image.LANCZOS);im.paste(fr,b[:2],M[k])
    t=i/max(1,N-1);t=t*t*(3-2*t)
    # camera: from wide to slow push toward kenji
    cw=1024-260*t;cx=768-(768-330)*t*0.9;cy=512-(512-420)*t
    box=(cx-cw/2,cy-cw/2,cx+cw/2,cy+cw/2)
    fr=im.transform((OUT,OUT),Image.EXTENT,box,Image.BICUBIC)
    p.stdin.write(fr.tobytes())
p.stdin.close();p.wait();print('ok')
