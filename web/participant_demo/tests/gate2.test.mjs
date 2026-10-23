import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {transition} from '../lib/research-protocol.ts';
import {validateReview, reviewApplies} from '../lib/gate2-protocol.ts';
import {registryBundle} from '../lib/gate2-registry.ts';
const registryPath = new URL('../data/gate2-review-server.json', import.meta.url);
const rawRegistry = gunzipSync(Buffer.from(JSON.parse(readFileSync(registryPath)).gzip_base64, 'base64'));
const registry = JSON.parse(rawRegistry);
const bundle = registryBundle(registry, registry.current);
const frozenVersions = {
 '00217ce3144c32f8efccf3d6c9eee6d0df19a6aff8778c778e73c4f3b8681617':572,
 '05f0dcc83ff4b008fad3a973bb7611a50eeda2e817f54d3774072ccc02c6ed98':297,
 '0c826b115230ab38224e43463e14b0ba44ce0607123e8517126b902c3a074249':321,
 '35b6ce40392d6f6e2b8bdcbf6c8da7e87bc72ab5c1c38c9d04176f2ab57ea3c3':321,
 '59bc577398b3f2404b05196e6de14f4de8e22563212e4bbab0e2c2cfc8403877':572,
 '6b58d9716e61720d9c79a73b96d4d409da8376a85a3ec06083a66950c0bea424':321,
 '8534808161fd0573af97ce0807034f2cc784d651fda5db80458824cda3a91143':297,
 '8adc261dd33259c5dd66617b8000cdaf9a5b6adf6d7b8857594475c76966d46d':321,
 '90749ccf16b873742bbcf74446bfae9c266a688c94ac6877c6be9d7d395944d9':321,
 'bbdda524393a9fd4329e5c7bcc5607ad78ef9345d4065f2be6a496a7fd440d1f':572,
 'ef5cdc293a340c9e9a12b9da55eb5e3aeb68cf2064412d75fe4b497238f73725':321,
};
const tasks = [bundle.tasks.find(t => t.kind === 'E1'), bundle.tasks.find(t => t.kind === 'E2')];
const answer = t => ({values:Object.fromEntries(t.questions.map(q => [q.id, Object.keys(q.choices)[0]])), rationale:'Observed evidence in the bound packet.'});
const independent = {[tasks[0].id]:answer(tasks[0])};
const initial = {phase:'blind', baselineEligible:true, exclusions:[], gate2:{packet_sha256:bundle.sha256, answers:{}}};
test('new workflow requires independent votes before GT; final submission requires scene reviews', () => {
 const locked = transition(initial, 'lock', {answers:{}}, [], [], 'one', tasks).workflow;
 assert.equal(locked.phase, 'gate2');
 assert.throws(() => transition(locked, 'submit', {gt:{}, attestation:true}, [], [], 'two', tasks));
 assert.throws(() => transition(locked, 'gate2-lock', {gate2Answers:{}}, [], [], 'two', tasks));
 assert.throws(() => transition(locked, 'draft', {gate2Answers:{[tasks[1].id]:answer(tasks[1])}}, [], [], 'two', tasks));
 const gt = transition(locked, 'gate2-lock', {gate2Answers:independent}, [], [], 'two', tasks).workflow;
 assert.equal(gt.phase,'gt'); assert.equal(gt.gate2.independentLockedAt,'two');
 assert.throws(() => transition(gt, 'submit', {gt:{}, gate2Answers:independent, attestation:true}, [], [], 'three', tasks));
 const changed = structuredClone(independent); changed[tasks[0].id].rationale = 'overwrite attempt';
 const final = transition(gt, 'submit', {gt:{}, gate2Answers:{...changed,[tasks[1].id]:answer(tasks[1])},attestation:true}, [], [], 'three', tasks).workflow;
 assert.equal(final.phase,'complete');assert.deepEqual(final.gate2.answers[tasks[0].id], independent[tasks[0].id]);
});
test('review labels, assignment, missing evidence and scalar types are validated', () => {
 assert.throws(() => validateReview({foreign:answer(tasks[0])}, tasks, false));
 assert.throws(() => validateReview({[tasks[0].id]:{values:{bad:'yes'},rationale:'x'}}, tasks, false));
 assert.throws(() => validateReview({[tasks[0].id]:{values:{[tasks[0].questions[0].id]:1},rationale:'x'}}, tasks, false));
 assert.throws(() => validateReview({[tasks[0].id]:{...answer(tasks[0]),rationale:' '}}, [tasks[0]], true));
});
test('review packets keep independent evidence separate and bind exact video bytes', () => {
 const research = JSON.parse(gunzipSync(Buffer.from(JSON.parse(readFileSync(new URL('../data/research-server.json', import.meta.url))).gzip_base64, 'base64')));
 assert.equal(bundle.dataset_sha256, research.dataset_sha256);
 assert.ok(registry.versions.every(b => registryBundle(registry, b.sha256).tasks.every(t => t.sha256 && t.questions.length)));
 assert.equal(bundle.tasks.length,535);
 assert.equal(bundle.tasks.filter(t=>reviewApplies(t,'offline_text')||reviewApplies(t,'offline_video')).length,425);
 assert.equal(bundle.tasks.filter(t=>t.kind==='media-quality').length,100);
 assert.equal(bundle.tasks.filter(t=>t.kind==='E1').length,40);
 assert.equal(bundle.tasks.filter(t=>t.kind==='E2').length,20);
 assert.equal(bundle.tasks.filter(t=>t.kind==='E8').length,40);
 assert.equal(bundle.tasks.filter(t=>t.kind==='E9').length,40);
 for (const t of bundle.tasks.filter(t=>t.stage==='independent')) {
  assert.doesNotMatch(JSON.stringify(t.evidence), /"(?:machine_directions_after_vote|numeric_state_delta|state_after|original_output|paraphrase_output)"/);
 }
 assert.equal(new Set(bundle.tasks.map(t=>t.id)).size,bundle.tasks.length);
});


test('all eleven frozen review versions retain their original task lists and identity', () => {
 assert.equal(Object.keys(frozenVersions).length,11);
 for (const [hash,count] of Object.entries(frozenVersions)) {
  const resolved=registryBundle(registry,hash);
  assert.ok(resolved,`Missing frozen bundle ${hash}`);
  assert.equal(resolved.sha256,hash);
  assert.equal(resolved.tasks.length,count,`Changed task count for ${hash}`);
 }
 assert.equal(registryBundle(registry,'unknown-frozen-version'),undefined);
});

test('registry resolver preserves legacy tasks and rejects missing or mismatched pooled references', () => {
 const task=tasks[0], legacy={sha256:'legacy',dataset_sha256:'dataset',tasks:[task]};
 const oldRegistry={current:'legacy',versions:[legacy]};
 assert.strictEqual(registryBundle(oldRegistry,'legacy'),legacy);
 assert.strictEqual(registryBundle(oldRegistry,'legacy').tasks[0],task);
 const compact={current:'compact',versions:[{sha256:'compact',dataset_sha256:'dataset',task_refs:[task.sha256]}],task_pool:{[task.sha256]:task}};
 assert.strictEqual(registryBundle(compact,'compact').tasks[0],task);
 assert.throws(()=>registryBundle({...compact,task_pool:{}},'compact'),/reference mismatch/i);
 assert.throws(()=>registryBundle({...compact,task_pool:{[task.sha256]:{...task,sha256:'wrong'}}},'compact'),/reference mismatch/i);
 assert.throws(()=>registryBundle({...compact,task_pool:undefined},'compact'),/invalid review registry/i);
});

test('pooled registry references every task directly and shares objects across frozen versions', () => {
 if (registry.format !== 'socialflux_gate2_registry_v2') {
  assert.ok(registry.versions.every(version=>Array.isArray(version.tasks)));
  return;
 }
 const seen=new Map(), referenced=new Set();let shared=0;
 for (const version of registry.versions) {
  assert.equal(Object.hasOwn(version,'tasks'),false,'Stored versions must not duplicate full task objects');
  const resolved=registryBundle(registry,version.sha256);
  assert.equal(resolved.tasks.length,version.task_refs.length);
  version.task_refs.forEach((sha,index)=>{
   assert.ok(Object.hasOwn(registry.task_pool,sha),`Missing task ${sha}`);
   const task=resolved.tasks[index];
   assert.equal(task.sha256,sha);assert.strictEqual(task,registry.task_pool[sha]);
   if(seen.has(sha)){assert.strictEqual(task,seen.get(sha));shared++;}
   else seen.set(sha,task);
   referenced.add(sha);
  });
 }
 assert.ok(shared>0,'Historical versions must share task objects');
 assert.equal(referenced.size,Object.keys(registry.task_pool).length,'Unreferenced tasks would inflate startup memory');
});

test('deduplicated registry stays within measured startup decompression budget', () => {
 // Measured after 100 Offline / 326 Online replacement: 13,812,667 bytes.
 // New media versions retain every historical packet; cap growth to 5% of this release.
 assert.equal(registry.format,'socialflux_gate2_registry_v2');
 assert.ok(rawRegistry.byteLength<=14_500_000,`Registry inflated to ${rawRegistry.byteLength} bytes`);
 assert.ok(rawRegistry.byteLength<43_968_759*0.35,'Deduplication must reduce decompressed data by at least 65%');
});

test('every expanded frozen bundle and pooled task still matches its original canonical hash', () => {
 // Use the builder's Python canonical JSON rule: JS parsing would erase 10.0 vs 10
 // before hashing. Python therefore verifies source bytes, not a JS reserialization.
 const check=spawnSync('python',['-c',String.raw`
import base64,gzip,hashlib,json,sys
with open(sys.argv[1],encoding='utf-8') as handle:
    registry=json.loads(gzip.decompress(base64.b64decode(json.load(handle)['gzip_base64'])))
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
unique={}
for stored in registry['versions']:
    bundle={k:v for k,v in stored.items() if k!='task_refs'}
    if 'task_refs' in stored:
        bundle['tasks']=[registry['task_pool'][sha] for sha in stored['task_refs']]
    assert digest({k:v for k,v in bundle.items() if k!='sha256'})==bundle['sha256'], 'Changed bundle '+bundle['sha256']
    for task in bundle['tasks']:
        previous=unique.setdefault(task['sha256'],task)
        assert previous==task, 'Conflicting task payload '+task['sha256']
for sha,task in unique.items():
    assert digest({k:v for k,v in task.items() if k!='sha256'})==sha, 'Changed task '+sha
print(json.dumps({'bundles':len(registry['versions']),'uniqueTasks':len(unique)}))
`,fileURLToPath(registryPath)],{encoding:'utf8'});
 assert.equal(check.status,0,check.stderr||check.stdout);
 const validated=JSON.parse(check.stdout);
 assert.equal(validated.bundles,registry.versions.length);
 assert.equal(validated.uniqueTasks,new Set(registry.versions.flatMap(version=>registryBundle(registry,version.sha256).tasks.map(task=>task.sha256))).size);
});
