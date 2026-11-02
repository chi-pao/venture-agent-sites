// node parity.mjs <site dir> <cand dir>: JavaScript runtime vs Python predictions on the same feature rows
import fs from 'node:fs';import path from 'node:path';import zlib from 'node:zlib';import {pathToFileURL} from 'node:url';
const [site,cand]=process.argv.slice(2).map(p=>path.resolve(p));
const {componentPrediction}=await import(pathToFileURL(path.join(site,'model-runtime.mjs')).href);
const c=JSON.parse(fs.readFileSync(path.join(cand,'component.json'),'utf8'));
const b=zlib.gunzipSync(fs.readFileSync(path.join(cand,'used_house.dat')));const buf=b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);
const {rows,expected}=JSON.parse(fs.readFileSync(path.join(cand,'parity.json'),'utf8'));
let worst=0;rows.forEach((r,i)=>{const got=componentPrediction(r,c,buf);worst=Math.max(worst,Math.abs(got-expected[i])/expected[i]);});
console.log(JSON.stringify({rows:rows.length,worstRelativeDiff:worst}));if(worst>1e-9)process.exit(1);
