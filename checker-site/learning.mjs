export const learningRoot='https://raw.githubusercontent.com/chi-pao/-/main/';
export const learningManifestUrl=learningRoot+'site-models/manifest.json';
function improves(before,after){return before&&after&&[before.median_ape_pct,before.mae_yen,before.within20_pct,after.median_ape_pct,after.mae_yen,after.within20_pct].every(Number.isFinite)&&after.median_ape_pct<=before.median_ape_pct-.5&&after.mae_yen<=before.mae_yen*1.01&&after.within20_pct>=before.within20_pct-1;}
export function acceptedLearning(manifest,catalog){
  const m=manifest,e=m?.evaluation;
  if(![1,2].includes(m?.schema)||m.status!=='approved'||m.model_key!=='used_house'||!/^[a-f0-9]{64}$/.test(m.model_sha256||''))return false;
  const deployedSha=catalog.models.used_house.sourceSha256;
  if(m.baseline_sha256!==deployedSha&&(m.baseline_sha256!==catalog.previousModels?.used_house.sourceSha256||m.deployed_incumbent_sha256!==deployedSha||!improves(e?.deployed_incumbent,e?.challenger)))return false;
  if(m.reference?.year!==catalog.reference.year||m.reference?.quarter!==catalog.reference.quarter)return false;
  if(!e||e.holdout_rows<200||!Number.isInteger(e.holdout_year)||e.holdout_year<1900||!/^[a-f0-9]{64}$/.test(e.holdout_sha256||''))return false;
  const proof=e.independence;
  const audited=proof?.method==='audited_unused_rows'&&/^[a-f0-9]{64}$/.test(proof.audit_sha256||'')&&proof.holdout_sha256===e.holdout_sha256&&proof.approved_model_sha256===m.model_sha256&&proof.training_disjoint===true&&proof.selection_disjoint===true&&proof.source_identity_verified===true&&Array.isArray(proof.verified_model_sha256)&&proof.verified_model_sha256.length>=2&&proof.verified_model_sha256.every(h=>/^[a-f0-9]{64}$/.test(h))&&proof.verified_model_sha256.includes(m.baseline_sha256);
  if(proof?.method==='audited_unused_rows'&&!audited)return false;
  if(!audited&&e.holdout_year<=Math.max(m.training_end_year,m.baseline_training_end_year))return false;
  if(!Number.isInteger(m.training_end_year)||!Number.isInteger(m.baseline_training_end_year)||!improves(e.baseline,e.challenger)||!improves(e.incumbent,e.challenger))return false;
  const components=m.model?.components;if(!Array.isArray(components)||!components.length||components.length>50||components.filter(c=>c.region==null).length!==1||!Number.isFinite(m.model.regionalWeight)||m.model.regionalWeight<0||m.model.regionalWeight>1)return false;
  return components.every(c=>c.algorithm==='lightgbm'&&c.postprocess==='v8_log_man'&&c.path.startsWith('site-models/versions/'+m.model_sha256+'/')&&/^site-models\/versions\/[a-f0-9]{64}\/[a-z0-9-]+\.dat$/.test(c.path)&&/^[a-f0-9]{64}$/.test(c.sha256)&&c.bytes>0&&c.bytes<25000000&&
    (m.schema===1?!(c.categoricalSplits?.length):Array.isArray(c.categoricalSplits)&&c.categoricalSplits.every(set=>Array.isArray(set)&&set.length>0&&set.every(v=>Number.isInteger(v)&&v>=0))));
}
