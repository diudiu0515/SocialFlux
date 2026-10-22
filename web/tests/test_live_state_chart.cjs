const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/gpt50_live.js'), 'utf8');
const context = vm.createContext({palette: ['green', 'orange', 'blue']});
vm.runInContext(source.slice(source.indexOf('function chartSeries('), source.indexOf('let chartVariable')), context);
const build = (v, s, group) => JSON.parse(JSON.stringify(context.chartSeries(v, s, group)));

const turns = Array.from({length: 20}, (_, i) => ({turn_id: `t${i + 1}`,
  state_after: {emotion: {hope: i % 11, trust: i % 11}}, dynamics_after: {pressure: 0}}));
let chart = build({initial_state: {emotion: {hope: 0, trust: 0}}, turns}, {}, 'emotion');
assert.equal(chart.ticks.length, 21);
assert.equal(chart.ticks.at(-1), 't20');
assert.equal(chart.series.length, 2, 'overlapping variables must remain distinct');
assert.deepEqual(chart.series[0].values, chart.series[1].values);
assert.equal(chart.series[0].values[0], 0);

chart = build({turns: [
  {turn_id: 't3', state_before: {emotion: {hope: 4}}, state_after: {emotion: {hope: 5, trust: 2}}},
  {turn_id: 't4', state_after: {emotion: {trust: 3}}},
]}, {initial_state: {emotion: {hope: 9}}}, 'emotion');
assert.deepEqual(chart.ticks, ['初始', 't3', 't4']);
assert.deepEqual(chart.series[0].values, [4, 5, null], 'use actual initial state and retain gaps');
assert.deepEqual(chart.series[1].values, [null, 2, 3], 'include variables absent from initial state');
chart = build({initial_dynamics: {pressure: 0}, turns}, {}, 'dynamics');
assert.equal(chart.series[0].values.length, 21);
assert.ok(chart.series[0].values.every(n => n === 0));
console.log('State chart data checks passed.');
