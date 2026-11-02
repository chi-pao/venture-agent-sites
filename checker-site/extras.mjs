// 査定結果の補足（中古戸建てのみ）:
// 1) 価格の幅: 2025年の実際の取引で、同じくらいの査定額の家の「実際の価格 ÷ 査定額」の真ん中の半分（25〜75%）。
//    2024年までで学習した同じ方式のモデルで測定（ops/checker/ACCURACY.md）。
// 2) 近くの似た取引: 同じ市区町村の実際の取引（area/<code>/sales.json）から、築年数・土地・建物の広さが近いもの5件。
const BANDS=[[800,.61,1.47],[1500,.67,1.43],[2500,.85,1.30],[4000,.90,1.21],[Infinity,.92,1.22]];
const fmt=v=>Math.round(v).toLocaleString('ja-JP');
const el=(tag,props={},...kids)=>{const e=document.createElement(tag);Object.assign(e,props);e.append(...kids);return e;};
let box;
function ensureBox(){
  if(box&&box.isConnected)return box;
  const anchor=document.querySelector('.intent-switch')||document.getElementById('offers-result');
  box=el('section',{id:'result-extras',className:'result-extras'});anchor?.before(box);return box;
}
async function show(d){
  const b=ensureBox();b.replaceChildren();
  if(d.type!=='used_house'||!Number.isFinite(d.estimate)){b.hidden=true;return;}
  b.hidden=false;
  const [,lo,hi]=BANDS.find(([max])=>d.estimate<max);
  const low=d.estimate*lo,high=d.estimate*hi,price=Number(d.price),has=Number.isFinite(price)&&price>0;
  // 幅は「似た家の真ん中の半分」なので、上限より高い＝4軒中3軒はそれより安く売れた、と言い換えられる。
  const zone=!has?'mid':price<low?'low':price>high?'high':'mid';
  const T={low:['相場より安め',`同じような家、4軒のうち3軒は ${has?fmt(price)+'万円':''}より高く売れています`,[1,1,1,0],'これより高く売れた'],
    mid:[has?'相場の範囲内':'実際に売れた相場',`同じような家、4軒のうち2軒が ${fmt(low)}万〜${fmt(high)}万円 で売れています`,[0,1,1,0],'この価格帯で売れた'],
    high:['相場より高め',`同じような家、4軒のうち3軒は ${has?fmt(price)+'万円':''}より安く売れています`,[1,1,1,0],'これより安く売れた']}[zone];
  const house=on=>{const n=document.createElementNS('http://www.w3.org/2000/svg','svg');n.setAttribute('viewBox','0 0 48 44');n.setAttribute('class','hh'+(on?' on':''));
    n.innerHTML='<path d="M4 20 24 4l20 16"/><rect x="9" y="18" width="30" height="24" rx="2"/><rect x="20" y="28" width="8" height="14"/>';return n;};
  b.append(el('div',{className:'band '+zone},
    el('span',{className:'band-label',textContent:has?`販売価格 ${fmt(price)}万円 は…`:'実際に売れた相場'}),
    el('strong',{className:'band-verdict',textContent:T[0]}),
    el('div',{className:'houses'},...T[2].map(house)),
    el('p',{className:'band-say',textContent:T[1]}),
    el('div',{className:'band-legend'},el('span',{className:'k on',textContent:T[3]}),el('span',{className:'k',textContent:'それ以外'})),
    el('small',{textContent:`相場は ${fmt(low)}万〜${fmt(high)}万円。2025年に実際に売れた家のうち、参考査定が同じくらい（${fmt(d.estimate)}万円前後）だった家の、真ん中の半分が入る価格帯です。`})));
  let sales=[];
  try{const r=await fetch(`area/${d.city}/sales.json`);if(r.ok)sales=await r.json();}catch{}
  if(!sales.length)return;
  const age=2026-d.year;
  const score=s=>{const a=s[6]?2026-s[6]:null;return (a==null?1.5:Math.abs(a-age)/8)**2+(s[4]&&d.landArea?Math.log(s[4]/d.landArea)/.35:1)**2+(s[5]&&d.buildingArea?Math.log(s[5]/d.buildingArea)/.25:1)**2;};
  const near=sales.map(s=>[score(s),s]).sort((x,y)=>x[0]-y[0]).slice(0,5).map(x=>x[1]);
  const rows=near.map(s=>el('tr',{},...[`${s[0]}年${s[1]?`第${s[1]}四半期`:''}`,s[2],`${fmt(s[3])}万円`,s[4]?`${s[4]}㎡`:'',s[5]?`${s[5]}㎡`:'',s[6]?`${s[6]}年`:''].map((t,i)=>el('td',{textContent:t,className:i>=2?'num':''}))));
  b.append(el('h3',{textContent:`${d.cityName}で築年数・広さが近い実際の取引`}),
    el('div',{className:'tablewrap'},el('table',{},el('thead',{},el('tr',{},...['時期','地区','価格','土地','建物','建築年'].map(t=>el('th',{textContent:t})))),el('tbody',{},...rows))),
    el('small',{textContent:'出典：国土交通省 不動産情報ライブラリ（当サイト集計）。取引ごとの事情や建物の状態は反映していません。'}));
}
document.addEventListener('checker:result',e=>show(e.detail));
