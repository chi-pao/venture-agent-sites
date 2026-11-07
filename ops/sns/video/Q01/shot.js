const {chromium}=require('playwright');const d=process.argv[2];
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
const list=[['q1'],['q1c3'],['q1c2'],['q1c1'],['a1'],['a1','pop=0.85'],['q2'],['q2c3'],['q2c2'],['q2c1'],['a2'],['a2','k=0.1'],['a2','k=0.4'],['a2','k=0.75'],['end']];
for(const [s,x] of list){await p.goto(`file://${d}/quiz.html?s=${s}&${x||''}`);await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
await p.screenshot({path:`${d}/f_${s}${x?'_'+x.replace(/[=.]/g,''):''}.png`});}
await b.close()})();
