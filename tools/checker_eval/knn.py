import pandas as pd,numpy as np,json,sys
h=pd.read_pickle('eval/houses.pkl')
odd=h['取引の事情等'].astype(str).str.contains('調停|関係者間|隣地|瑕疵|その他事情|取壊し')
h=h[~odd].copy()
h['age']=h['tyear']-h['year']
train=h[h['tyear']<=2024];test=h[h['tyear']==2025]
test=test.sample(min(20000,len(test)),random_state=1)
print('train',len(train),'test',len(test))
by=dict(tuple(train.groupby('市区町村コード')))
byp=dict(tuple(train.groupby('都道府県名')))
def est(r,k=10,variant='med'):
    g=by.get(r['市区町村コード'])
    if g is None or len(g)<k: g=byp[r['都道府県名']]
    d=(np.abs(np.log(g['floor'].values)-np.log(r['floor']))/0.25)**2+(np.abs(np.log(g['land'].values)-np.log(r['land']))/0.35)**2+((g['age'].values-r['age'])/8.0)**2
    d=d+np.where(g['地区名'].values==r['地区名'],0,1.0)
    idx=np.argsort(d)[:k];p=g['price'].values[idx]
    if variant=='med':return np.median(p)
    w=1/(1+d[idx]);lp=np.log(p);return float(np.exp((w*lp).sum()/w.sum()))
res={}
for v in ['med','wlog']:
    pr=np.array([est(r,10,v) for _,r in test.iterrows()])
    ape=np.abs(pr-test['price'].values)/test['price'].values*100
    res[v]=pr
    print(v,'誤差中央値 %.1f%%  20%%以内 %.0f%%'%(np.median(ape),(ape<=20).mean()*100))
test=test.assign(knn=res['wlog'])
test.to_pickle('eval/test.pkl')
