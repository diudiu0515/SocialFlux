const {chromium}=require('playwright');const assert=require('node:assert/strict');const {randomBytes}=require('node:crypto');const {execFileSync}=require('node:child_process');
const url=process.env.RESEARCH_QA_URL||'http://127.0.0.1:8047',invite='qa-human-gt-invite-20261022-abcdefghijklm';
async function post(c,a,data){const r=await c.request.post(url+'/api/demo/'+a,{data});assert.equal(r.status(),200,await r.text());return r.json();}
(async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});try{const c=await b.newContext();await post(c,'access',{invite});const alias='qa-legacy-flow-'+randomBytes(5).toString('hex'),recoveryCode='SF-'+randomBytes(32).toString('base64url');await post(c,'start',{alias,recoveryCode,assignmentId:'offline_text-01',consent:true,priorExposure:false});
execFileSync('python',['-c',`from pathlib import Path
import sqlite3,json,sys
assert sys.argv[1].startswith('qa-legacy-flow-')
for p in Path('.wrangler/state').glob('**/*.sqlite'):
 db=sqlite3.connect(p)
 if not db.execute("select count(*) from sqlite_master where name='demo_sessions'").fetchone()[0]:db.close();continue
 row=db.execute('select workflow_json from demo_sessions where reviewer_alias=?',(sys.argv[1],)).fetchone()
 if row:
  w=json.loads(row[0]);flow=w.pop('scenarioFlow');w['gate2']={'packet_sha256':flow['sourcePacketSha256'],'answers':{}};db.execute('update demo_sessions set workflow_json=?,revision=revision+1 where reviewer_alias=?',(json.dumps(w),sys.argv[1]));db.commit()
 db.close()`,alias]);
let s=await post(c,'recover',{alias,recoveryCode});assert.equal(s.session.workflow.scenarioFlow,undefined);const p=await c.newPage();await p.goto(url);await p.locator('input[name=research-answer]').first().waitFor();assert.equal(await p.locator('.flow-steps').count(),0);
const body=(s,x)=>({revision:s.session.revision,sceneId:s.session.workflow.sceneSequence.scenes[0].id,...x});s=await post(c,'lock',body(s,{answers:Object.fromEntries(s.research.items.map(x=>[x.id,{answer:'A',confidence:'medium',rationale:'Synthetic legacy QA',issue:'none'}]))}));if(s.session.workflow.phase==='gate2')s=await post(c,'gate2-lock',body(s,{gate2Answers:Object.fromEntries(s.research.gate2Tasks.map(t=>[t.id,{values:Object.fromEntries(t.questions.map(q=>[q.id,Object.keys(q.choices)[0]])),rationale:'Synthetic legacy QA'}]))}));assert.equal(s.session.workflow.phase,'gt');assert.equal(s.research.referenceAnswers.length,8);await p.reload();await p.locator('.scene-answer-summary').waitFor();console.log('PASS: existing version-1 session recovery, original UI, original independent review lock and evidence release');}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});
