import zipfile,io,pandas as pd,numpy as np
z=zipfile.ZipFile('mlit/All.zip');parts=[]
for n in z.namelist():
    df=pd.read_csv(io.BytesIO(z.read(n)),encoding='cp932',low_memory=False)
    parts.append(df)
df=pd.concat(parts,ignore_index=True)
print('all',len(df))
h=df[(df['種類']=='宅地(土地と建物)')&(df['用途'].astype(str).str.contains('住宅'))].copy()
num=lambda s:pd.to_numeric(s.astype(str).str.replace('以上','').str.replace(',',''),errors='coerce')
h['land']=num(h['面積（㎡）']);h['floor']=num(h['延床面積（㎡）'])
h['year']=pd.to_numeric(h['建築年'].astype(str).str.extract(r'(\d{4})')[0],errors='coerce')
h['tyear']=pd.to_numeric(h['取引時期'].astype(str).str.extract(r'(\d{4})')[0],errors='coerce')
h['tq']=pd.to_numeric(h['取引時期'].astype(str).str.extract(r'第(\d)')[0],errors='coerce')
h['st']=pd.to_numeric(h['最寄駅：距離（分）'],errors='coerce')
h['price']=h['取引価格（総額）']
h=h.dropna(subset=['land','floor','year','price','tyear'])
print('houses',len(h),'事情あり',h['取引の事情等'].notna().sum())
print(h['取引の事情等'].value_counts().head(10).to_dict())
h.to_pickle('eval/houses.pkl')
