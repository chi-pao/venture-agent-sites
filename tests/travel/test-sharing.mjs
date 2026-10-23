import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {onRequest,normalisePlan} from '../../functions/api/travel/[[path]].js';

const schema=readFileSync(new URL('../../schema/travel.sql',import.meta.url),'utf8');
function database(){const sql=new DatabaseSync(':memory:');sql.exec(schema);return {sql,prepare(query){let params=[];return {bind(...values){params=values;return this;},async first(){return sql.prepare(query).get(...params)??null;},async run(){const result=sql.prepare(query).run(...params);return {meta:{changes:Number(result.changes)}};}};}};}
function plan(title='家族の京都旅行'){return {version:1,trip:{title,destination:'京都',start:'2026-11-14',days:2,people:3,budget:25000,note:'休憩を多めに',companions:'family',dayStart:'09:00',buffer:15},events:[{id:'event-1',title:'昼食',day:1,time:'12:00',category:'food',cost:1800,memo:'候補',confirmed:false,move:30,duration:60}],packing:[{id:'pack-1',title:'充電器',done:false}]};}
function call(db,method,path,payload,token,extra={}){const headers={'Content-Type':'application/json',...extra};if(token)headers.Authorization='Bearer '+token;return onRequest({request:new Request('https://example.com/api/travel/'+path,{method,headers,body:payload===undefined?undefined:JSON.stringify(payload)}),env:{TRAVEL_DB:db,TRAVEL_SHARING_ENABLED:'true'}});}
const db=database();
const initial=await call(db,'POST','trips',{plan:plan()});assert.equal(initial.status,201);const shared=await initial.json();
assert.equal(shared.editToken.length,43);assert.equal(shared.viewToken.length,43);assert.notEqual(shared.editToken,shared.viewToken);
const stored=db.sql.prepare('SELECT * FROM travel_trips').get();assert.notEqual(stored.edit_hash,shared.editToken);assert.equal(stored.edit_hash.length,64);
assert(!JSON.stringify(stored).includes(shared.editToken));assert(!JSON.stringify(stored).includes(shared.viewToken));
assert.equal((await call(db,'GET','trips/'+shared.id)).status,401);
assert.equal((await call(db,'GET','trips/'+shared.id,undefined,'x'.repeat(43))).status,404);
const viewed=await (await call(db,'GET','trips/'+shared.id,undefined,shared.viewToken)).json();assert.equal(viewed.editable,false);assert.equal(viewed.plan.trip.title,'家族の京都旅行');assert(!('edit_hash' in viewed));
assert.equal((await call(db,'PUT','trips/'+shared.id,{version:1,plan:plan('許可なし')},shared.viewToken)).status,404);
const update=await call(db,'PUT','trips/'+shared.id,{version:1,plan:plan('ふたりで京都へ')},shared.editToken);assert.equal(update.status,200);assert.equal((await update.json()).version,2);
const concurrent=await Promise.all([call(db,'PUT','trips/'+shared.id,{version:2,plan:plan('Aの変更')},shared.editToken),call(db,'PUT','trips/'+shared.id,{version:2,plan:plan('Bの変更')},shared.editToken)]);
assert.deepEqual(concurrent.map(r=>r.status).sort(),[200,409]);
assert.equal(db.sql.prepare('SELECT version FROM travel_trips').get().version,3);
assert.equal((await call(db,'POST','trips',{plan:plan()},undefined,{Origin:'https://other.example'})).status,403);
assert.equal((await call(db,'POST','trips',{plan:{...plan(),events:[...plan().events,...plan().events]}})).status,400);
const invalid=plan();invalid.trip.days='2';assert.throws(()=>normalisePlan(invalid));
assert.equal((await call(db,'POST','trips',{padding:'x'.repeat(50000),plan:plan()})).status,413);
db.sql.prepare('UPDATE travel_trips SET expires_at=0 WHERE id=?').run(shared.id);
assert.equal((await call(db,'GET','trips/'+shared.id,undefined,shared.editToken)).status,404);
const disabled=await onRequest({request:new Request('https://example.com/api/travel/trips',{method:'POST'}),env:{TRAVEL_DB:db}});assert.equal(disabled.status,503);
const health=await onRequest({request:new Request('https://example.com/api/travel/health'),env:{TRAVEL_DB:db}});assert.deepEqual(await health.json(),{databaseBound:true,schemaReady:true,sharingEnabled:false,search:'connection_required',searchSchemaReady:true,searchPolicy:'2026-10-23-geoapify-1',searchModes:['walk','drive'],transit:'not_connected'});
const quota=database();for(let i=0;i<20;i++)assert.equal((await call(quota,'POST','trips',{plan:plan()})).status,201);
assert.equal((await call(quota,'POST','trips',{plan:plan()})).status,429);assert.equal(quota.sql.prepare('SELECT count(*) AS n FROM travel_trips').get().n,20);
db.sql.close();quota.sql.close();
console.log('PASS: create/read/edit, separate permissions, token hashes, concurrent version conflict, origin, validation, size cap, expiry, disabled mode, health and daily cap');
