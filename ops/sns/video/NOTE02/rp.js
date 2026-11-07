const {chromium}=require('playwright');const fs=require('fs');const d=process.argv[2],mode=process.argv[3];
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
await p.goto('file://'+d+'/promo.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(1500);
const tl=JSON.parse(fs.readFileSync(d+'/tl.json'));await p.evaluate(x=>setTL(x),tl);
if(mode==='test'){for(const t of [1,6,9,13,17,22]){await p.evaluate(t=>render(t),t);await p.waitForTimeout(100);await p.screenshot({path:`${d}/P_${t}.png`});}}
else{fs.mkdirSync(d+'/fr',{recursive:true});const n=Math.ceil(tl.total*25);for(let i=0;i<n;i++){await p.evaluate(t=>render(t),i/25);await p.screenshot({path:`${d}/fr/${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:90});}}
await b.close()})();
