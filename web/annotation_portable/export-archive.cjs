// Local administrative migration only. There is no cross-user HTTP export API.
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
if(!process.env.ANNOTATION_DATABASE||!process.env.ANNOTATION_RECEIPTS)throw Error('Private database and archive paths required');
for(const ext of ['.ts','.tsx'])require.extensions[ext]=(module,file)=>module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,file);
const {sqlite,checkpointBackup}=require('./db/index.ts'),{current,exportRecord}=require('./lib/store.ts');
(async()=>{let count=0;for(const {user_id} of sqlite.prepare('SELECT user_id FROM demo_sessions').all()){
 const row=await current(user_id);if(!row)throw Error('Missing frozen release');
 const value=JSON.stringify(exportRecord(row),null,2)+'\n',folder=path.resolve(process.env.ANNOTATION_RECEIPTS,row.id);
 fs.mkdirSync(folder,{recursive:true,mode:0o700});const file=path.join(folder,row.revision+'.json');
 if(fs.existsSync(file)){if(fs.readFileSync(file,'utf8')!==value)throw Error('Archive differs; refuse overwrite');}
 else fs.writeFileSync(file,value,{flag:'wx',mode:0o600});count++;
}await checkpointBackup();console.log(JSON.stringify({archived:count}));sqlite.close();})().catch(e=>{console.error(e.message);process.exitCode=1;});
