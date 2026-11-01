// Page visits only. App form values, property data and OCR images are never read.
const productionOrigin='https://okaidoku-checker.pages.dev';
const trackerHash='e705e5af82ce572ee53bef4fc6e171f3'; // Public Metricool brand tracking identifier.
export function startVisitTracking(win=window,doc=document){
  if(win.location.origin!==productionOrigin||win.__okaidokuVisitTracking)return false;
  if(win.navigator?.globalPrivacyControl===true||['1','yes'].includes(win.navigator?.doNotTrack))return false;
  win.__okaidokuVisitTracking='loading';
  const script=doc.createElement('script');
  script.src='https://tracker.metricool.com/resources/be.js';
  script.async=true;
  script.referrerPolicy='strict-origin-when-cross-origin';
  let sent=false;
  script.onload=()=>{
    if(sent||typeof win.beTracker?.t!=='function')return;
    sent=true;
    try{win.beTracker.t({hash:trackerHash});win.__okaidokuVisitTracking='sent';}
    catch{win.__okaidokuVisitTracking='unavailable';}
  };
  script.onerror=()=>{win.__okaidokuVisitTracking='unavailable';};
  doc.head.appendChild(script);
  return true;
}
if(typeof window!=='undefined'&&typeof document!=='undefined')startVisitTracking();
