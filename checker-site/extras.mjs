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
  // 結論を先に大きく、下に「安め｜相場｜高め」のメーターと販売価格の位置。
  const zone=!has?null:price<low?'low':price>high?'high':'mid';
  const verdict={low:['相場より安め',`相場の下限より ${fmt(low-price)}万円 安い`],mid:['相場の範囲内','実際に売れた価格の真ん中あたり'],high:['相場より高め',`相場の上限より ${fmt(price-high)}万円 高い`]}[zone]||['実際に売れた相場',''];
  const min=Math.min(low,has?price:low)*0.8,max=Math.max(high,has?price:high)*1.12,pos=v=>Math.min(97,Math.max(3,(v-min)/(max-min)*100));
  const meter=el('div',{className:'meter'},
    el('div',{className:'meter-track'},el('span',{className:'z low'}),el('span',{className:'z mid'}),el('span',{className:'z high'})),
    el('div',{className:'meter-ticks'},el('span',{textContent:`${fmt(low)}万`}),el('span',{textContent:`${fmt(high)}万`})));
  const [zl,zm,zh]=meter.firstChild.children;
  zl.style.width=`${pos(low)}%`;zm.style.left=`${pos(low)}%`;zm.style.width=`${pos(high)-pos(low)}%`;zh.style.left=`${pos(high)}%`;
  const [tl,th]=meter.lastChild.children;tl.style.left=`${pos(low)}%`;th.style.left=`${pos(high)}%`;
  if(has){const at=pos(price),pin=el('div',{className:`meter-pin ${zone} ${at<25?'l':at>75?'r':''}`},el('span',{textContent:`販売価格 ${fmt(price)}万円`}));pin.style.left=`${at}%`;meter.prepend(pin);}
  b.append(el('div',{className:'band '+(zone||'')},
    el('span',{className:'band-label',textContent:'実際に売れた相場とくらべると'}),
    el('strong',{className:'band-verdict',textContent:verdict[0]}),
    ...(verdict[1]?[el('p',{className:'band-diff',textContent:verdict[1]})]:[]),
    meter,
    el('small',{textContent:`相場＝2025年に実際に売れた家のうち、参考査定が同じくらい（${fmt(d.estimate)}万円前後）だった家の半数が入る価格帯（${fmt(low)}万〜${fmt(high)}万円）。`})));
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
