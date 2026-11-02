import {features,componentPrediction,combine} from './engine.mjs';
import {sha256Hex} from './integrity.mjs';
import {learningRoot,learningManifestUrl,acceptedLearning} from './learning.mjs';
const cached=new Map();let catalog;
let remoteCandidates=[],activeLearned,checkedAt=0;
async function learnedModels(){
  if(Date.now()-checkedAt>600000){checkedAt=Date.now();try{const response=await fetch(learningManifestUrl,{cache:'no-cache',credentials:'omit',signal:AbortSignal.timeout(5000)});if(response.ok){const m=await response.json();remoteCandidates=[m,m.previous].filter(x=>acceptedLearning(x,catalog));}}catch{}}
  return [...remoteCandidates,activeLearned].filter((m,i,all)=>m&&all.findIndex(x=>x?.model_sha256===m.model_sha256)===i);
}
async function load(meta,index,total){
  if(cached.has(meta.path))return cached.get(meta.path);
  postMessage({kind:'progress',text:'査定モデルを準備しています（'+index+'/'+total+'）…'});
  const response=await fetch(meta.path);if(!response.ok)throw Error('モデルの読み込みに失敗しました。再度お試しください');
  const compressed=await response.arrayBuffer();if(compressed.byteLength!==meta.bytes)throw Error('モデルのファイルサイズが一致しません');
  const hash=await sha256Hex(compressed);
  if(hash!==meta.sha256)throw Error('モデルの整合性を確認できませんでした');
  const stream=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buffer=await new Response(stream).arrayBuffer();cached.set(meta.path,buffer);return buffer;
}
// Large category-split tables live in their own gzip file (splitsPath) so the catalog stays small;
// they are fetched only for the model that needs them and checked like the model binary.
const splitCache=new Map();
async function ensureSplits(c){
  if(!c.splitsPath||c.categoricalSplits)return;
  if(!splitCache.has(c.splitsPath))splitCache.set(c.splitsPath,(async()=>{
    const response=await fetch(c.splitsPath);if(!response.ok)throw Error('モデルの読み込みに失敗しました。再度お試しください');
    const compressed=await response.arrayBuffer();if(compressed.byteLength!==c.splitsBytes)throw Error('モデルのファイルサイズが一致しません');
    if(await sha256Hex(compressed)!==c.splitsSha256)throw Error('モデルの整合性を確認できませんでした');
    return JSON.parse(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
  })());
  try{c.categoricalSplits=await splitCache.get(c.splitsPath);}catch(error){splitCache.delete(c.splitsPath);throw error;}
}
globalThis.onmessage=async event=>{try{
  catalog??=await(await fetch('models/catalog.json')).json();
  const input=event.data,model=catalog.models[input.type];if(!model)throw Error('対応していない物件種別です');
  const row=features(input),predictions=[];
  if(input.type==='used_house')for(const learned of await learnedModels()){
    try{
      const parts=learned.model.components.filter(c=>c.region==null||c.region===row.Prefecture),values=[];
      for(let i=0;i<parts.length;i++){const c={...parts[i],path:new URL(parts[i].path,learningRoot).href};values.push(componentPrediction(row,c,await load(c,i+1,parts.length)));}
      const g=parts.findIndex(c=>c.region==null),r=parts.findIndex(c=>c.region===row.Prefecture);if(g<0)throw Error('Base model missing');
      const w=learned.model.regionalWeight||0,yen=r>=0?(1-w)*values[g]+w*values[r]:values[g];if(!Number.isFinite(yen)||yen<=0)throw Error('Invalid learned prediction');
      const labels={MunicipalityCode:'市区町村',DistrictName:'町名',Structure:'構造',CityPlanning:'用途地域'},unknownFields=[];
      for(const c of parts)for(const [field,label]of Object.entries(labels)){const j=c.categorical.indexOf(field);if(j>=0&&row[field]&&!c.categories[j].includes(row[field]))unknownFields.push(label);}
      activeLearned=learned;postMessage({kind:'result',yen,modelInfo:{name:learned.model.name,metrics:learned.model.metrics,learned:true,unknownFields:[...new Set(unknownFields)],sourceSha256:learned.model_sha256}});return;
    }catch{ /* Keep the previous independently approved model or bundled model. */ }
  }
  async function bundledPrediction(item){
    const values=[];
    for(let i=0;i<item.components.length;i++){const c=item.components[i];const buffer=await load(c,i+1,item.components.length);await ensureSplits(c);values.push(componentPrediction(row,c,buffer));}
    const yen=combine(values,item.components);if(!Number.isFinite(yen)||yen<=0)throw Error('査定価格を算出できませんでした。入力内容を確認してください');return yen;
  }
  try{postMessage({kind:'result',yen:await bundledPrediction(model)});}
  catch(error){const previous=catalog.previousModels?.[input.type];if(!previous)throw error;postMessage({kind:'result',yen:await bundledPrediction(previous),modelInfo:previous});}

}catch(error){postMessage({kind:'error',text:error.message||'査定に失敗しました'})}};
