// Run against a private Sites row projection and a matching frozen material bundle.
// Never reconstruct human answers, workflow state, or identity values.
const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto'), ts=require('typescript');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{fileName:filename,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,filename);
const {researchFor,researchHashes,researchVersions}=require('./lib/research.ts');
const [input,output]=process.argv.slice(2);if(!input||!output)throw Error('input and output required');
if(fs.existsSync(output))throw Error('Output must be new');
const source=JSON.parse(fs.readFileSync(input)), normalized=[],reconstructed=[];
for(const page of source.snapshots){
 if(page.table_name!=='demo_sessions')continue;
 if(page.model_projection.omitted_columns||page.model_projection.omitted_rows)throw Error('Incomplete rows');
 for(const raw of page.rows){
  const row=structuredClone(raw);
  if(!/^[a-zA-Z0-9-]{8,80}$/.test(row.id)||!/^\w{64}$/.test(row.user_id))throw Error('Invalid identity');
  for(const [field,value] of Object.entries(row))if(typeof value==='string'&&value.includes('[truncated for model]')){
   if(!['item_hashes_json','media_hashes_json'].includes(field))throw Error('Human data is truncated; full export required');
   if(!researchVersions.includes(row.dataset_sha256))throw Error('Unknown frozen dataset');
   const assignment=JSON.parse(row.assignment_json),data=researchFor(row.dataset_sha256);
   if(JSON.stringify(data.assignments.find(a=>a.id===assignment.id))!==JSON.stringify(assignment))throw Error('Assignment mismatch');
   const restored=field==='item_hashes_json'?researchHashes(assignment,data):Object.fromEntries(data.items.filter(x=>assignment.item_ids.includes(x.id)).map(x=>[x.id,assignment.track==='offline_video'?x.media:[]]));
   const text=JSON.stringify(restored),prefix=value.slice(0,value.indexOf('… [truncated for model]'));
   if(!prefix||!text.startsWith(prefix))throw Error('Frozen prefix mismatch: '+field);
   row[field]=text;reconstructed.push({project_id:page.project_id,id:row.id,field,dataset_sha256:row.dataset_sha256,source_prefix_verified:true});
  }
  for(const key of Object.keys(row).filter(k=>k.endsWith('_json')))JSON.parse(row[key]);
  normalized.push({project_id:page.project_id,row});
 }
}
if(new Set(normalized.map(x=>x.row.id)).size!==normalized.length||new Set(normalized.map(x=>x.row.user_id)).size!==normalized.length)throw Error('Duplicate identity across Sites; explicit resolution required');
const result={format:'socialflux_sites_migration_v1',source_sha256:crypto.createHash('sha256').update(fs.readFileSync(input)).digest('hex'),
 note:'Human answers and workflow are exact source values. Only truncated deterministic item/media bindings were restored from the exact frozen release, with source prefixes verified.',reconstructed,records:normalized};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
console.log(JSON.stringify({records:normalized.length,submitted:normalized.filter(x=>x.row.status==='submitted').length,restored_frozen_fields:reconstructed.length,human_fields_reconstructed:0}));
