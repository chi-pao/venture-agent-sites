const {chromium}=require('playwright');const fs=require('fs');const d=process.argv[2];
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
await p.goto('file://'+d+'/end.html');await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(1500);
fs.mkdirSync(d+'/endfr',{recursive:true});for(let i=0;i<125;i++){await p.evaluate(t=>render(t),i/25);await p.screenshot({path:`${d}/endfr/${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:90});}
await b.close()})();
