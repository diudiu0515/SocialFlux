import {createServer, type IncomingMessage} from 'node:http';
import {createHash, timingSafeEqual} from 'node:crypto';
import {readFileSync, mkdirSync, writeFileSync, renameSync, openSync, fsyncSync, closeSync, statSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {spawnSync} from 'node:child_process';
import {current, start, save, payload, evidence, exportRecord, ConflictError, researchCatalog} from './lib/store';
import {InputError} from './lib/protocol';
import {recoveryPattern} from './lib/credentials';
import {sqlite, checkpointBackup} from './db';

const secretFile=process.env.ANNOTATION_PROXY_SECRET_FILE;
if(!secretFile) throw new Error('Missing trusted local proxy secret');
const secret=readFileSync(secretFile,'utf8').trim();
const archive=process.env.ANNOTATION_RECEIPTS;
if(!archive)throw new Error('Missing durable receipt archive');
mkdirSync(archive,{recursive:true,mode:0o700});
function equal(a:string,b:string){const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);}
function userId(code:unknown){if(typeof code!=='string'||!recoveryPattern.test(code))throw new InputError('请提供完整恢复码。');return createHash('sha256').update(code).digest('hex');}
async function body(req:IncomingMessage){let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>1000000)throw new InputError('内容过长。');}const value=JSON.parse(raw);if(!value||typeof value!=='object'||Array.isArray(value))throw new InputError('请求格式无效。');return value;}
function archiveReceipt(row:any){
 const value=exportRecord(row), folder=resolve(archive!,row.id);mkdirSync(folder,{recursive:true,mode:0o700});
 const target=resolve(folder,`${row.revision}.json`),text=JSON.stringify(value,null,2)+'\n';
 try {if(readFileSync(target,'utf8')!==text)throw new Error('Receipt revision conflict');return;}catch(error:any){if(error.code!=='ENOENT')throw error;}
 const temporary=target+'.'+crypto.randomUUID()+'.tmp';
 const fd=openSync(temporary,'wx',0o600);try{writeFileSync(fd,text);fsyncSync(fd);}finally{closeSync(fd);}renameSync(temporary,target);
 const directory=openSync(folder,'r');try{fsyncSync(directory);}finally{closeSync(directory);}
}
let backupQueue=Promise.resolve();
async function durable(row:any){
 archiveReceipt(row);backupQueue=backupQueue.catch(()=>{}).then(()=>checkpointBackup()).then(()=>{});await backupQueue;
 if(process.env.ANNOTATION_IMPORT_SCRIPT&&exportRecord(row).format==='socialflux_human_gt_v1'){
  const run=spawnSync(process.env.ANNOTATION_PYTHON||'python',[process.env.ANNOTATION_IMPORT_SCRIPT,resolve(archive!,row.id,`${row.revision}.json`)],{cwd:process.env.ANNOTATION_RESEARCH_ROOT,encoding:'utf8',timeout:15000});
  if(run.status!==0)console.error('Receipt is durably saved; summary import pending.');
 }
}
const server=createServer(async(req,res)=>{
 const reply=(status:number,value:any,extra:Record<string,string>={})=>{const bytes=Buffer.from(JSON.stringify(value));res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Content-Length':String(bytes.length),...extra});res.end(bytes);};
 if(!equal(String(req.headers['x-socialflux-proxy']||''),secret)){req.resume();return reply(401,{error:'未授权'});}
 const action=new URL(req.url!,'http://127.0.0.1').pathname.split('/').at(-1)!;
 try{
  if(action==='health')return reply(200,{ok:true,storage:'sqlite',sessions:(sqlite.prepare('SELECT count(*) AS n FROM demo_sessions').get() as any).n});
  const token=req.headers['x-annotation-recovery'];
  if(req.method==='GET'){
   const row=token?await current(userId(token)):undefined;
   if(action==='status')return reply(200,row?{...payload(row),invited:true}:{session:null,invited:true,catalog:researchCatalog()});
   if(action==='export'&&row)return reply(200,exportRecord(row),{'Content-Disposition':'attachment; filename="socialflux-annotation.json"'});
   return reply(row?404:401,{error:row?'没有这个接口。':'请先开始或恢复标注。'});
  }
  if(req.method!=='POST'||!String(req.headers['content-type']).startsWith('application/json')){req.resume();return reply(400,{error:'请求格式无效。'});}
  const data=await body(req);
  if(action==='logout')return reply(200,{ok:true});
  if(action==='start'||action==='recover'){
   const id=userId(data.recoveryCode),previous=await current(id);
   if(previous&&previous.alias!==String(data.alias).trim())return reply(401,{error:'编号或恢复码不匹配。'});
   if(action==='recover'&&!previous)return reply(401,{error:'编号或恢复码不匹配。'});
   if(previous)return reply(200,{...payload(previous),invited:true});
   const result=await start(id,{...data,ownerUserId:'recovery-code'});await durable(await current(id));return reply(200,{...result,invited:true});
  }
  const id=userId(token),row=await current(id);
  if(!row)return reply(401,{error:'请使用编号和恢复码恢复标注。'});
  if(action==='evidence')return reply(200,evidence(row,data.instanceId));
  if(!['draft','submit','lock','gate2-lock'].includes(action))return reply(404,{error:'没有这个接口。'});
  const result=await save(id,data,action==='submit',action);await durable(await current(id));return reply(200,{...result,invited:true});
 }catch(error:any){reply(error instanceof ConflictError?409:error instanceof InputError||error instanceof SyntaxError?400:503,{error:error instanceof InputError||error instanceof ConflictError?error.message:'保存暂未确认，请保留页面并重试。'});if(!(error instanceof InputError||error instanceof ConflictError))console.error(error.message);}
});
server.listen(Number(process.env.ANNOTATION_PORT||6067),'127.0.0.1',()=>console.log('Annotation storage ready on local port '+(process.env.ANNOTATION_PORT||6067)));
