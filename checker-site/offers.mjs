// 結果画面の広告を、目的（買う予定／売る予定）と物件の条件に合わせて出し分ける。
// 広告の一覧は offers.json（enabled かつ href のあるものだけ表示、最大2つ）。
const box=document.getElementById('offers-result');
if(box){
  let offers=null,last=null;
  const load=()=>offers??=fetch('offers.json').then(r=>r.ok?r.json():{offers:[]}).then(d=>(d.offers||[]).filter(o=>o.enabled&&o.href)).catch(()=>[]);
  const intent=()=>document.querySelector('input[name=intent]:checked')?.value||'buy';
  try{const saved=localStorage.getItem('checker-intent');const r=saved&&document.querySelector(`input[name=intent][value="${saved}"]`);if(r)r.checked=true;}catch{}
  const el=(tag,props={},...kids)=>{const e=document.createElement(tag);Object.assign(e,props);e.append(...kids);return e;};
  function card(o){
    const link=el('a',{href:o.href,target:'_blank',rel:'sponsored nofollow noopener'});
    if(o.kind==='banner'&&o.img)link.append(el('img',{src:o.img,width:o.width||320,height:o.height||50,alt:o.alt||o.label+'（広告）',loading:'lazy'}));
    else{link.className='affiliate-text';link.textContent=o.text+' ↗';}
    const parts=[link];
    if(o.pixel)parts.push(el('img',{className:'ad-pixel',src:o.pixel,width:1,height:1,alt:'',loading:'lazy'}));
    return parts;
  }
  async function render(){
    const list=await load(),want=intent(),age=last?2026-last.year:null;
    const fit=list.filter(o=>o.intent.includes(want)&&(o.minAge==null||(age!=null&&age>=o.minAge)))
      .sort((a,b)=>(a.priority??9)-(b.priority??9));
    const labels=[],chosen=[];
    for(const o of fit){if(chosen.length>=2)break;chosen.push(o);if(!labels.includes(o.label))labels.push(o.label);}
    box.hidden=!chosen.length;
    if(!chosen.length)return;
    box.replaceChildren(el('p',{className:'ad-label',textContent:'広告・PR｜'+labels.join('・')}),...chosen.flatMap(card));
  }
  document.addEventListener('checker:result',e=>{last=e.detail;render();});
  document.querySelectorAll('input[name=intent]').forEach(r=>r.addEventListener('change',()=>{try{localStorage.setItem('checker-intent',intent());}catch{}render();}));
}
