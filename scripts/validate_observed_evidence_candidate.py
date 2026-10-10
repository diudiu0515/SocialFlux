#!/usr/bin/env python3
"""One preregistered comparison: remove authored hypothetical transition targets."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import validate_state_context_samples as v
from scripts.resume_state_context_validation import DeadlineProvider, route_config
from rollout.configuration import load_rollout_config
from providers.factory import public_provider_config

OLD=v.OUTPUT
OUT=OLD.parent/'observed_evidence_v6_fixed'
CONFIG=ROOT/'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json'

def main():
    if (OUT/'preregistration.json').exists():
        raise FileExistsError('No repeated run or overwriting evidence')
    frozen=v.load(OLD/'prepared_requests.json')
    env=load_rollout_config(CONFIG)['environment']
    v.PROMPT=env['state_appraisal_prompt_id']
    prepared=[v.prepare_case(item['case'],env) for item in frozen]
    for item,before in zip(prepared,frozen):
        old=deepcopy(before['payload'])
        for entry in old['state_semantics']['variables'].values():
            entry.pop('scenario_transition_evidence',None)
        old['state_semantics']['interpretation']=item['payload']['state_semantics']['interpretation']
        assert old==item['payload'], 'unplanned semantic input difference'
        assert item['request']['generation']==before['request']['generation']
        assert item['request']['messages'][0]==before['request']['messages'][0]
    schedule=[1,3,9,0,2,4,5,6,7,8,10,11]
    routes={i:route_config(env,0 if n%2==0 else 4) for n,i in enumerate(schedule)}
    files=['environment/independent_appraisal.py','environment/calibration.py','environment/appraisal_context.py',
           'environment/public_situation.py','environment/observation.py','scripts/validate_observed_evidence_candidate.py',
           'scripts/validate_state_context_samples.py','scripts/resume_state_context_validation.py',
           'prompts/environment_state_appraisal_v6_observed_evidence.md','prompts/manifest.json',str(CONFIG.relative_to(ROOT))]
    freeze={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
    requests=[{'case':p['case'],'request':p['request'],'payload':p['payload']} for p in prepared]
    v.save(OUT/'preregistration.json',{
        'schedule':schedule,'fixed_count':10,'retests':[10,11],
        'intervention':'Remove scenario_transition_evidence and its matching-target interpretation; no definition/label/delta-rule change',
        'control':'saved v5 outputs; no re-running old scheme to select favorable results',
        'gate':'all 10 fixed and 2 retest calls complete; recognition and required update direction correct for every target; exact strength reported, not a gate',
        'bounded_run':'one logical call per observation; retained bounded schema repairs; no semantic retries; 3 workers; 600s budget per logical call',
        'inputs_sha256':hashlib.sha256(json.dumps(requests,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        'code_sha256':freeze,'routes':{str(i):public_provider_config(c) for i,c in routes.items()},
        'full_scale_authorized':False})
    v.save(OUT/'prepared_requests.json',requests)
    v.OUTPUT=OUT;v.build_provider=DeadlineProvider
    report={'status':'running','rows':{},'full_scale_authorized':False}
    v.save(OUT/'results.json',report)
    print('Frozen inputs checked; start one 10-case set plus 2 predeclared retests',flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending={pool.submit(v.run_one,i,prepared[i],env,routes[i]):i for i in schedule}
        for future in as_completed(pending):
            report['rows'][str(pending[future])]=future.result()
            v.save(OUT/'results.json',report)
    report['status']='completed'
    report['gate_passed']=all(
        r['status']=='completed' and r['recognition_correct'] and r['direction_correct'] and r['call_complete']
        and ((r['target_delta']!='similar') if r['case']['expected_judgment'] in v.NEW else r['target_delta']=='similar')
        for r in report['rows'].values())
    report['summary']={}
    for name,indices in [('fixed',range(10)),('retests',range(10,12))]:
        rows=[report['rows'][str(i)] for i in indices];done=[r for r in rows if r['status']=='completed']
        report['summary'][name]={'scheduled':len(rows),'complete':len(done),**{
            key:sum(bool(r.get(key)) for r in done) for key in
            ['recognition_correct','strength_correct','direction_correct','false_positive','false_negative','call_complete']}}
    report['code_freeze_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in freeze.items())
    assert report['code_freeze_unchanged']
    v.save(OUT/'results.json',report)
    print(json.dumps({'gate_passed':report['gate_passed'],'summary':report['summary']},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
