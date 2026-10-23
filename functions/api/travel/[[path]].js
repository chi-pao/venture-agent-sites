// Cloudflare Pages Functions. Disabled until explicit configuration and product review.
const JSON_HEADERS={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};
const MAX_BODY=40000,MAX_PLAN=32768,TTL=90*86400;
class InputError extends Error{constructor(message,status=400){super(message);this.status=status;}}
const reply=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:JSON_HEADERS});
const fail=(message,status)=>{throw new InputError(message,status);};
function string(value,max,required=false){if(typeof value!=='string'||value.length>max)fail('文字列の形式・長さを確認してください');value=value.trim();if(required&&!value)fail('必須項目を入力してください');return value;}
function integer(value,min,max){if(typeof value!=='number'||!Number.isInteger(value)||value<min||value>max)fail('数値の範囲を確認してください');return value;}
function optionalNumber(value,max){return value===null?null:integer(value,0,max);}
function object(value){if(!value||typeof value!=='object'||Array.isArray(value))fail('データ形式を確認してください');return value;}
export function normalisePlan(input){
 const p=object(input),t=object(p.trip);
 if(p.version!==1||!Array.isArray(p.events)||p.events.length>60||!Array.isArray(p.packing)||p.packing.length>50)fail('対応していない旅行データです');
 const start=string(t.start??'',10);
 if(start&&(!/^20\d\d-\d\d-\d\d$/.test(start)||Number.isNaN(Date.parse(start+'T12:00:00Z'))||new Date(start+'T12:00:00Z').toISOString().slice(0,10)!==start))fail('出発日を確認してください');
 const dayStart=string(t.dayStart??'09:00',5);
 if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(dayStart))fail('出発時刻を確認してください');
 const trip={title:string(t.title,70,true),destination:string(t.destination??'',60),start,
  days:integer(t.days,1,14),people:integer(t.people,1,30),budget:optionalNumber(t.budget??null,10000000),
  note:string(t.note??'',500),companions:['friends','couple','family','other'].includes(t.companions)?t.companions:'other',dayStart,buffer:integer(t.buffer??10,0,120),endBy:string(t.endBy??'18:00',5),pace:t.pace==='slow'?'slow':'normal'};
 if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(trip.endBy))fail('終了目標を確認してください');
 const ids=new Set();
 const events=p.events.map(raw=>{const e=object(raw),id=string(e.id,80,true);if(ids.has(id))fail('予定IDが重複しています');ids.add(id);
  const time=string(e.time??'',5);if(time&&!/^([01]\d|2[0-3]):[0-5]\d$/.test(time))fail('予定の時刻を確認してください');
  return {id,title:string(e.title,80,true),day:integer(e.day,1,trip.days),time,
   category:['spot','food','transport','stay','other'].includes(e.category)?e.category:'other',
   cost:optionalNumber(e.cost??null,10000000),memo:string(e.memo??'',300),confirmed:e.confirmed===true,
   move:optionalNumber(e.move??null,1440),duration:optionalNumber(e.duration??null,1440),
   location:e.location==null?null:point(e.location),sourceURL:safeSource(e.sourceURL),retrievedAt:string(e.retrievedAt??'',40),
   routeKey:string(e.routeKey??'',180),routeMode:['walk','drive','manual'].includes(e.routeMode)?e.routeMode:'manual',
   routeSource:string(e.routeSource??'',120),routeChecked:string(e.routeChecked??'',40)};});
 const packing=p.packing.map(raw=>{const p=object(raw);return {id:string(p.id,80,true),title:string(p.title,70,true),done:p.done===true};});
 if(new Set(packing.map(p=>p.id)).size!==packing.length)fail('持ち物IDが重複しています');
 const result={version:1,isSample:p.isSample===true,trip,events,packing};
 if(new TextEncoder().encode(JSON.stringify(result)).length>MAX_PLAN)fail('計画のサイズが大きすぎます',413);
 return result;
}
async function bodyJSON(request){
 if(!(request.headers.get('Content-Type')||'').toLowerCase().startsWith('application/json'))fail('JSONで送信してください',415);
 if(Number(request.headers.get('Content-Length')||0)>MAX_BODY)fail('データが大きすぎます',413);
 const reader=request.body?.getReader();if(!reader)fail('データがありません');const chunks=[];let size=0;
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>MAX_BODY){await reader.cancel();fail('データが大きすぎます',413);}chunks.push(value);}}
 finally{reader.releaseLock();}
 const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
 try{return object(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));}catch(error){if(error instanceof InputError)throw error;fail('JSONを確認してください');}
}
async function hash(token){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token)))].map(b=>b.toString(16).padStart(2,'0')).join('');}
function secret(){const bytes=crypto.getRandomValues(new Uint8Array(32));return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');}
function bearer(request){const match=/^Bearer ([A-Za-z0-9_-]{43})$/.exec(request.headers.get('Authorization')||'');if(!match)fail('招待情報が必要です',401);return match[1];}
function publicTrip(row,editable){return {id:row.id,version:row.version,plan:JSON.parse(row.plan_json),updatedAt:row.updated_at,expiresAt:row.expires_at,editable};}
async function room(db,id,request,edit=false){
 const tokenHash=await hash(bearer(request));
 const row=await db.prepare('SELECT * FROM travel_trips WHERE id=? AND expires_at>?').bind(id,Math.floor(Date.now()/1000)).first();
 if(!row||!(tokenHash===row.edit_hash||(!edit&&tokenHash===row.view_hash)))fail('計画が見つからないか、この操作を許可されていません',404);
 return {row,editable:tokenHash===row.edit_hash,tokenHash};
}
const SEARCH_VERSION='2026-10-24-geoapify-workers-2';
function coordinate(value,min,max){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)fail('緯度・経度を確認してください');return value;}
function point(value){const p=object(value);return {lat:coordinate(p.lat,-90,90),lon:coordinate(p.lon,-180,180)};}
function safeSource(value){if(value==null||value==='')return '';const text=string(value,250);try{const url=new URL(text);if(url.protocol==='https:'&&url.hostname==='www.openstreetmap.org')return url.href;}catch{}fail('出典URLの形式を確認してください');}
function cleanString(value,max=200){return typeof value==='string'?value.slice(0,max):'';}
function osmLink(p){const raw=p.datasource?.raw||{},kind=raw.osm_type,id=String(raw.osm_id||'');return ['node','way','relation'].includes(kind)&&/^\d{1,20}$/.test(id)?'https://www.openstreetmap.org/'+kind+'/'+id:'';}
async function reserveSearch(env,request){
 const day=new Date().toISOString().slice(0,10),minute=Math.floor(Date.now()/60000);
 const ip=await hash(request.headers.get('CF-Connecting-IP')||'local-client');
 const client=await env.TRAVEL_DB.prepare('INSERT INTO travel_api_limits(bucket,count) VALUES(?,1) ON CONFLICT(bucket) DO UPDATE SET count=count+1 WHERE count<10 RETURNING count').bind('m:'+minute+':'+ip).first();
 if(!client)fail('検索が続いています。1分ほど待って再度お試しください',429);
 // Reserve two credits conservatively per outbound call. Unused reservations are not refunded.
 const cap=Math.min(1000,Math.max(2,Number.parseInt(env.TRAVEL_API_DAILY_CREDITS||'1000',10)||1000));
 const quota=await env.TRAVEL_DB.prepare('INSERT INTO travel_api_limits(bucket,count) VALUES(?,2) ON CONFLICT(bucket) DO UPDATE SET count=count+2 WHERE count+2<=? RETURNING count').bind('d:'+day,cap).first();
 if(!quota)fail('今日の検索上限に達しました。保存済みの旅程は利用できます',429);
 await env.TRAVEL_DB.prepare('DELETE FROM travel_api_limits WHERE bucket LIKE ? AND bucket NOT LIKE ?').bind('d:%','d:'+day).run();
 await env.TRAVEL_DB.prepare('DELETE FROM travel_api_limits WHERE bucket LIKE ? AND CAST(substr(bucket,3,instr(substr(bucket,3),\':\')-1) AS INTEGER)<?').bind('m:%',minute-2).run();
}
async function providerCall(path,params,env,request){
 await reserveSearch(env,request);
 const url=new URL('https://api.geoapify.com/'+path);for(const [k,v] of Object.entries(params))url.searchParams.set(k,String(v));
 url.searchParams.set('apiKey',env.GEOAPIFY_API_KEY);
 let response;try{response=await fetch(url,{headers:{Accept:'application/json'},signal:AbortSignal.timeout(12000),redirect:'manual'});}catch{fail('検索先への接続ができません。入力した旅程は保持しています',502);}
 // Workers rejects redirect:'error' before sending. Manual prevents forwarding the key to another origin.
 if(response.status>=300&&response.status<400)fail('検索先から転送応答を受け取りました。接続先の設定を確認してください',502);
 if(!response.ok)fail(response.status===429?'検索先の無料枠または回数制限に達しました':'検索先の応答を確認できません。キーとAPIの設定を確認してください',response.status===429?429:502);
 const text=await response.text();if(text.length>1000000)fail('検索先の応答が大きすぎます',502);
 let data;try{data=JSON.parse(text);}catch{fail('検索先から正しいデータを取得できませんでした',502);}return data;
}
export async function searchTravel(action,input,env,request){
 if(env.TRAVEL_SEARCH_ENABLED!=='true'||!env.GEOAPIFY_API_KEY)fail('検索APIの接続待ちです。運営者の設定後に検索できます',503);
 if(!env.TRAVEL_DB)fail('検索回数を管理するデータベースの接続待ちです',503);
 const metadata={provider:'Geoapify / OpenStreetMap',retrievedAt:new Date().toISOString(),policy:SEARCH_VERSION};
 if(action==='search'){
  const text=string(input.text,120,true);if(text.length<2)fail('場所は2文字以上で入力してください');
  const data=await providerCall('v1/geocode/search',{text,format:'json',lang:'ja',filter:'countrycode:jp',limit:5},env,request);
  const places=(data.results||[]).filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon)).slice(0,5).map(p=>({name:cleanString(p.name||p.formatted,100),address:cleanString(p.formatted),lat:p.lat,lon:p.lon,sourceURL:osmLink(p)}));
  return {...metadata,places};
 }
 if(action==='nearby'){
  const center=point(input),kind=input.kind==='food'?'food':'spot';
  const data=await providerCall('v2/places',{categories:kind==='food'?'catering.restaurant,catering.cafe':'tourism.sights',filter:`circle:${center.lon},${center.lat},5000`,bias:`proximity:${center.lon},${center.lat}`,limit:10,lang:'ja'},env,request);
  const places=(data.features||[]).map(f=>f.properties||{}).filter(p=>p.name&&Number.isFinite(p.lat)&&Number.isFinite(p.lon)).slice(0,10).map(p=>({name:cleanString(p.name,100),address:cleanString(p.formatted),lat:p.lat,lon:p.lon,kind,sourceURL:osmLink(p),openingHours:null,durationHint:kind==='food'?60:45,durationSource:'アプリの初期目安。施設の公表値ではなく変更できます'}));
  return {...metadata,places};
 }
 if(action==='route'){
  const from=point(input.from),to=point(input.to),mode=input.mode;
  if(!['walk','drive'].includes(mode))fail('対応は徒歩・車です。電車・バスの時刻表検索は別接続が必要です');
  const data=await providerCall('v1/routing',{waypoints:`${from.lat},${from.lon}|${to.lat},${to.lon}`,mode,units:'metric',format:'geojson'},env,request);
  const route=data.features?.[0]?.properties;
  if(!route||!Number.isFinite(route.time)||route.time<0||!Number.isFinite(route.distance)||route.distance<0)fail('この区間の経路が見つかりません。別の出発地・目的地で試してください',422);
  return {...metadata,mode,from,to,seconds:route.time,minutes:Math.ceil(route.time/60),meters:Math.round(route.distance),estimate:true,notice:'経路モデルによる目安です。実際の交通・混雑・待ち時間は反映しません'};
 }
 fail('検索機能が見つかりません',404);
}

export async function onRequest(context){
 const {request,env}=context,url=new URL(request.url);
 const pieces=url.pathname.split('/').filter(Boolean);
 const path=pieces.slice(2); // /api/travel/{action}
 const origin=request.headers.get('Origin');
 if(origin&&origin!==url.origin)return reply({error:'別のサイトからの操作は受け付けていません'},403);
 if(request.method==='GET'&&path.length===1&&path[0]==='health'){
  let searchSchema=false;try{if(env.TRAVEL_DB){await env.TRAVEL_DB.prepare('SELECT bucket FROM travel_api_limits LIMIT 1').first();searchSchema=true;}}catch{}
  let schema=false;if(env.TRAVEL_DB){try{await env.TRAVEL_DB.prepare('SELECT id FROM travel_trips LIMIT 1').first();schema=true;}catch{}}
  return reply({databaseBound:!!env.TRAVEL_DB,schemaReady:schema,sharingEnabled:env.TRAVEL_SHARING_ENABLED==='true',search:env.TRAVEL_SEARCH_ENABLED==='true'&&!!env.GEOAPIFY_API_KEY?(searchSchema?'configured':'database_schema_required'):'connection_required',searchSchemaReady:searchSchema,searchPolicy:SEARCH_VERSION,searchModes:['walk','drive'],transit:'not_connected'});
 }
 if(path.length===1&&['search','nearby','route'].includes(path[0])&&request.method==='POST'){
  try{return reply(await searchTravel(path[0],await bodyJSON(request),env,request));}
  catch(error){return reply({error:error instanceof InputError?error.message:'検索設定を確認してください',code:error instanceof InputError?error.status:503},error instanceof InputError?error.status:503);}
 }
 if(!env.TRAVEL_DB||env.TRAVEL_SHARING_ENABLED!=='true')return reply({error:'共同保存は接続・確認待ちです'},503);
 try{
  const db=env.TRAVEL_DB,now=Math.floor(Date.now()/1000);
  if(path.length===1&&path[0]==='trips'&&request.method==='POST'){
   const input=await bodyJSON(request),plan=normalisePlan(input.plan);
   const day=new Date().toISOString().slice(0,10);
   const quota=await db.prepare('INSERT INTO travel_create_limits(day,count) VALUES(?,1) ON CONFLICT(day) DO UPDATE SET count=count+1 WHERE count<20 RETURNING count').bind(day).first();
   if(!quota)return reply({error:'本日の試験用作成上限に達しました'},429);
   await db.prepare('DELETE FROM travel_trips WHERE id IN (SELECT id FROM travel_trips WHERE expires_at<=? LIMIT 50)').bind(now).run();
   const count=await db.prepare('SELECT COUNT(*) AS n FROM travel_trips').first();
   if(count.n>=1000)return reply({error:'試験用の保存上限に達しました'},429);
   const id=crypto.randomUUID(),editToken=secret(),viewToken=secret();
   await db.prepare('INSERT INTO travel_trips(id,plan_json,version,edit_hash,view_hash,created_at,updated_at,expires_at) VALUES(?,?,1,?,?,?,?,?)')
    .bind(id,JSON.stringify(plan),await hash(editToken),await hash(viewToken),now,now,now+TTL).run();
   return reply({id,version:1,editToken,viewToken,expiresAt:now+TTL},201);
  }
  if(path.length!==2||path[0]!=='trips'||!/^[-0-9a-f]{36}$/.test(path[1]))return reply({error:'見つかりません'},404);
  const id=path[1];
  if(request.method==='GET'){
   const found=await room(db,id,request);return reply(publicTrip(found.row,found.editable));
  }
  if(request.method==='PUT'){
   const found=await room(db,id,request,true),input=await bodyJSON(request);
   const expected=integer(input.version,1,1000000),plan=normalisePlan(input.plan);
   const result=await db.prepare('UPDATE travel_trips SET plan_json=?,version=version+1,updated_at=?,expires_at=? WHERE id=? AND version=? AND edit_hash=? AND expires_at>?')
    .bind(JSON.stringify(plan),now,now+TTL,id,expected,found.tokenHash,now).run();
   if(result.meta.changes!==1)return reply({error:'別の人が予定を更新しました。最新の計画を読み直してから変更を反映してください',conflict:true},409);
   return reply({id,version:expected+1,updatedAt:now,expiresAt:now+TTL});
  }
  return reply({error:'この操作には対応していません'},405);
 }catch(error){
  if(error instanceof InputError)return reply({error:error.message},error.status);
  return reply({error:'共同保存の接続・利用枠を確認してください'},503);
 }
}
