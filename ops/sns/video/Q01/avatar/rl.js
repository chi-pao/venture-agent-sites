const {chromium}=require('playwright');const fs=require('fs');const d=process.argv[2],mode=process.argv[3];
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
await p.goto('file://'+d+'/layers.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(1500);
const tl=JSON.parse(fs.readFileSync(d+'/tl.json'));await p.evaluate(x=>setTL(x),tl.tl);
if(mode==='test'){for(const t of [0.2,1,8,14,30,48]){for(const l of ['bg','fg']){await p.evaluate(([t,l])=>render(t,l),[t,l]);await p.screenshot({path:`${d}/T_${l}_${t}.png`,omitBackground:l==='fg'});}}}
else{for(const l of ['bg','fg']){fs.mkdirSync(`${d}/${l}`,{recursive:true});const n=Math.ceil(tl.total*30);for(let i=0;i<n;i++){await p.evaluate(([t,l])=>render(t,l),[i/30,l]);await p.screenshot({path:`${d}/${l}/${String(i).padStart(5,'0')}.${l==='bg'?'jpg':'png'}`,type:l==='bg'?'jpeg':'png',quality:l==='bg'?90:undefined,omitBackground:l==='fg'});}}}
await b.close()})();
