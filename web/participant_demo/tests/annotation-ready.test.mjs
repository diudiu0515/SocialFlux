import test from 'node:test';
import assert from 'node:assert/strict';
import {transition, dimensions} from '../lib/research-protocol.ts';
import {reviewApplies, reviewComplete, validateReview} from '../lib/gate2-protocol.ts';

const trajectory = [{id:'GPT50_001', turn_ids:['t1','t2']}];
const ratings = {GPT50_001:Object.fromEntries(dimensions.map(d => [d, {
  score:6, evidence_turn_ids:['t1'], rationale:'Observed independent evidence.', insufficient_evidence:false,
}]))};
const task = {id:'T4-trigger:GPT50_001', scene_id:'GPT50_001', kind:'T4-trigger',
  tracks:['t4'], stage:'review', sha256:'bound', title:'Trigger audit', evidence:{},
  questions:[{id:'timing',label:'Timing',choices:{yes:'Appropriate',uncertain:'Insufficient'}}]};
const initial = {phase:'blind', baselineEligible:true, exclusions:[], gate2:{packet_sha256:'packet',answers:{}}};
const review = {[task.id]:{values:{timing:'uncertain'},rationale:'No video for this trigger; this is not a pass.'}};

test('new T4 ratings lock before auditing; missing ratings, review, attestation and foreign tasks fail', () => {
  assert.throws(() => transition(initial,'submit',{ratings:{},attestation:true},[],trajectory,'one',[task]));
  assert.throws(() => transition(initial,'submit',{ratings,attestation:true},[],trajectory,'one',[]));
  const locked = transition(initial,'submit',{ratings,attestation:true,gate2Answers:review},[],trajectory,'one',[task]).workflow;
  assert.equal(locked.phase,'t4_review'); assert.equal(locked.ratingsLockedAt,'one');
  assert.deepEqual(locked.gate2.answers,{}); assert.equal(locked.attestedAt,undefined);
  assert.throws(() => transition(locked,'submit',{gate2Answers:{},attestation:true},[],trajectory,'two',[task]));
  assert.throws(() => transition(locked,'draft',{gate2Answers:{other:review[task.id]}},[],trajectory,'two',[task]));
  assert.throws(() => transition(locked,'submit',{gate2Answers:review},[],trajectory,'two',[task]));
  const changed = structuredClone(ratings); changed.GPT50_001.goal_achievement.score=0;
  const drafted = transition(locked,'draft',{ratings:changed,gate2Answers:review},[],trajectory,'two',[task]).workflow;
  assert.deepEqual(drafted.ratings,ratings); assert.deepEqual(drafted.gate2.answers,review);
  const final = transition(drafted,'submit',{ratings:changed,gate2Answers:review,attestation:true},[],trajectory,'three',[task]).workflow;
  assert.equal(final.phase,'complete'); assert.equal(final.attestedAt,'three'); assert.deepEqual(final.ratings,ratings);
  assert.throws(() => transition(final,'draft',{ratings},[],trajectory,'four',[task]));
});

test('historical T4 sessions retain the original single-stage scoring workflow', () => {
  const old = {phase:'blind',baselineEligible:true,exclusions:[]};
  const result = transition(old,'submit',{ratings,attestation:true},[],trajectory,'one',[]).workflow;
  assert.equal(result.phase,'complete'); assert.equal(result.ratingsLockedAt,undefined);
});

test('T4, offline text and offline audio-video receive only their own review tasks', () => {
  for(const track of ['offline_text','offline_video']) assert.equal(reviewApplies(task,track),false);
  assert.equal(reviewApplies(task,'t4'),true);
  const media = {...task,kind:'media-quality',tracks:['offline_video']};
  assert.equal(reviewApplies(media,'offline_text'),false);
  assert.equal(reviewApplies(media,'offline_video'),true);
  const legacy = {...task,kind:'E8',tracks:undefined};
  assert.equal(reviewApplies(legacy,'offline_text'),true);
  assert.equal(reviewApplies(legacy,'offline_video'),true);
  assert.equal(reviewApplies(legacy,'t4'),false);
});

test('media quality cannot pass without full playback or with contradictory defects; unavailable remains recordable', () => {
  const media={...task,kind:'media-quality',questions:[
    {id:'playback',label:'Playback',choices:{watched_listened:'Watched',unavailable:'Unavailable'}},
    {id:'dialogue',label:'Dialogue',choices:{yes:'Yes',no:'No',uncertain:'Uncertain'}},
    {id:'usability',label:'Use',choices:{usable:'Usable',uncertain:'Uncertain'}},
  ]};
  const row={values:{playback:'unavailable',dialogue:'yes',usability:'usable'},rationale:'QA'};
  assert.equal(reviewComplete(media,{[media.id]:row}),false);
  assert.throws(()=>validateReview({[media.id]:row},[media],true));
  row.values.playback='watched_listened';row.values.dialogue='no';
  assert.throws(()=>validateReview({[media.id]:row},[media],true));
  row.values.playback='unavailable';row.values.dialogue='uncertain';row.values.usability='uncertain';
  assert.equal(reviewComplete(media,{[media.id]:row}),true);
});
