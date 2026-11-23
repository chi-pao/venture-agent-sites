import json,subprocess,os,random
d=json.load(open('tl.json'));T=d['total'];ev=d['ev']
segs=[]
for e in ev:
    end=e['t0']+e['d']
    if segs and segs[-1][0]==e['expr']: segs[-1][2]=end
    else: segs.append([e['expr'],e['t0'],end])
F={'normal':'c02-1-normal','surprised':'c02-2-surprised','angry':'c02-3-angry','tired':'c02-4-tired','happy':'c02-5-happy','typing':'c02-6-typing'}
X=0.2;parts=[]
for i,(e,a,b) in enumerate(segs):
    L=b-a+(X if i<len(segs)-1 else 0)
    src=f'../c02g/{F[e]}.mp4'
    if not os.path.exists(src): src='../c02g/c02-1-normal.mp4'
    o=f'seg{i}.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-i',src,'-filter_complex','[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[p];[p]split[p1][p2];[p1][p2]concat=n=2:v=1,scale=1080:1920:flags=lanczos,crop=1080:1670:0:250,pad=1080:1920:0:0:color=0x05060f,fps=24,setsar=1[v]','-map','[v]','-t',f'{L:.3f}','-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',o],check=True)
    parts.append((o,b-a))
ins=[];fl=[];prev='[0:v]';off=0
for o,_ in parts: ins+=['-i',o]
for i in range(1,len(parts)):
    off+=parts[i-1][1];fl.append(f'{prev}[{i}:v]xfade=transition=fade:duration={X}:offset={off:.3f}[x{i}]');prev=f'[x{i}]'
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(fl),'-map',prev,'-c:v','libx264','-crf','16','-pix_fmt','yuv420p','base.mp4'],check=True)
# sounds
S=[]  # (file,time,vol)
random.seed(3)
for e in ev:
    if e['kind']=='user':
        n=len(e['text']);dur=e['d']-0.5
        for k in range(n*2): S.append(('key.wav',e['t0']+dur*k/(n*2)+random.uniform(-0.02,0.02),0.7))
        S.append(('send.wav',e['t0']+e['d']-0.45,0.6))
    if e['kind']=='ai_type':
        full=sum(len(x) for x in e['lines']);dur=e['d']*0.85
        for k in range(0,full,3): S.append(('tick.wav',e['t0']+dur*k/full,0.5))
    if e.get('ai_jp'):
        full=len(e['ai_jp']);dur=e['d']*0.7
        for k in range(0,full,2): S.append(('tick.wav',e['t0']+dur*k/full,0.4))
    if 'n' in e: S.append((e['n']+'.wav',e['t0'],1.6))
ins=['-i','../q1/bgm.mp3'];fl=[f'[0]atrim=90:{90+T},asetpts=PTS-STARTPTS,volume=0.10,afade=in:d=0.5,afade=out:st={T-2}:d=2[b]'];labs=['[b]'];k=1
for f,t,v in S:
    ins+=['-i',f];ms=max(0,int(t*1000));fl.append(f'[{k}]aresample=44100,volume={v},adelay={ms}|{ms}[x{k}]');labs.append(f'[x{k}]');k+=1
fl.append(''.join(labs)+f'amix=inputs={len(labs)}:normalize=0,atrim=0:{T},alimiter=limit=0.95[a]')
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(fl),'-map','[a]','-ar','44100','mix.m4a'],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-i','base.mp4','-framerate','24','-i','ov/%05d.png','-i','mix.m4a','-filter_complex','[0][1]overlay=0:0[v]','-map','[v]','-map','2:a','-t',str(T),'-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','C02.mp4'],check=True)
print('ok',T,len(S))
