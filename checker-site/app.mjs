import {features,comparison,validate,parseScreenshot,normalize,parsePrice,formatPrice,parseArea,parseBuildingYear,kanaKey,searchTowns} from './engine.mjs';
import {learningManifestUrl,acceptedLearning} from './learning.mjs';
const $=id=>document.getElementById(id),form=$('property-form');
let catalog,municipalities,worker,lastResult,busy=false,ocrBusy=false,autoEstimatePending=false,objectUrls=[];
let townData,townPromise,townRequest=0,townSelectionFocus=false;
const areaFields=['landArea','buildingArea','area'];
const pricePickerFields=['priceOku','priceHundreds','priceRemainder'];
const contactAddress='okaidokuhudousannchecker@gmail.com';
const publicSiteUrl='https://okaidoku-checker.rightharp65.chatgpt.site/';
const shareData={title:'お買い得物件チェッカー',text:'気になる物件の価格、目安を確かめてみませんか？スクショ・手入力で参考査定価格と割安度を無料チェック。',url:publicSiteUrl+'?utm_source=share&utm_medium=referral&utm_campaign=user_share'};
function contactMail(values){
  const body=['お買い得物件チェッカーへのお問い合わせ','種類：'+values.category,'内容：',values.message.trim(),'','使ってみた感想：'+(values.usefulness||'未回答'),'知ったきっかけ：'+(values.source||'未回答'),'お名前：'+(values.name.trim()||'未記入'),'返信希望：'+(values.reply?'はい':'いいえ'),'返信先：'+(values.email.trim()||'未記入')].join('\n');
  return {body,url:'mailto:'+contactAddress+'?subject='+encodeURIComponent('[お買い得物件チェッカー] '+values.category)+'&body='+encodeURIComponent(body)};
}
function contactValues(){return {category:$('contact-category').value,message:$('contact-message').value,usefulness:$('contact-usefulness').value,source:$('contact-source').value,name:$('contact-name').value,email:$('contact-email').value,reply:$('contact-reply').checked};}
const areaNumber=value=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:8}).format(value);
function readArea(id,unit=$('areaUnit').value){const text=normalize($(id).value).trim();return parseArea(/(?:㎡|m|平方メートル|坪)$/i.test(text)?text:text+unit);}
function areaHint(id){const sqm=readArea(id),unit=$('areaUnit').value;$(id+'Hint').textContent=sqm==null?($(id).value.trim()?'面積の数字を確認してください。':'単位を選んで、数字だけ入力'):'約 '+new Intl.NumberFormat('ja-JP',{maximumFractionDigits:2}).format(unit==='坪'?sqm:sqm*121/400)+(unit==='坪'?'㎡':'坪');}
function formatAreaInput(id,unit=$('areaUnit').value){const sqm=readArea(id,unit);if(sqm!=null)$(id).value=areaNumber($('areaUnit').value==='坪'?sqm*121/400:sqm);areaHint(id);}
const townKanaGroups=[['あ','あいうえおぁぃぅぇぉ'],['か','かきくけこゕゖ'],['さ','さしすせそ'],['た','たちつてとっ'],['な','なにぬねの'],['は','はひふへほ'],['ま','まみむめも'],['や','やゆよゃゅょ'],['ら','らりるれろ'],['わ','わをんゎゐゑ'],['他','']];
function townGroup(reading){const first=kanaKey(reading).normalize('NFD').replace(/\p{M}/gu,'')[0];return townKanaGroups.find(([,chars])=>chars.includes(first))?.[0]||'他';}
const names={type:'物件種別',prefecture:'都道府県',city:'市区町村',district:'町名',price:'価格',year:'建築年',landArea:'土地面積',buildingArea:'建物面積',area:'専有面積',structure:'構造',layout:'間取り',stationMinutes:'駅徒歩'};
const typeLabels={used_house:'中古戸建て',used_condo:'中古マンション',new_house:'新築戸建て'};
const fmt=n=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:0}).format(n);
function status(id,text,tone=''){const el=$(id);el.textContent=text;el.className='status '+tone;}
function option(select,value,label=value){const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);}
function getInput(){const p=Object.fromEntries(new FormData(form));p.type=form.querySelector('input[name=type]:checked')?.value||'';p.price=parsePrice(p.price)??'';p.year=parseBuildingYear(p.year)??'';for(const key of areaFields)p[key]=readArea(key)??'';delete p.areaUnit;return p;}
const contactForm=$('contact-form');
function validateContact(){const values=contactValues();$('contact-message').setCustomValidity(values.message.trim()?'':'お問い合わせ内容を入力してください。');$('contact-email').required=values.reply;return contactForm.reportValidity();}
$('contact-reply').addEventListener('change',()=>{$('contact-email').required=$('contact-reply').checked;});
$('contact-message').addEventListener('input',()=>$('contact-message').setCustomValidity(''));
contactForm.addEventListener('submit',event=>{event.preventDefault();if(!validateContact())return;status('contact-status','メールアプリで送信してください。開かない場合は「入力内容をコピー」と下のメールアドレスをご利用ください。');window.location.href=contactMail(contactValues()).url;});
$('copy-contact').addEventListener('click',async()=>{if(!validateContact())return;try{await navigator.clipboard.writeText(contactMail(contactValues()).body);status('contact-status','入力内容をコピーしました。下のメールアドレス宛てに貼り付けて送信できます。','success');}catch{status('contact-status','コピーできませんでした。入力欄から内容を選んでコピーしてください。','error');}});
async function copySiteLink(){try{await navigator.clipboard.writeText(shareData.url);status('share-status','紹介リンクをコピーしました。SNSやメッセージに貼り付けて使えます。','success');}catch{status('share-status','コピーできませんでした。ブラウザーのアドレス欄からURLをコピーしてください。','error');}}
$('copy-site-link').addEventListener('click',copySiteLink);
$('share-site').addEventListener('click',async()=>{if(!navigator.share){await copySiteLink();return;}try{await navigator.share(shareData);status('share-status','共有操作を開きました。');}catch(error){if(error.name!=='AbortError')await copySiteLink();}});
const sourceNames={x:'X',twitter:'X',instagram:'Instagram',threads:'Threads',facebook:'Facebook',youtube:'YouTube',tiktok:'TikTok',bluesky:'Bluesky',share:'知人の紹介'};
const visitSource=new URLSearchParams(location.search).get('utm_source')?.toLowerCase();if(sourceNames[visitSource])$('contact-source').value=sourceNames[visitSource];
function markChanged(){if(lastResult){lastResult=null;$('result').hidden=true;$('empty-result').hidden=false;status('model-progress','入力が変更されました。もう一度査定してください。');}}
function updateType(){const type=getInput().type,condo=type==='used_condo';$('house-areas').hidden=condo;$('condo-area').hidden=!condo;$('layout-field').hidden=false;$('area-unit-hint').textContent=condo?'専有面積に適用します。':'土地・建物にまとめて適用します。';$('station-hint').textContent='最寄り駅までの徒歩分数を選択できます。';}
function cities(pref,city=''){$('city').replaceChildren();option($('city'),'',pref?'市区町村を選択':'都道府県を先に選択');for(const [code,[p,name]] of Object.entries(municipalities))if(p===pref)option($('city'),code,name);$('city').disabled=!pref;$('city').value=city;resetDistrict();}
function hideTowns(){townRequest++;$('town-browser').hidden=true;$('town-options').hidden=true;$('district').setAttribute('aria-expanded','false');}
function resetDistrict(){$('district').value='';$('district').dataset.selectedTown='';hideTowns();$('town-options').replaceChildren();$('town-status').textContent='市区町村を選ぶと、入力せずに五十音から町名を探せます。';if($('city').value)showTowns();}
async function showTowns(jump=''){
  const city=$('city').value,request=++townRequest;
  if(!city){$('town-status').textContent='先に都道府県・市区町村を選択してください。';hideTowns();return;}
  try{
    if(!townData){$('town-status').textContent='町名の候補を準備しています…';townPromise??=fetch('towns.json').then(r=>{if(!r.ok)throw Error('towns');return r.json()});townData=await townPromise;}
    if($('city').value!==city||request!==townRequest)return;
    const rows=[...(townData[city]||[])].sort((a,b)=>kanaKey(a[1]).localeCompare(kanaKey(b[1]),'ja')||a[0].localeCompare(b[0],'ja'));
    const query=$('district').value===$('district').dataset.selectedTown?'':$('district').value;
    const matches=searchTowns(rows,query,rows.length),box=$('town-options'),headings=new Map();let selectedButton;box.replaceChildren();
    for(const [key] of townKanaGroups){
      const group=matches.filter(([,reading])=>townGroup(reading)===key);if(!group.length)continue;
      const heading=document.createElement('p');heading.className='town-heading';heading.textContent=key==='他'?'その他':key+'行';box.append(heading);headings.set(key,heading);
      for(const [name,reading] of group){
        const button=document.createElement('button'),label=document.createElement('span'),kana=document.createElement('small');button.type='button';button.className='town-option';button.disabled=busy;label.textContent=name;kana.textContent=kanaKey(reading);button.append(label,kana);button.setAttribute('aria-pressed',String(name===$('district').value));
        if(name===$('district').value)selectedButton=button;
        button.onclick=event=>{event.preventDefault();event.stopPropagation();$('district').value=name;$('district').dataset.selectedTown=name;markChanged();hideTowns();$('town-status').textContent='町名「'+name+'」を選択しました。町名欄を押すと選び直せます。';$('district').blur();button.blur();$('town-options').replaceChildren();guideAutoEstimate({start:true});};box.append(button);
      }
    }
    for(const button of $('town-kana').children){const key=button.dataset.kana,available=rows.some(([,reading])=>townGroup(reading)===key);button.dataset.unavailable=String(!available);button.disabled=busy||!available;button.hidden=key==='他'&&!available;button.setAttribute('aria-pressed',String(key===jump));}
    $('town-browser').hidden=false;box.hidden=!matches.length;$('district').setAttribute('aria-expanded',String(!!matches.length));
    const target=jump?headings.get(jump):selectedButton;box.scrollTop=target?Math.max(0,target.offsetTop-10):0;
    $('town-status').textContent=matches.length?(jump?(jump==='他'?'その他':jump+'行')+'へ移動しました。':'')+municipalities[city][1]+'の町名'+matches.length+'件。前後は一覧をスクロールして探せます。':'候補が見つからない場合も、そのまま手入力できます。';
  }catch{townPromise=null;$('town-status').textContent='候補を取得できませんでした。町名は手入力できます。';}
}
function ageHint(){const y=parseBuildingYear($('year').value);$('age-hint').textContent=y!=null?y+'年築・築'+(2026-y)+'年（2026年時点）':'築年数と建築年を一緒に確認して選べます。';}
function syncPricePicker(amount){
  $('price-selected').textContent=amount==null?'金額を選択してください':formatPrice(amount);
  if(amount==null){$('priceOku').value='0';$('priceHundreds').value='';$('priceRemainder').value='0';return;}
  const oku=Math.floor(amount/10000),hundreds=Math.floor((amount-oku*10000)/100)*100,remainder=Number((amount-oku*10000-hundreds).toFixed(8));
  for(const [id,value,label] of [['priceOku',oku,oku+'億円'],['priceHundreds',hundreds,fmt(hundreds)+'万円'],['priceRemainder',remainder,remainder+'万円']]){if(![...$(id).options].some(o=>o.value===String(value)))option($(id),String(value),label);$(id).value=String(value);}
}
function priceHint(){const value=$('price').value,amount=parsePrice(value);syncPricePicker(amount);$('price-hint').textContent=!value.trim()?'例：2,900万円 ＋ 80万円 → 2,980万円':amount==null?'金額を確認してください。例：2,980万円・29,800,000円':'選んだ金額で価格差・割安度を比較します。';$('price-hint').classList.toggle('invalid',!!value.trim()&&amount==null);return amount;}
function usePricePicker(){const amount=Number($('priceOku').value)*10000+Number($('priceHundreds').value)+Number($('priceRemainder').value);$('price').value=amount>0?formatPrice(amount):'';updatePrice();guideAutoEstimate({start:true});}
function updatePrice(){
  const amount=priceHint();$('form-errors').hidden=true;
  if(!lastResult)return;
  if(amount==null){$('result').hidden=true;$('empty-result').hidden=false;status('model-progress','価格を入力すると、同じ物件の割安度を更新します。');return;}
  renderResult(lastResult.estimate*10000,getInput(),{moveFocus:false,modelInfo:lastResult.modelInfo});
  status('model-progress','価格差と割安度を更新しました。','success');
}
function guideAutoEstimate({start=false}={}){
  if(!autoEstimatePending)return;
  const errors=validate(getInput());
  if(errors.length){status('auto-status','あと'+errors.length+'項目を確認：'+errors.map(x=>x.split('を')[0]).join('・')+'。入力後、そのまま査定に進みます。');return;}
  status('auto-status','必要な情報がそろいました。読み取り内容を確認してください。','success');
  if(start&&!busy&&!ocrBusy){autoEstimatePending=false;form.requestSubmit();}
}
function fill(p,clear=false){
  autoEstimatePending=false;
  if(clear){form.reset();cities('');for(const id of ['district','price','year','landArea','buildingArea','area','stationMinutes'])$(id).value='';}
  if(p.type){if(typeLabels[p.type])form.querySelector('input[value="'+p.type+'"]').checked=true;else form.querySelectorAll('input[name=type]').forEach(el=>{el.checked=false;});}
  if(p.prefecture){$('prefecture').value=p.prefecture;cities(p.prefecture,p.city||'');}
  if(areaFields.some(key=>Object.hasOwn(p,key))){const previous=$('areaUnit').value;$('areaUnit').value='㎡';for(const id of areaFields)formatAreaInput(id,previous);}
  for(const [key,value] of Object.entries(p)){
    if(['type','prefecture','city'].includes(key)||!$(key))continue;
    const el=$(key);
    if(el.tagName==='SELECT'){
      const wanted=key==='year'?parseBuildingYear(value):value,match=[...el.options].find(o=>normalize(o.value)===normalize(wanted));el.value=match?.value||'';
    }else el.value=value;
  }
  if(parsePrice($('price').value)!=null)$('price').value=formatPrice(parsePrice($('price').value));
  $('areaUnit').dataset.previousUnit=$('areaUnit').value;for(const id of areaFields)formatAreaInput(id);
  if(p.district){$('district').dataset.selectedTown=$('district').value;hideTowns();$('town-status').textContent='町名「'+$('district').value+'」を設定しました。町名欄を押すと選び直せます。';}
  updateType();ageHint();priceHint();markChanged();$('form-errors').hidden=true;
}
function applyText(){if(!municipalities)return;const parsed=parseScreenshot($('ocr-text').value,municipalities);const keys=Object.keys(parsed.values);if(keys.length){fill(parsed.values,true);autoEstimatePending=true;status('ocr-status','読み取り完了：'+keys.map(k=>names[k]||k).join('・')+'。認識に誤りがあれば下の欄で修正してください。','success');if(parsed.warnings.length)status('ocr-status',$('ocr-status').textContent+' '+parsed.warnings.join(' / '));guideAutoEstimate({start:true});}else status('ocr-status',parsed.warnings.join(' / ')||'物件情報を読み取れませんでした。','error');}
async function loadData(){
  try{const responses=await Promise.all([fetch('models/catalog.json'),fetch('municipalities.json')]);if(responses.some(r=>!r.ok))throw Error('data');[catalog,municipalities]=await Promise.all(responses.map(r=>r.json()));
    const prefs=[...new Set(Object.values(municipalities).map(x=>x[0]))];prefs.forEach(p=>option($('prefecture'),p));
    for(const [id,field] of [['structure','Structure'],['planning','CityPlanning'],['layout','FloorPlan']]){
      const all=new Set();for(const m of Object.values(catalog.models))for(const c of m.components){const i=c.categorical.indexOf(field);if(i>=0)c.categories[i].forEach(x=>{if(x!=='__missing__'&&x!=='不明')all.add(x)});}
      [...all].sort((a,b)=>a.localeCompare(b,'ja')).forEach(x=>option($(id),x));
    }
  }catch{status('model-progress','初期データの読み込みに失敗しました。ページを再読み込みしてください。','error');$('estimate').disabled=true;}
}
for(let year=2026;year>=1870;year--)option($('year'),String(year),(year===2026?'新築・築0年':'築'+(2026-year)+'年')+'（'+year+'年築）');
for(let n=1;n<=100;n++)option($('priceOku'),String(n),n+'億円');
for(let n=0;n<10000;n+=100)option($('priceHundreds'),String(n),fmt(n)+'万円');
for(let n=1;n<100;n++)option($('priceRemainder'),String(n),n+'万円');
for(let minutes=1;minutes<=180;minutes++)option($('stationMinutes'),String(minutes),'徒歩'+minutes+'分');
const ready=loadData();updateType();
ready.then(async()=>{if(!catalog)return;try{const r=await fetch(learningManifestUrl,{cache:'no-cache',credentials:'omit',signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error('manifest');const m=await r.json();$('learning-status').textContent=acceptedLearning(m,catalog)?'比較検証を通過した新しい中古戸建てモデルを取り込みます。更新日：'+m.approved_at.slice(0,10):(catalog.models.used_house.releaseKind==='reviewed_existing_transactions'?'中古戸建ては、既存の取引データで旧モデルとの比較を行った2026年10月更新モデルを使用しています。独立検証は未完了です。':'比較検証を通過した学習結果を待っています。現在は保存済みモデルで査定します。');}catch{$('learning-status').textContent=(catalog.models.used_house.releaseKind==='reviewed_existing_transactions'?'中古戸建ては2026年10月更新モデルで査定します。独立検証は未完了です。更新情報は確認できませんでした。':'現在の保存済みモデルで査定します。更新情報は確認できませんでした。');}});
$('prefecture').addEventListener('change',()=>cities($('prefecture').value));
$('city').addEventListener('change',resetDistrict);
for(const [key] of townKanaGroups){const button=document.createElement('button');button.type='button';button.textContent=key;button.dataset.kana=key;button.setAttribute('aria-label',key==='他'?'その他の町名へ移動':key+'行の町名へ移動');button.setAttribute('aria-controls','town-options');button.onclick=()=>{$('district').value='';markChanged();showTowns(key);};$('town-kana').append(button);}
$('district').addEventListener('focus',()=>{if(!townSelectionFocus&&$('town-browser').hidden)showTowns();});$('district').addEventListener('click',()=>{if($('town-browser').hidden)showTowns();});$('district').addEventListener('input',()=>showTowns());
$('district').addEventListener('keydown',event=>{if(event.key==='Escape')hideTowns();if(event.key==='ArrowDown'&&!$('town-options').hidden){event.preventDefault();$('town-options').querySelector('button')?.focus();}});
for(const id of pricePickerFields)$(id).addEventListener('change',usePricePicker);
form.addEventListener('input',event=>{if(pricePickerFields.includes(event.target.id))return;if(event.target.id==='price'){updatePrice();guideAutoEstimate();return;}if(areaFields.includes(event.target.id))areaHint(event.target.id);updateType();ageHint();markChanged();$('form-errors').hidden=true;guideAutoEstimate();});
form.addEventListener('change',event=>{if(pricePickerFields.includes(event.target.id))return;if(event.target.id!=='price')markChanged();guideAutoEstimate({start:true});});
$('price').addEventListener('blur',()=>{const amount=parsePrice($('price').value);if(amount!=null)$('price').value=formatPrice(amount);priceHint();});
$('price').addEventListener('focus',()=>$('price').select());
$('year').addEventListener('change',ageHint);
$('areaUnit').dataset.previousUnit=$('areaUnit').value;
$('areaUnit').addEventListener('change',()=>{const unit=$('areaUnit');for(const id of areaFields)formatAreaInput(id,unit.dataset.previousUnit);unit.dataset.previousUnit=unit.value;});
for(const id of areaFields){$(id).addEventListener('blur',()=>formatAreaInput(id));$(id).addEventListener('focus',()=>$(id).select());}
$('example').onclick=async()=>{await ready;fill({type:'used_condo',prefecture:'東京都',city:'13108',district:'亀戸',price:2980,year:2005,area:70,structure:'ＲＣ',layout:'３ＬＤＫ',stationMinutes:10},true);status('model-progress','入力例を設定しました。価格確認ボタンで査定できます。');};
$('parse-text').onclick=async()=>{await ready;applyText();};
function showErrors(errors){const box=$('form-errors');box.replaceChildren();const ul=document.createElement('ul');errors.forEach(t=>{const li=document.createElement('li');li.textContent=t;ul.append(li)});box.append(ul);box.hidden=false;box.scrollIntoView({behavior:'smooth',block:'center'});}
function setBusy(value){busy=value;for(const el of form.elements)el.disabled=value||el.dataset.unavailable==='true';for(const id of ['example','parse-text','pick'])$(id).disabled=value;$('estimate').textContent=value?'査定価格を計算しています…':'参考査定価格を確認する →';if(!value){$('city').disabled=!$('prefecture').value;updateType();}}
function renderResult(yen,input,{moveFocus=true,modelInfo}={}){
  const estimate=yen/10000,price=Number(input.price),c=comparison(estimate,price),model=modelInfo||catalog.models[input.type];
  lastResult={input,estimate,comparison:c,model:input.type,modelInfo,reference:catalog.reference.label,calculatedAt:new Date().toISOString()};
  $('estimated-price').textContent=fmt(estimate);$('sale-price').textContent=fmt(price)+'万円';$('price-difference').textContent=(c.difference>=0?'+':'−')+fmt(Math.abs(c.difference))+'万円';$('discount-rate').textContent=(c.discount>=0?'':'−')+Math.abs(c.discount).toFixed(1)+'%';$('discount-box').className='discount-box '+c.tone;
  $('result-badge').textContent=c.label;$('result-badge').className='badge '+c.tone;
  const max=Math.max(price,estimate);$('sale-bar').style.width=price/max*100+'%';$('estimate-bar').style.width=estimate/max*100+'%';$('sale-bar-text').textContent=fmt(price)+'万円';$('estimate-bar-text').textContent=fmt(estimate)+'万円';
  $('result-description').textContent=c.discount>=0?'販売価格は参考査定より約'+fmt(c.difference)+'万円低い結果です。建物の状態や修繕費をあわせて確認してください。':'販売価格は参考査定より約'+fmt(-c.difference)+'万円高い結果です。立地・設備・リフォームの内容もあわせて確認してください。';
  const city=municipalities[input.city]?.[1]||input.city;$('result-location').textContent=typeLabels[input.type]+' / '+input.prefecture+city+(input.district||'')+' / '+(input.type==='used_condo'?'専有 '+input.area+'㎡':'土地 '+input.landArea+'㎡・建物 '+input.buildingArea+'㎡')+' / '+input.year+'年築';
  $('model-name').textContent='使用モデル：'+model.name+'。'+(model.releaseKind==='reviewed_existing_transactions'?'既存の取引データで旧モデルとの比較を行い、改善を確認して採用しました。':'保存済みの学習モデルを使用しています。');
  const metric=model.metrics?.median_ape_pct;$('validation-metric').textContent=metric!=null?(model.releaseKind==='reviewed_existing_transactions'?'既存の取引データで比較した際の誤差中央値：':'保存モデルの検証時の誤差中央値：')+Number(metric).toFixed(1)+'%。'+(model.releaseKind==='reviewed_existing_transactions'?'完全な未使用データでの独立検証ではありません。':'')+'この物件の誤差や最新時点での精度を保証する値ではありません。':'このモデルの最新時点での予測精度は未確認です。';
  const row=features(input),unknown=modelInfo?.learned?[...modelInfo.unknownFields]:[];for(const c2 of model.components||[])for(const field of ['MunicipalityCode','DistrictName','Structure','CityPlanning']){const i=c2.categorical.indexOf(field);if(i>=0&&row[field]&&!c2.categories[i].includes(row[field]))unknown.push(({MunicipalityCode:'市区町村',DistrictName:'町名',Structure:'構造',CityPlanning:'用途地域'})[field]);}
  $('unknown-categories').hidden=!unknown.length;$('unknown-categories').textContent='学習時にない'+[...new Set(unknown)].join('・')+'が含まれます。査定の不確かさが大きい可能性があります。';
  $('empty-result').hidden=true;$('result').hidden=false;if(moveFocus){$('result').focus({preventScroll:true});if(matchMedia('(max-width:690px)').matches)$('result').scrollIntoView({behavior:'smooth',block:'start'});}
}
form.addEventListener('submit',async event=>{event.preventDefault();if(busy||ocrBusy)return;await ready;const input=getInput(),errors=validate(input);if(errors.length){showErrors(errors);return;}autoEstimatePending=false;$('form-errors').hidden=true;setBusy(true);status('model-progress','査定を開始しています…');
  try{worker??=new Worker(new URL('./model-worker.mjs?v=20261022-price',import.meta.url),{type:'module'});worker.onmessage=e=>{const data=e.data;if(data.kind==='progress')status('model-progress',data.text);else{setBusy(false);if(data.kind==='result'){renderResult(data.yen,input,{modelInfo:data.modelInfo});status('model-progress','査定が完了しました。','success');}else status('model-progress',data.text,'error');}};worker.onerror=()=>{setBusy(false);status('model-progress','モデルの読み込みに失敗しました。再度お試しください。','error');worker?.terminate();worker=null;};worker.postMessage(input);}catch(error){setBusy(false);status('model-progress',error.message,'error');}
});
$('revise').onclick=()=>{$('input-title').scrollIntoView({behavior:'smooth',block:'start'});$('price').focus({preventScroll:true});};
$('download').onclick=()=>{if(!lastResult)return;const r=lastResult,p=r.input,city=municipalities[p.city]?.[1]||p.city;
  const text=['お買い得物件チェッカー 査定結果','計算日時：'+new Date(r.calculatedAt).toLocaleString('ja-JP'),'査定基準時点：'+r.reference,'物件種別：'+typeLabels[p.type],'所在地：'+p.prefecture+city+(p.district||''),'建築年：'+p.year+'年',...(p.type==='used_condo'?['専有面積：'+p.area+'㎡']:['土地面積：'+p.landArea+'㎡','建物面積：'+p.buildingArea+'㎡']),'販売価格：'+fmt(Number(p.price))+'万円','参考査定価格：'+fmt(r.estimate)+'万円','価格差（査定−販売）：'+fmt(r.comparison.difference)+'万円','割安率：'+r.comparison.discount.toFixed(1)+'%','判定：'+r.comparison.label,'','学習済みモデルによる参考情報です。正式な不動産鑑定評価ではなく、売買価格を保証しません。','割安率＝（査定−販売）÷査定×100。未入力項目・地価情報はモデル保存時の補完値を使用。'].join('\n');
  const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='物件査定結果_'+new Date().toISOString().slice(0,10)+'.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

const zone=$('dropzone');$('pick').onclick=e=>{e.stopPropagation();$('file').click();};zone.onclick=e=>{if(e.target!==$('pick'))$('file').click();};zone.onkeydown=e=>{if(e.target===zone&&(e.key==='Enter'||e.key===' ')){e.preventDefault();$('file').click();}};
$('file').onchange=e=>{const files=[...e.target.files];e.target.value='';processImages(files);};
zone.ondragover=e=>{e.preventDefault();zone.classList.add('dragging');};zone.ondragleave=()=>zone.classList.remove('dragging');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('dragging');processImages([...e.dataTransfer.files]);};
document.addEventListener('paste',event=>{
  const files=[...(event.clipboardData?.items||[])].filter(i=>i.type.startsWith('image/')).map(i=>i.getAsFile()).filter(Boolean);
  if(files.length){event.preventDefault();processImages(files);return;}
  const target=event.target,editable=target?.closest?.('input,textarea,select,[contenteditable="true"]');
  if(editable&&editable.id!=='price')return;
  const amount=parsePrice(event.clipboardData?.getData('text/plain'));
  if(amount==null)return;
  event.preventDefault();if(busy||ocrBusy){status('ocr-status','読み取り・査定が完了してから価格を貼り付けてください。');return;}
  $('price').value=formatPrice(amount);updatePrice();
  status('ocr-status','販売価格 '+formatPrice(amount)+' を入力しました。','success');
  if(!lastResult){autoEstimatePending=true;guideAutoEstimate({start:true});}
});
async function imageCanvas(file){
  const url=URL.createObjectURL(file),image=new Image();try{await new Promise((ok,no)=>{image.onload=ok;image.onerror=()=>no(Error('この画像を開けませんでした。PNGかJPEGをお試しください'));image.src=url;});
    const ratio=Math.min(2.2,2200/image.naturalWidth,3600/image.naturalHeight),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*ratio));canvas.height=Math.max(1,Math.round(image.naturalHeight*ratio));const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);return canvas;
  }finally{URL.revokeObjectURL(url);}
}
async function processImages(files){
  if(busy){status('ocr-status','査定が完了してから、次のスクショを入れてください。');return;}
  if(ocrBusy){status('ocr-status','現在の画像を読み取り中です。完了後に次の画像を入れてください。');return;}
  const selected=files.filter(f=>/^image\/(png|jpeg|webp|bmp)$/.test(f.type));if(!selected.length){status('ocr-status','PNG・JPEG・WebP・BMPの画像を選んでください。','error');return;}
  if(selected.length>4||selected.some(f=>f.size>12*1024*1024)){status('ocr-status','画像は1枚12MBまで、1回に4枚までにしてください。','error');return;}
  ocrBusy=true;$('pick').disabled=true;$('estimate').disabled=true;$('ocr-progress').hidden=false;$('ocr-progress').value=0;objectUrls.forEach(URL.revokeObjectURL);objectUrls=[];$('thumbnails').replaceChildren();for(const file of selected){const image=document.createElement('img'),url=URL.createObjectURL(file);objectUrls.push(url);image.src=url;image.alt='読み取り対象：'+file.name;$('thumbnails').append(image);}
  let ocr;
  try{
    await ready;if(!catalog||!municipalities)throw Error('初期データを読み込めませんでした。ページを再読み込みしてください');
    if(!globalThis.Tesseract)throw Error('文字認識を準備できませんでした。ページを再読み込みしてください');
    status('ocr-status','日本語の文字認識を準備しています。初回は少し時間がかかります…');
    ocr=await Tesseract.createWorker('jpn+eng',1,{workerPath:new URL('ocr-worker.min.js',location.href).href,corePath:new URL('tesseract-core-lstm.wasm.js',location.href).href,langPath:new URL('.',location.href).href,workerBlobURL:false,logger:message=>{if(message.status==='recognizing text'){$('ocr-progress').value=Math.round(message.progress*100);}}});
    const results=[];
    for(let i=0;i<selected.length;i++){
      status('ocr-status','スクショを読み取っています（'+(i+1)+'/'+selected.length+'枚）…');
      const canvas=await imageCanvas(selected[i]);await ocr.setParameters({tessedit_pageseg_mode:'4'});const first=(await ocr.recognize(canvas)).data.text;
      // Sparse layout handles web tables with labels in different columns.
      await ocr.setParameters({tessedit_pageseg_mode:'11'});const second=(await ocr.recognize(canvas)).data.text;results.push(first,second);canvas.width=1;canvas.height=1;
    }
    const text=results.join('\n\n').trim();if(!text)throw Error('文字を読み取れませんでした。価格や面積が鮮明に写った画像をお試しください。');
    $('ocr-text').value=text;applyText();$('ocr-progress').value=100;
  }catch(error){status('ocr-status','読み取りに失敗しました。'+(error.message||'画像を変えてお試しください。'),'error');}
  finally{try{if(ocr)await ocr.terminate();}finally{ocrBusy=false;$('pick').disabled=false;$('estimate').disabled=busy||!catalog;$('ocr-progress').hidden=true;guideAutoEstimate({start:true});}}
}
