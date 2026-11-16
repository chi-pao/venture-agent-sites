import json,subprocess,os
d=json.load(open('tl.json'));tl=d['tl'];T=0.25;FPS=30;W=992
os.makedirs('seg',exist_ok=True)
for i,s in enumerate(tl):
    L=s['len']+(T if i<len(tl)-1 else 0)
    start=0.4 if s['clip'].startswith('idle') else 0
    n=int(round(L*FPS))
    z=f"1.0+0.10*on/{n}" if i%2==0 else f"1.10-0.10*on/{n}"
    vf=(f"fps={FPS},trim=start={start},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=10,trim=duration={L},"
        f"scale={W*2}:{W*2},zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{W}:fps={FPS},setsar=1,format=yuv420p")
    subprocess.run(['ffmpeg','-v','error','-y','-i',f"clips/{s['clip']}.mp4",'-vf',vf,'-an','-frames:v',str(n),'-c:v','libx264','-crf','16',f'seg/{i:02d}.mp4'],check=True)
# xfade chain
ins=[];fl=[];prev='[0:v]';off=0
for i in range(len(tl)): ins+=['-i',f'seg/{i:02d}.mp4']
trs=['slideleft','slideright','circleopen','slideup']
for i in range(1,len(tl)):
    off+=tl[i-1]['len'];tr=trs[i%len(trs)] if not tl[i].get('count') else 'fade'
    fl.append(f"{prev}[{i}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}[x{i}]");prev=f'[x{i}]'
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(fl),'-map',prev,'-c:v','libx264','-crf','16','avatar_track.mp4'],check=True)
# audio
Tt=d['total'];ins=['-i','../q1/bgm.mp3'];fl=[f'[0]atrim=0:{Tt},volume=0.14,afade=in:d=0.5,afade=out:st={Tt-2}:d=2,asetpts=PTS-STARTPTS[b]'];labs=['[b]'];k=1
for n,t in d['aud']:
    ins+=['-i',f'{n}.wav'];ms=int(t*1000);fl.append(f'[{k}]aresample=44100,volume=1.5,adelay={ms}|{ms}[x{k}]');labs.append(f'[x{k}]');k+=1
for s,t in d['sfx']:
    ins+=['-i',f'../q1/{s}.wav'];ms=int(t*1000);fl.append(f'[{k}]aresample=44100,volume=0.7,adelay={ms}|{ms}[x{k}]');labs.append(f'[x{k}]');k+=1
fl.append(''.join(labs)+f'amix=inputs={len(labs)}:normalize=0,atrim=0:{Tt},alimiter=limit=0.95[a]')
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(fl),'-map','[a]','-ar','44100','mix.m4a'],check=True)
# composite
subprocess.run(['ffmpeg','-v','error','-y','-framerate','30','-i','bg/%05d.jpg','-i','avatar_track.mp4','-framerate','30','-i','fg/%05d.png','-i','mix.m4a',
 '-filter_complex','[0][1]overlay=44:304:shortest=0[v1];[v1][2]overlay=0:0[v]','-map','[v]','-map','3:a','-t',str(Tt),'-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart','Q01-v3.mp4'],check=True)
print('done')
