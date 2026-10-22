import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreMediaSnapshot} from '../lib/research-snapshots.ts';

const current = {release:'new',dataset_sha256:'new-data',source_bank_sha256:'bank',assignments:[],
  items:[{id:'q1',item_sha256:'same-question',public_text:{modality:'text',input:{line:'Frozen dialogue'}},
    public_video:null,media:[],coverage:{complete:false}}]};
const snapshot = {release:'earlier',dataset_sha256:'old-data',source_bank_sha256:'bank',
  assignments:[{id:'offline_video-01',item_ids:['q1']}],items:[{id:'q1',item_sha256:'same-question',
    has_video:true,media:[{sha256:'old-video',url:'/media/old-video.mp4'}],coverage:{complete:true}}]};

test('an old session restores its exact assignment and media even if current availability changes',()=>{
  const restored = restoreMediaSnapshot(current,snapshot);
  assert.equal(restored.dataset_sha256,'old-data');
  assert.deepEqual(restored.assignments,snapshot.assignments);
  assert.deepEqual(restored.items[0].media,snapshot.items[0].media);
  assert.equal(restored.items[0].public_video.modality,'text+video');
  assert.equal(current.items[0].public_video,null);
});
test('a prior text session does not acquire videos from a later release',()=>{
  const text=structuredClone(snapshot);text.items[0].has_video=false;text.items[0].media=[];
  assert.equal(restoreMediaSnapshot(current,text).items[0].public_video,null);
});
test('changed questions, missing rows, duplicate rows or a different bank cannot restore a snapshot',()=>{
  for(const mutate of [x=>x.source_bank_sha256='other',x=>x.items[0].item_sha256='changed',
    x=>x.items=[],x=>x.items.push(x.items[0])]){
    const invalid=structuredClone(snapshot);mutate(invalid);
    assert.throws(()=>restoreMediaSnapshot(current,invalid));
  }
});
