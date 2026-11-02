export function features(input) {
  const area=Number(input.type==='used_condo'?input.area:input.landArea), floor=Number(input.buildingArea);
  return {Area:area,TotalFloorArea:floor,BuildingYear:Number(input.year),BuildingAge:Math.max(0,2026-Number(input.year)),TransactionYear:2026,Quarter:4,
    StationMinutes:input.stationMinutes?Number(input.stationMinutes):null,LandPriceMatchLevel:0,
    LogArea:Math.log1p(area),LogTotalFloorArea:Math.log1p(floor),LandBuildingRatio:floor>0?area/floor:null,
    MunicipalityCode:input.city,DistrictName:input.districtKey||input.district||null,Prefecture:input.prefecture,
    Structure:input.structure||null,CityPlanning:input.planning||null,FloorPlan:input.layout||null,Use:input.type!=='used_condo'?'住宅':null};
}
export {transform,componentPrediction,combine} from './model-runtime.mjs';
export function comparison(estimate,price) {
  if(!Number.isFinite(estimate)||estimate<=0||!Number.isFinite(price)||price<=0)throw Error('価格は0より大きい数値にしてください');
  const discount=(estimate-price)/estimate*100;
  return {discount,difference:estimate-price,label:price/estimate<=.9?'割安の可能性':price/estimate<=1.1?'相場に近い':'割高の可能性',tone:price/estimate<=.9?'good':price/estimate<=1.1?'neutral':'high'};
}
export function parsePrice(value) {
  if(typeof value==='number')return Number.isFinite(value)&&value>0&&value<=10000000?value:null;
  let s=String(value??'').normalize('NFKC').trim().replace(/^(?:販売価格|物件価格|売出価格|価格)\s*[:：]?\s*/,'').replace(/\s*[（(]?(?:消費税込|税込|税抜)[）)]?$/,'').replace(/\s/g,'');
  const yenPrefix=/^[¥￥]/.test(s);s=s.replace(/^[¥￥]/,'');
  const number='(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?',read=v=>v?Number(v.replace(/,/g,'')):0;
  let amount,match;
  if((match=s.match(new RegExp('^('+number+')億(?:('+number+')万)?(?:('+number+')円|円)?$'))))amount=read(match[1])*10000+read(match[2])+read(match[3])/10000;
  else if((match=s.match(new RegExp('^('+number+')万(?:('+number+')円|円)?$'))))amount=read(match[1])+read(match[2])/10000;
  else if((match=s.match(new RegExp('^('+number+')円$'))))amount=read(match[1])/10000;
  else if((match=s.match(new RegExp('^('+number+')$'))))amount=read(match[1])/(yenPrefix?10000:1);
  return Number.isFinite(amount)&&amount>0&&amount<=10000000?amount:null;
}
export const formatPrice=amount=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:8}).format(amount)+'万円';
export function validate(p) {
  const errors=[];
  if(!['used_house','new_house','used_condo'].includes(p.type))errors.push('物件種別を選択してください');
  if(!p.prefecture||!/^\d{5}$/.test(p.city||''))errors.push('都道府県と市区町村を選択してください');
  if(!Number.isFinite(Number(p.price))||Number(p.price)<=0||Number(p.price)>10000000)errors.push('販売価格を入力してください（例：2,980万円・29,800,000円）');
  for(const [k,label] of p.type==='used_condo'?[['area','専有面積']]:[['landArea','土地面積'],['buildingArea','建物面積']])if(!Number.isFinite(Number(p[k]))||Number(p[k])<5||Number(p[k])>10000)errors.push(label+'を5〜10,000㎡で入力してください');
  if(!Number.isInteger(Number(p.year))||Number(p.year)<1870||Number(p.year)>2026)errors.push('建築年を1870〜2026年で入力してください');
  if(p.type==='new_house'&&2026-Number(p.year)>2)errors.push('築年が古い物件は「中古戸建て」を選択してください');
  if(p.stationMinutes!==''&&p.stationMinutes!=null&&(!Number.isFinite(Number(p.stationMinutes))||Number(p.stationMinutes)<1||Number(p.stationMinutes)>180))errors.push('駅徒歩は1〜180分、または空欄にしてください');
  return errors;
}
export const normalize=text=>String(text).normalize('NFKC').replace(/[\t　]+/g,' ').replace(/([\u3040-\u30ff\u3400-\u9fff]) +(?=[\u3040-\u30ff\u3400-\u9fff])/g,'$1').replace(/m\s*[²2]/gi,'㎡');
export function parseArea(value){
  const s=normalize(value??'').replace(/\s/g,''),match=s.match(/^((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(㎡|m|平方メートル|坪)?$/i);
  if(!match)return null;
  const area=Number(match[1].replace(/,/g,''))*(match[2]==='坪'?400/121:1);
  return area>0&&area<=10000?area:null;
}
export function parseBuildingYear(value){
  const s=normalize(value??'').replace(/\s/g,'');let year,match;
  if((match=s.match(/^(\d{4})(?:年(?:\(築\d+年\))?)?$/)))year=Number(match[1]);
  else if((match=s.match(/^(昭和|平成|令和)(元|\d{1,2})年?$/)))year=({昭和:1925,平成:1988,令和:2018}[match[1]])+(match[2]==='元'?1:Number(match[2]));
  else if((match=s.match(/^(?:築)?(\d{1,3})年?$/)))year=2026-Number(match[1]);
  return Number.isInteger(year)&&year>=1870&&year<=2026?year:null;
}
export function parseAddress(value,municipalities={}){
  const text=normalize(value??'').replace(/[\s〒]/g,'').replace(/^\d{3}-?\d{4}/,'');if(!text)return null;
  const entries=Object.entries(municipalities),pref=[...new Set(entries.map(([,v])=>v[0]))].find(p=>text.startsWith(p));
  const rest=pref?text.slice(pref.length):text;
  const matches=entries.filter(([,v])=>(!pref||v[0]===pref)&&rest.startsWith(v[1])).sort((a,b)=>b[1][1].length-a[1][1].length);
  if(!matches.length||matches.filter(x=>x[1][1].length===matches[0][1][1].length).length!==1)return null;
  const [city,[prefecture,name]]=matches[0],district=rest.slice(name.length).replace(/[0-9０-９].*$/,'').trim();
  return {prefecture,city,district};
}
export const kanaKey=text=>normalize(text??'').replace(/[ァ-ヶ]/g,c=>String.fromCharCode(c.charCodeAt(0)-96)).replace(/\s/g,'').toLowerCase();
export function searchTowns(rows,query,limit=12){const q=kanaKey(query);return rows.filter(([name,reading])=>!q||kanaKey(name).includes(q)||kanaKey(reading).includes(q)).slice(0,limit);}
export function parseScreenshot(text,municipalities={}) {
  const raw=normalize(text),out={},warnings=[];
  const compact=raw.replace(/([0-9])\s+(?=[0-9])/g,'$1');
  const price=compact.match(/(?:販売価格|物件価格|売出価格|価格)\s*[:：]?\s*([0-9,.]+\s*億\s*)?([0-9,.]+)?\s*万\s*円/)||compact.match(/([0-9,.]+\s*億\s*)?([0-9,.]+)?\s*万\s*円/);
  const money=value=>{let s=String(value).replace(/,/g,'');if(/^\d{1,3}(?:\.\d{3})+$/.test(s))s=s.replace(/\./g,'');return Number(s);};
  if(price){out.price=(price[1]?money(price[1].replace(/[^0-9.]/g,''))*10000:0)+(price[2]?money(price[2]):0)}
  else {const m=compact.match(/([0-9.]+)\s*億\s*円/);if(m)out.price=Number(m[1])*10000;}
  const area=(label)=>{const match=compact.match(new RegExp('(?:'+label+')\\s*[:：]?\\s*(?:[^0-9\\n]{0,12})?([0-9,]+(?:\\.[0-9]+)?)\\s*(?:㎡|m)(?![a-z])','i'));return match?Number(match[1].replace(/,/g,'')):null};
  for(const [key,label] of [['landArea','土地\\s*面積|敷地\\s*面積'],['buildingArea','建物\\s*面積|延床\\s*面積|延べ床\\s*面積'],['area','専有\\s*面積']]){const v=area(label);if(v)out[key]=v;}
  if(/新築マンション/.test(raw)){out.type='new_condo';warnings.push('新築マンションは対応していません。中古物件か別の対応種別を選択してください');}
  else if(/中古マンション|専有\s*面積/.test(raw))out.type='used_condo';
  else if(/新築.*(?:戸建|一戸建)|(?:戸建|一戸建).*新築/.test(raw))out.type='new_house';
  else if(/戸建|一戸建|建物\s*面積|土地\s*面積/.test(raw))out.type='used_house';
  let date=raw.match(/(?:築年月|建築年月|建築年|築年|完成時期|完成年月)\s*[:：]?\s*((?:19|20)\d{2})\s*年/);
  if(date)out.year=Number(date[1]);
  else {const era=raw.match(/(?:築年月|建築年月|建築年|完成時期|完成年月)\s*[:：]?\s*(昭和|平成|令和)\s*(元|\d{1,2})\s*年/);if(era)out.year=({昭和:1925,平成:1988,令和:2018}[era[1]])+(era[2]==='元'?1:Number(era[2]));else{const age=raw.match(/築\s*(\d{1,2})\s*年/);if(age)out.year=2026-Number(age[1]);}}
  const layout=raw.match(/([1-9])\s*(S?LDK|SDK|DK|K|R)(?:\s*\+\s*S)?/i);if(layout)out.layout=layout[1]+layout[2].toUpperCase();
  const station=raw.match(/徒歩\s*(\d{1,3})\s*分/);if(station)out.stationMinutes=Number(station[1]);
  if(/鉄骨鉄筋コンクリート|SRC/.test(raw))out.structure='ＳＲＣ';else if(/鉄筋コンクリート|RC造|RC/.test(raw))out.structure='ＲＣ';else if(/軽量鉄骨/.test(raw))out.structure='軽量鉄骨造';else if(/木造/.test(raw))out.structure='木造';else if(/鉄骨/.test(raw))out.structure='鉄骨造';
  const prefectures=[...new Set(Object.values(municipalities).map(x=>x[0]))];
  const pref=prefectures.find(p=>raw.includes(p));
  let addressLine=raw.split('\n').find(x=>/所在地|住所/.test(x));
  if(addressLine){addressLine=addressLine.replace(/^.*?(?:所在地|住所)\s*[:：]?\s*/,'').trim();if(!addressLine)addressLine=raw.split('\n')[raw.split('\n').findIndex(x=>/所在地|住所/.test(x))+1]||'';}
  const search=addressLine||raw;
  const matches=Object.entries(municipalities).filter(([,v])=>(!pref||v[0]===pref)&&search.includes(v[1])).sort((a,b)=>b[1][1].length-a[1][1].length);
  if(matches.length){const [code,[p,city]]=matches[0];out.city=code;out.prefecture=p;let address=search.slice(search.indexOf(city)+city.length).split(/\n|交通|地図|周辺|物件概要|価格|土地面積|建物面積/)[0].trim();out.district=address.replace(/[0-9０-９].*$/,'').replace(/\s/g,'');}
  else if(pref){out.prefecture=pref;warnings.push('市区町村を選択してください');}
  if(!Object.keys(out).length)warnings.push('物件の項目が見つかりませんでした。画像を切り取るか、手入力してください');
  for(const k of ['price','landArea','buildingArea','area'])if(out[k]!=null&&(!Number.isFinite(out[k])||out[k]<=0)){delete out[k];warnings.push('数値の認識結果を確認してください');}
  return {values:out,warnings};
}
