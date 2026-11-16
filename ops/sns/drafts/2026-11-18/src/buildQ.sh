#!/bin/bash
set -e
S=/tmp/claude-0/-home-user-venture-agent-sites/68731e5c-3a0a-5d00-8f66-f41a7327d5b4/scratchpad; q=$1; out=$2
cd $S/g && python3 trackQ.py $S/$q
cd $S/$q && python3 - <<'PY'
import json,subprocess
d=json.load(open('tl.json'));T=d['total']
ins=['-i','../q1/bgm.mp3'];fl=[f'[0]atrim=0:{T},volume=0.14,afade=in:d=0.5,afade=out:st={T-2}:d=2,asetpts=PTS-STARTPTS[b]'];labs=['[b]'];k=1
for n,t in d['aud']:
    ins+=['-i',f'{n}.wav'];ms=int(t*1000);fl.append(f'[{k}]aresample=44100,volume=1.5,adelay={ms}|{ms}[x{k}]');labs.append(f'[x{k}]');k+=1
for s,t in d['sfx']:
    ins+=['-i',f'../q1/{s}.wav'];ms=int(t*1000);fl.append(f'[{k}]aresample=44100,volume=0.7,adelay={ms}|{ms}[x{k}]');labs.append(f'[x{k}]');k+=1
fl.append(''.join(labs)+f'amix=inputs={len(labs)}:normalize=0,atrim=0:{T},alimiter=limit=0.95[a]')
subprocess.run(['ffmpeg','-v','error','-y',*ins,'-filter_complex',';'.join(fl),'-map','[a]','-ar','44100','mix.m4a'],check=True)
PY
T=$(python3 -c "import json;print(json.load(open('tl.json'))['total'])")
ffmpeg -v error -y -framerate 25 -i bg25/%05d.jpg -i track25.mp4 -framerate 25 -i fg25/%05d.png -i mix.m4a -filter_complex "[0][1]overlay=44:304[v1];[v1][2]overlay=0:0[v]" -map "[v]" -map 3:a -t $T -c:v libx264 -crf 20 -pix_fmt yuv420p -r 25 -c:a aac -b:a 160k body.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 body.mp4)
ffmpeg -v error -y -i body.mp4 -i ../v3/end.mp4 -ss 54 -t 5.5 -i ../q1/bgm.mp3 -filter_complex "[0:v]fps=25,format=yuv420p[v0];[1:v]fps=25,format=yuv420p[v1];[v0][v1]xfade=transition=fade:duration=0.4:offset=$(python3 -c "print($D-0.4)")[v];[2:a]volume=0.14,afade=out:st=3.5:d=1.5[bg];[1:a]volume=1.5[vo];[vo][bg]amix=inputs=2:normalize=0[ea];[0:a][ea]acrossfade=d=0.4[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart $out
ffprobe -v error -show_entries format=duration -of csv=p=0 $out
