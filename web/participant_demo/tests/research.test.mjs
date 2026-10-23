import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {transition, validateGT, validateRatings, dimensions} from '../lib/research-protocol.ts';
const compressed=JSON.parse(readFileSync(new URL('../data/research-server.json',import.meta.url)));
const data=JSON.parse(gunzipSync(Buffer.from(compressed.gzip_base64,'base64')));
const assignment=data.assignments.find(x=>x.track==='offline_video') || data.assignments.find(x=>x.track==='offline_text');
const questions=data.items.filter(x=>assignment.item_ids.includes(x.id)).map(x=>({...x.public_text,instance_id:x.id}));
const initial={phase:'blind',baselineEligible:true,exclusions:[]};
const answers=Object.fromEntries(questions.map(q=>[q.instance_id,{answer:Object.keys(q.options)[0],confidence:'medium',rationale:'',issue:'none'}]));
test('partial answers cannot unlock private evidence; lock preserves immutable first answers',()=>{
 assert.throws(()=>transition(initial,'lock',{answers:{}},questions,[],'now'));
 assert.throws(()=>transition(initial,'submit',{answers},questions,[],'now'));
 const locked=transition(initial,'lock',{answers},questions,[],'now');assert.equal(locked.workflow.phase,'gt');
 const gt=Object.fromEntries(questions.map(q=>[q.instance_id,{answer:'A',acceptable_answers:['A'],decision:'usable',rationale:'private evidence'}]));
 const final=transition(locked.workflow,'submit',{answers:{},gt,attestation:true},questions,[],'later');
 assert.deepEqual(final.workflow.blind,answers);assert.equal(final.workflow.phase,'complete');assert.throws(()=>transition(final.workflow,'draft',{},questions,[],'again'));
});
test('ambiguous GT cannot be called usable and foreign questions are rejected',()=>{
 const q=questions[0],row={answer:'A',acceptable_answers:['A','B'],decision:'usable',rationale:'ambiguous'};
 assert.throws(()=>validateGT({[q.instance_id]:row},[q],true));
 assert.equal(validateGT({[q.instance_id]:{...row,decision:'revise'}},[q],true)[q.instance_id].decision,'revise');
 assert.throws(()=>validateGT({foreign:row},[q],false));
});
test('T4 requires observed evidence and only recovery may be not applicable',()=>{
 const items=[{id:'x',turn_ids:['t1','t2']}];const ratings={x:Object.fromEntries(dimensions.map(d=>[d,{score:6,evidence_turn_ids:['t1'],rationale:'observed',insufficient_evidence:false}]))};
 assert.deepEqual(validateRatings(ratings,items,true),ratings);
 ratings.x.recovery={score:null,evidence_turn_ids:['t1','t2'],rationale:'no observed setback',insufficient_evidence:true};assert.equal(validateRatings(ratings,items,true).x.recovery.score,null);
 ratings.x.goal_achievement.score=null;assert.throws(()=>validateRatings(ratings,items,true));ratings.x.goal_achievement.score=6;
 ratings.x.goal_achievement.evidence_turn_ids=['t999'];assert.throws(()=>validateRatings(ratings,items,true));
 assert.throws(()=>transition(initial,'submit',{ratings:{}},[],items,'now'));
});
test('sample is fixed at 50 with explicit availability and 38/12 source strata',()=>{
 assert.equal(data.t4.length,50);assert.equal(new Set(data.t4.map(x=>x.id)).size,50);assert.equal(data.sampling.population,200);
 assert.equal(data.t4.filter(x=>x.family==='CF150').length,38);assert.equal(data.t4.filter(x=>x.family==='GPT50').length,12);
 for(const row of data.t4)if(row.machine)assert.equal(row.packet_sha256,row.machine.packet_sha256);
});
test('all 50 scenes have 3/2/3 English questions and available audio/video pairs are complete',()=>{
 assert.equal(data.items.filter(x=>x.media.length).length,data.media_readiness.complete_items);assert.equal(data.items.length,400);
 assert.equal(new Set(data.items.map(x=>x.id)).size,400);
 assert.equal(data.items.filter(x=>x.public_video).length,300);
 assert.equal(new Set(data.items.flatMap(x=>x.media.map(v=>v.sha256))).size,100);
 assert.equal(new Set(data.items.map(x=>x.scene_id)).size,50);
 assert.deepEqual(data.task_difficulty,{T1:{ordinary:90,hard:60},T2:{ordinary:60,hard:40},T3:{ordinary:90,hard:60}});
 for(const scene of new Set(data.items.map(x=>x.scene_id))){
  const items=data.items.filter(x=>x.scene_id===scene);
  assert.deepEqual(Object.fromEntries(['T1','T2','T3'].map(t=>[t,items.filter(x=>x.task===t).length])),{T1:3,T2:2,T3:3});
 }
 for(const item of data.items){
  assert.doesNotMatch(JSON.stringify(item.public_video),/"(?:authoring|ground_truth|initial_state|hidden_intention)"/);
  assert.doesNotMatch(JSON.stringify(item.public_text),/[\u3400-\u9fff]/);
  if(item.public_video)assert.deepEqual({...item.public_video,modality:'text'},item.public_text);
  assert.equal(item.coverage.complete,!!item.public_video);
  for(const video of item.media){
   assert.equal(video.audio_required,true);assert.equal(video.speech_language,'en');assert.ok(video.spoken_text);
   assert.match(video.url,new RegExp(video.sha256+'\\.mp4$'));
   if(video.spoken_scope==='checkpoint_sentence'){
    assert.ok(video.full_public_response && video.source_quote);
    assert.ok(video.full_public_response.includes(video.source_quote));
    assert.ok(video.duration_seconds>=4 && video.duration_seconds<=5.2);
    assert.equal(item.coverage.full_reply_text_preserved,true);
    assert.equal(item.coverage.complete_spoken_response,false);
    const input=item.public_text.input;
    const turns=[...(input.history||[]),...(input.history_a||[]),...(input.history_b||[]),...(input.shared_ending?[input.shared_ending]:[])];
    assert.ok(turns.some(t=>(t.environment_character||t.environment_response||t.current_response)===video.full_public_response));
    assert.ok(['pending','approved_pilot'].includes(video.human_review));
   }
  }
  if(item.task==='T2'){assert.equal(item.public_video,null);assert.deepEqual(item.media,[]);}
 }
 for(const mode of ['offline_text','offline_video']){
  const groups=data.assignments.filter(x=>x.track===mode);
  assert.ok(groups.every(g=>g.scene_ids.length<=5&&g.item_ids.length===8*g.scene_ids.length));
  assert.equal(new Set(groups.flatMap(g=>g.item_ids)).size,400);
  if(mode==='offline_text')assert.equal(groups.length,10);
 }
});
test('the previous human-GT release and its T4 evidence remain available unchanged',()=>{
 const previous=JSON.parse(gunzipSync(Buffer.from(JSON.parse(readFileSync(new URL('../data/research-20261022-v1-server.json',import.meta.url))).gzip_base64,'base64')));
 assert.equal(previous.items.length,300);assert.notEqual(previous.dataset_sha256,data.dataset_sha256);
 assert.deepEqual(data.t4,previous.t4);assert.deepEqual(data.rubric,previous.rubric);
 assert.ok(previous.assignments.filter(x=>x.track==='offline_text').every(x=>x.item_ids.length===30));
});
