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
  b.append(el('div',{className:'band'},
    el('span',{className:'band-label',textContent:'似た査定額の家の実際の取引（真ん中の半分）'}),
    el('strong',{textContent:`${fmt(d.estimate*lo)}万〜${fmt(d.estimate*hi)}万円`}),
    el('small',{textContent:'2025年の実際の取引で、同じくらいの査定額だった家の価格の幅です。建物の状態や立地で、この幅の外になることもあります。'})));
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
