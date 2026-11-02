"""python swap_site.py <site> <cand dir> <out site>: copy of the site whose used_house model is the candidate."""
import json,os,shutil,sys
from pathlib import Path
site,cand,out=map(Path,sys.argv[1:])
if out.exists():shutil.rmtree(out)
out.mkdir(parents=True)
for p in site.iterdir():
    if p.name!='models':os.symlink(p.resolve(),out/p.name)
(out/'models').mkdir()
for p in (site/'models').iterdir():
    if p.name!='catalog.json':os.symlink(p.resolve(),out/'models'/p.name)
shutil.copy(cand/'used_house.dat',out/'models'/'used_house.dat')
cat=json.loads((site/'models'/'catalog.json').read_text(encoding='utf-8'))
cat['models']['used_house']=dict(cat['models']['used_house'],components=[json.loads((cand/'component.json').read_text(encoding='utf-8'))])
(out/'models'/'catalog.json').write_text(json.dumps(cat,ensure_ascii=False),encoding='utf-8')
