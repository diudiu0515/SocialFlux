import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validateAnswers,validateMediaReviews} from '../lib/protocol.ts';
const bundle=JSON.parse(readFileSync(new URL('../data/multimodal.json',import.meta.url)));
const videos=bundle.videos;
const reviewed=Object.fromEntries(videos.map(v=>[v.asset_id,{verdict:'usable',issues:[],note:'',watched:true}]));
test('all current videos appear exactly once, bound to public scene questions and file hashes',()=>{
 assert.equal(videos.length,52);assert.equal(new Set(videos.map(v=>v.sha256)).size,52);assert.equal(bundle.scenes.length,45);assert.equal(bundle.items.length,270);
 assert.equal(videos.filter(v=>v.kind==='talking_head').length,7);assert.equal(videos.filter(v=>v.kind==='nonverbal').length,45);
 const ids=new Set(bundle.items.map(row=>row.public.instance_id));
 for(const v of videos){assert.match(v.url,/^\/media\/[a-f0-9]{64}\.mp4$/);assert.equal(createHash('sha256').update(readFileSync(new URL('../public'+v.url,import.meta.url))).digest('hex'),v.sha256);assert.ok(v.bindings.every(b=>ids.has(b.instance_id)));if(v.kind==='talking_head'){assert.doesNotMatch(v.spoken_text,/[\u3400-\u9fff]/);assert.ok(v.bindings.every(b=>b.evidence_ids.every(id=>id==='ending')));}}
 for(const row of bundle.items){assert.deepEqual(Object.keys(row.public).sort(),['input','instance_id','modality','options','question']);}
 assert.doesNotMatch(JSON.stringify(bundle),/"(?:authoring|oracle|reference_answer|ground_truth|private_state|state_after|scenario_source|provider_states)"/);
});
test('a single per-video review is reused and optional question answering does not block media review',()=>{
 assert.deepEqual(validateMediaReviews(reviewed,videos,true),reviewed);assert.deepEqual(validateAnswers({},bundle.items.map(row=>row.public)),{});
 const missing=structuredClone(reviewed);delete missing[videos[0].asset_id];assert.throws(()=>validateMediaReviews(missing,videos,true));
});
test('media reviews reject foreign ids, hidden fields, contradictory usable flags and missing viewing confirmation',()=>{
 assert.throws(()=>validateMediaReviews({...reviewed,foreign:{}},videos));
 for(const change of [{sha256:'forged'},{verdict:'approved'},{issues:['foreign']},{issues:['audio','audio']},{note:'x'.repeat(2001)},{watched:false},{issues:['lip_sync']}]){
  const copy=structuredClone(reviewed);Object.assign(copy[videos[0].asset_id],change);assert.throws(()=>validateMediaReviews(copy,videos,true));
 }
});
test('unplayable videos can be reported and negative decisions require a reason',()=>{
 const copy=structuredClone(reviewed);copy[videos[0].asset_id]={verdict:'uncertain',issues:['playback'],note:'Video does not load',watched:false};assert.doesNotThrow(()=>validateMediaReviews(copy,videos,true));
 copy[videos[0].asset_id]={verdict:'unusable',issues:[],note:'',watched:true};assert.throws(()=>validateMediaReviews(copy,videos,true));
 copy[videos[0].asset_id].note='Wrong context';assert.doesNotThrow(()=>validateMediaReviews(copy,videos,true));
});
