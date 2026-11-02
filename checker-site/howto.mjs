// 開いてすぐの「使い方」一覧: 左の項目に合わせて、右のカード（実際の画面）と情報を切り替える。
// 項目を押すと切り替わり、見えている間は数秒ごとに自動で次へ進む。
const STEPS=[
  {img:'app-icon.png',alt:'お買い得物件チェッカーのアイコン',mode:'icon',meta:[['料金','無料'],['計算','この端末の中'],['データ','国土交通省の取引データ']]},
  {img:'img/howto-upload.webp',alt:'スクショを貼り付ける画面',meta:[['入力','物件ページのスクショ'],['枚数','最大4枚・1枚12MBまで'],['読み取り','この端末の中']]},
  {img:'img/howto-form.webp',alt:'物件情報の入力画面（入力例）',meta:[['物件種別','戸建て・マンション・新築'],['必須','種別・場所・価格・築年・面積'],['入力例','ボタン1つで入る']]},
  {img:'img/howto-result.webp',alt:'査定結果の画面（入力例）',meta:[['販売価格','2,980万円'],['参考査定','3,078万円'],['判定','相場に近い']]},
  {img:'img/howto-compare.webp',alt:'販売価格を変えた査定結果の画面',meta:[['販売価格','2,680万円'],['割安率','12.9%'],['判定','割安の可能性']]},
  {img:'img/howto-caution.webp',alt:'買う前に確認したい点',meta:[['建物','劣化・修繕費用'],['土地','接道・再建築・権利'],['周辺','災害リスク・取引価格']]},
];
const section=document.getElementById('howto');
if(section){
  const buttons=[...section.querySelectorAll('[data-step]')],card=document.getElementById('howto-card'),img=document.getElementById('howto-img'),
    meta=document.getElementById('howto-meta'),count=document.getElementById('howto-n');
  const reduce=matchMedia('(prefers-reduced-motion: reduce)');
  STEPS.forEach(s=>{const i=new Image();i.src=s.img;});
  let current=0;
  function show(n){
    if(n===current&&img.getAttribute('src')===STEPS[n].img)return;current=n;const s=STEPS[n];
    buttons.forEach((b,k)=>{if(k===n)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
    card.classList.remove('swap');void card.offsetWidth;if(!reduce.matches)card.classList.add('swap');
    img.src=s.img;img.alt=s.alt;card.dataset.mode=s.mode||'shot';
    meta.replaceChildren(...s.meta.map(([t,d])=>{const w=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=t;dd.textContent=d;w.append(dt,dd);return w;}));
    count.textContent=n+1;
  }
  // 押して切り替え。見えている間は数秒ごとに自動で次へ（カーソルを乗せている間・押した後・動きを減らす設定では止める）
  let userTook=false,hovering=false,visible=false;
  buttons.forEach((b,k)=>b.addEventListener('click',()=>{userTook=true;show(k);}));
  section.addEventListener('pointerenter',()=>hovering=true);section.addEventListener('pointerleave',()=>hovering=false);
  section.addEventListener('focusin',()=>userTook=true);
  new IntersectionObserver(e=>{visible=e[0].isIntersecting;},{threshold:.3}).observe(section);
  setInterval(()=>{if(!userTook&&!hovering&&visible&&!reduce.matches&&!document.hidden)show((current+1)%STEPS.length);},4000);
}
