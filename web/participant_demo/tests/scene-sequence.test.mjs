import test from 'node:test';
import assert from 'node:assert/strict';
import {transition, activeScene} from '../lib/research-protocol.ts';
const scenes=[{id:'one',itemIds:['q1','q2']},{id:'two',itemIds:['q3','q4']}];
const questions=scenes.flatMap(s=>s.itemIds.map(instance_id=>({instance_id,options:{A:'a',B:'b'}})));
const tasks=scenes.flatMap(s=>['independent','review'].map(stage=>({id:s.id+stage,scene_id:s.id,kind:'scenario',title:'review',stage,sha256:'hash',evidence:{},questions:[{id:'ok',choices:{yes:'yes'}}]})));
const answer={answer:'A',confidence:'medium',rationale:'public only',issue:'none'};
const gt={answer:'B',acceptable_answers:['B'],decision:'usable',rationale:'checked evidence'};
const review={values:{ok:'yes'},rationale:'checked'};
const initial=()=>({phase:'blind',baselineEligible:true,exclusions:[],sceneSequence:{version:1,scenes,index:0,completed:{}},gate2:{packet_sha256:'hash',answers:{}}});
const go=(w,action,data={})=>transition(w,action,{sceneId:activeScene(w)?.id,...data},questions,[],'time-'+action,tasks);
function finish(w){const scene=activeScene(w),answers=Object.fromEntries(scene.itemIds.map(id=>[id,answer]));
 w=go(w,'lock',{answers}).workflow;assert.equal(w.phase,'gate2');
 w=go(w,'gate2-lock',{gate2Answers:{[scene.id+'independent']:review}}).workflow;
 const judgments=Object.fromEntries(scene.itemIds.map(id=>[id,gt]));
 return go(w,'submit',{gt:judgments,gate2Answers:{[scene.id+'independent']:review,[scene.id+'review']:review},attestation:true});
}
test('each scene locks its complete blind answers, preserves independent reviews and then unlocks next',()=>{
 let w=initial();assert.throws(()=>go(w,'lock',{answers:{q1:answer}}));assert.throws(()=>go(w,'submit',{attestation:true}));
 const first=finish(w);w=first.workflow;assert.equal(w.phase,'blind');assert.equal(activeScene(w).id,'two');assert.deepEqual(Object.keys(w.blind),['q1','q2']);assert.equal(w.blindLockedAt,undefined);assert.equal(w.gate2.independentLockedAt,undefined);assert.equal(w.sceneSequence.completed.one.blindLockedAt,'time-lock');
 assert.equal(w.gt.q1.answer,'B');assert.equal(w.blind.q1.answer,'A');
 const final=finish(structuredClone(w));assert.equal(final.workflow.phase,'complete');assert.equal(final.workflow.sceneSequence.index,2);assert.equal(Object.keys(final.workflow.blind).length,4);assert.equal(Object.keys(final.workflow.gt).length,4);assert.equal(Object.keys(final.workflow.gate2.answers).length,4);
 assert.throws(()=>go(final.workflow,'draft'));
});
test('future scene writes and stale scene replays fail; completed scene votes cannot change',()=>{
 let w=initial();assert.throws(()=>go(w,'draft',{answers:{q3:answer}}),/当前场景/);
 assert.throws(()=>go(w,'draft',{gt:{q3:gt}}),/当前场景/);
 assert.throws(()=>go(w,'draft',{gate2Answers:{twoindependent:review}}),/当前场景/);
 assert.throws(()=>go(w,'draft',{sceneId:'two',answers:{}}),/场景已变化/);
 w=finish(w).workflow;
 assert.throws(()=>go(w,'draft',{sceneId:'one'}),/场景已变化/);
 assert.throws(()=>go(w,'draft',{answers:{q1:{...answer,answer:'B'}}}),/不能修改/);
 assert.throws(()=>go(w,'draft',{gt:{q1:{...gt,answer:'A'}}}),/不能修改/);
 assert.throws(()=>go(w,'draft',{gate2Answers:{oneindependent:{...review,rationale:'changed'}}}),/不能修改/);
 const draft=go(w,'draft',{answers:{...w.blind,q3:answer},gt:w.gt,gate2Answers:w.gate2.answers});
 assert.equal(draft.answers.q3.answer,'A');assert.deepEqual(draft.workflow.blind,w.blind);
});
test('current scene blind answers cannot change during evidence review, and incomplete audits cannot advance',()=>{
 let w=go(initial(),'lock',{answers:{q1:answer,q2:answer}}).workflow;
 assert.throws(()=>go(w,'draft',{answers:{q1:{...answer,answer:'B'}}}),/已经锁定/);
 assert.throws(()=>go(w,'gate2-lock',{gate2Answers:{}}));
 w=go(w,'gate2-lock',{gate2Answers:{oneindependent:review}}).workflow;
 assert.throws(()=>go(w,'submit',{gt:{q1:gt,q2:gt},gate2Answers:{oneindependent:review},attestation:true}));
 assert.equal(activeScene(w).id,'one');
});
