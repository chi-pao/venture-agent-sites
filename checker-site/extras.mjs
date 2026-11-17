// 査定結果の補足（中古戸建てのみ）:
// 1) 価格の幅: 直近の実際の取引で、場所（都会・中堅都市・田舎）・築年数（30年未満/以上）・査定額が同じくらいの家の
//    「実際の価格 ÷ 査定額」の真ん中の半分（25〜75%）。price-bands.json（tools/checker_train/build_bands.py）。
//    読めないときや件数が少ない区分は、査定額だけで分けた幅を使う。
// 1b) 築30年以上の家: 建物の状態で値段が大きく変わることと、土地だけの目安（公示地価×土地の広さ）を添える。
// 2) 近くの似た取引: 同じ市区町村の実際の取引（area/<code>/sales.json）から、築年数・土地・建物の広さが近いもの5件。
const BANDS=[[800,.61,1.47],[1500,.67,1.43],[2500,.85,1.30],[4000,.90,1.21],[Infinity,.92,1.22]];
const fmt=v=>Math.round(v).toLocaleString('ja-JP');
const el=(tag,props={},...kids)=>{const e=document.createElement(tag);Object.assign(e,props);e.append(...kids);return e;};
let box,bandsPromise;
const bandsData=()=>bandsPromise??=fetch('price-bands.json').then(r=>r.ok?r.json():null).catch(()=>null);
function pickBand(data,d){
  const fallback=BANDS.find(([max])=>d.estimate<max).slice(1);
  if(!data?.bands)return {lo:fallback[0],hi:fallback[1],cls:null,old:false};
  const k=String(data.edges.filter(e=>d.estimate>=e).length),cls=data.classes?.[d.city]||null,old=2026-d.year>=(data.oldAge||30);
  const cell=cls?data.bands[cls+(old?'・築30年以上':'・築30年未満')]:null;
  const v=cell?.[k]||data.bands.all?.[k];
  return v?{lo:v[0],hi:v[1],cls,old}:{lo:fallback[0],hi:fallback[1],cls,old};
}
function ensureBox(){
  if(box&&box.isConnected)return box;
  const anchor=document.querySelector('.intent-switch')||document.getElementById('offers-result');
  box=el('section',{id:'result-extras',className:'result-extras'});anchor?.before(box);return box;
}
async function show(d){
  const b=ensureBox();b.replaceChildren();
  if(d.type!=='used_house'||!Number.isFinite(d.estimate)){b.hidden=true;return;}
  b.hidden=false;
  const {lo,hi,cls,old}=pickBand(await bandsData(),d);
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
    el('small',{textContent:`相場は ${fmt(low)}万〜${fmt(high)}万円。最近実際に売れた家のうち、${cls?`${cls}・築${old?'30年以上':'30年未満'}で、`:''}参考査定が同じくらい（${fmt(d.estimate)}万円前後）だった家の、真ん中の半分が入る価格帯です。`})));
  if(old){
    const land=d.landPrice>0&&d.landArea>0?d.landPrice*d.landArea/10000:null;
    b.append(el('div',{className:'old-note'},
      el('p',{textContent:`築30年以上の家は、建物の傷み・リフォームの有無・建て替えできるかで、値段が大きく変わります${cls==='田舎'?'。特に人の少ない地域では、その差が大きくなりがちです':''}。上の幅は目安として見てください。`}),
      land?el('p',{},el('strong',{textContent:`土地だけの目安：約${fmt(land)}万円`}),
        el('small',{textContent:` （公示地価 ${fmt(d.landPrice)}円/㎡ × 土地 ${fmt(d.landArea)}㎡。${d.landPriceLevel===2?'同じ町':'同じ市区町村'}の住宅地の地点の真ん中の値。土地の形や前の道で上下します）`})):''));
  }
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
