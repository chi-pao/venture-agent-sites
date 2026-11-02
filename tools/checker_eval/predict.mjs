// usage: node predict.mjs <site dir> <inputs.json>  -> prints one estimate (万円) per input
import fs from 'node:fs';import path from 'node:path';import zlib from 'node:zlib';import {pathToFileURL} from 'node:url';
const site=path.resolve(process.argv[2]);
const {features,componentPrediction,combine}=await import(pathToFileURL(path.join(site,'engine.mjs')).href);
const catalog=JSON.parse(fs.readFileSync(path.join(site,'models/catalog.json'),'utf8'));
const buf={};const load=p=>{if(!buf[p]){const b=zlib.gunzipSync(fs.readFileSync(path.join(site,p)));buf[p]=b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}return buf[p]};
const inputs=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const out=inputs.map(input=>{const m=catalog.models[input.type];const row=features(input);const v=m.components.map(c=>componentPrediction(row,c,load(c.path)));return Math.round(combine(v,m.components)/10000)});
console.log(JSON.stringify(out));
