const test = require('node:test');
const assert = require('node:assert/strict');
const {binding, eventsFor, safeMediaUrl} = require('../static/live_multimodal.js');
const asset = {scenario_id:'GPT50_002', asset_type:'online_nonverbal', media_asset_id:'exact', event_family:'engaged'};
const version = {trajectory_id:'current', turns:[{turn_id:'t1', trigger_events:[{media_asset_id:'exact', turn_id:'t01'}]}]};
test('state clips bind only to the exact asset and scenario in the selected rollout', () => {
  assert.equal(binding(asset, 'GPT50_002', version).length, 1);
  assert.equal(binding({...asset, media_asset_id:'other'}, 'GPT50_002', version).length, 0);
  assert.equal(binding(asset, 'GPT50_003', version).length, 0);
  assert.equal(binding(asset, 'GPT50_002', {turns:[]}).length, 0);
  assert.equal(binding({...asset, media_asset_id:null}, 'GPT50_002', {turns:[{trigger_events:[{}]}]}).length, 0);
});
test('old audit events do not count as current triggers', () => {
  assert.equal(binding({...asset, observed_trigger_events:[{turn_id:'t1'}]}, 'GPT50_002', null).length, 0);
  assert.equal(eventsFor(version)[0].turn_id, 't1');
});
test('talking-head binds by trajectory, turn and exact public reply', () => {
  const clip = {...asset, asset_type:'talking_head', trajectory_id:'current', turn_id:'t01', source_public_response:'Okay.'};
  const v = {trajectory_id:'current', turns:[{turn_id:'t1', environment_response:'Okay.'}]};
  assert.equal(binding(clip, 'GPT50_002', v).length, 1);
  assert.equal(binding({...clip, trajectory_id:'old'}, 'GPT50_002', v).length, 0);
  assert.equal(binding({...clip, turn_id:'t2'}, 'GPT50_002', v).length, 0);
  assert.equal(binding({...clip, source_public_response:'Different.'}, 'GPT50_002', v).length, 0);
});
test('video URLs are restricted to the served media routes', () => {
  assert.ok(safeMediaUrl('/online-video/gpt/clip.mp4?v=abcdef1234'));
  assert.ok(safeMediaUrl('/talking-video/gpt/clip--t1.mp4'));
  for (const url of ['https://external.test/clip.mp4', '//external.test', 'javascript:alert(1)', '/online-video/gpt/../secret.mp4', '/online-video/claude/clip.mp4', null]) {
    assert.equal(safeMediaUrl(url), '');
  }
});
