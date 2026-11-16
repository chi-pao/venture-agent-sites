import assert from 'node:assert/strict';import {DatabaseSync} from 'node:sqlite';import {readFileSync} from 'node:fs';import {onRequest,pickHotels} from '../../functions/api/travel/[[path]].js';
const sql=new DatabaseSync(':memory:');sql.exec(readFileSync(new URL('../../schema/travel.sql',import.meta.url),'utf8'));sql.exec('CREATE TABLE IF NOT EXISTS travel_api_limits(bucket TEXT PRIMARY KEY,count INTEGER NOT NULL)');
const db={prepare(q){let p=[];return {bind(...v){p=v;return this},async first(){return sql.prepare(q).get(...p)??null},async run(){return {meta:{changes:Number(sql.prepare(q).run(...p).changes)}}}}}};
const env={TRAVEL_DB:db,RAKUTEN_APP_ID:'app-secret',RAKUTEN_ACCESS_KEY:'access-secret',RAKUTEN_AFFILIATE_ID:'aff-id'};
const call=(data,over={},headers={})=>onRequest({request:new Request('https://example.com/api/travel/hotels',{method:'POST',headers:{'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.9',...headers},body:JSON.stringify(data)}),env:{...env,...over}});
const sample={hotels:[[{hotelBasicInfo:{hotelName:'試験の宿',hotelInformationUrl:'https://hb.afl.rakuten.co.jp/hgc/x/?pc=https%3A%2F%2Ftravel.rakuten.co.jp%2FHOTEL%2F1%2F',hotelThumbnailUrl:'https://img.travel.rakuten.co.jp/a.jpg',hotelMinCharge:8800,reviewAverage:4.3,reviewCount:120,nearestStation:'長谷',latitude:35.31,longitude:139.53}},{hotelRatingInfo:{}}],{hotel:[{hotelBasicInfo:{hotelName:'悪いリンク',hotelInformationUrl:'javascript:alert(1)'}}]}]};
const original=globalThis.fetch;let seen;
try{
 globalThis.fetch=async(url,init)=>{seen={url:new URL(url),init};return Response.json(sample)};
 let r=await call({lat:35.31,lon:139.53});assert.equal(r.status,200);let d=await r.json();
 assert.equal(d.hotels.length,1);assert.equal(d.hotels[0].name,'試験の宿');assert.equal(d.hotels[0].minCharge,8800);assert.ok(d.hotels[0].url.startsWith('https://hb.afl.rakuten.co.jp/'));
 assert.equal(seen.url.origin,'https://openapi.rakuten.co.jp');assert.equal(seen.url.searchParams.get('affiliateId'),'aff-id');assert.equal(seen.url.searchParams.get('datumType'),'1');assert.equal(seen.init.redirect,'manual');assert.ok(seen.init.headers.Referer.startsWith('https://'));
 assert(!JSON.stringify(d).includes('secret'));
 assert.equal((await call({lat:35,lon:139},{RAKUTEN_APP_ID:''})).status,503);
 assert.equal((await call({lat:95,lon:139})).status,400);
 assert.equal((await call({lat:35,lon:139},{},{Origin:'https://evil.example'})).status,403);
 globalThis.fetch=async()=>new Response('boom app-secret',{status:500});r=await call({lat:35,lon:139});assert.equal(r.status,502);assert(!(await r.text()).includes('secret'));
 globalThis.fetch=async()=>Response.json(sample);sql.exec('DELETE FROM travel_api_limits');for(let i=0;i<10;i++)assert.equal((await call({lat:35,lon:139})).status,200);assert.equal((await call({lat:35,lon:139})).status,429);
 assert.deepEqual(pickHotels({}),[]);
 console.log('PASS: hotels — affiliate link kept, unsafe links dropped, keys hidden, not-configured 503, bad coordinates, other-site block, rate limit');
}finally{globalThis.fetch=original;sql.close()}
