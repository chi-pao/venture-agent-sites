import json,subprocess
L={l[0]:l for l in json.load(open('lines.json'))}
dur=lambda f: float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f],capture_output=True,text=True).stdout)
tl=[];aud=[];sfx=[];t=0.0
def say(n,panel,gap=0.25,conf=False):
    global t
    who=L[n][1];d=dur(f'{n}.wav')
    tl.append(dict(t0=t,who=who,text=L[n][3],panel=panel,confetti=conf,clip=n,len=d+gap));aud.append((n,t));t+=d+gap
def count(panel,faces):
    global t
    for c,f in zip((3,2,1),faces):
        tl.append(dict(t0=t,who=f,text='',panel=panel,count=c,clip='idle-'+f,len=0.8));sfx.append(('tick',t));t+=0.8
sfx.append(('whoosh',0))
say('01','q1');say('02','q1');say('03','q1');say('04','q1');say('05','q1')
count('q1',['kenji','miho','sota'])
sfx.append(('ding',t));say('06','a1',conf=True);say('07','a1');say('08','a1',gap=0.35)
sfx.append(('whoosh',t));say('09','q2');say('10','q2');say('11','q2');say('12','q2')
count('q2',['miho','kenji','hana'])
sfx.append(('ding',t));say('13','a2',conf=True);say('14','a2');say('15','end');say('16','end');say('17','end',gap=1.2)
json.dump(dict(tl=tl,aud=aud,sfx=sfx,total=t),open('tl.json','w'),ensure_ascii=False)
print(round(t,2),len(tl))
