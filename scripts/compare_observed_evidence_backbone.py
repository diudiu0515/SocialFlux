#!/usr/bin/env python3
"""One alternate-backbone run on the exact v6 observations; no semantic edits."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import validate_state_context_samples as v
from scripts.resume_state_context_validation import DeadlineProvider
from providers.factory import public_provider_config
from rollout.configuration import load_rollout_config

SOURCE=v.BASE/'observed_evidence_v6_fixed'
OUT=v.BASE/'observed_evidence_v6_fable_comparison'

def main():
    if (OUT/'preregistration.json').exists():
        raise FileExistsError('No repeated run or overwriting results')
    env=load_rollout_config(ROOT/'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json')['environment']
    frozen=v.load(SOURCE/'prepared_requests.json')
    v.PROMPT=env['state_appraisal_prompt_id']
    prepared=[v.prepare_case(item['case'],env) for item in frozen]
    for item,old in zip(prepared,frozen):
        assert item['request']==old['request'],'backbone comparison changed prompt/payload/sampling'
    provider=deepcopy(env['response_provider']['candidates'][1])
    assert provider['provider']=='openai_compatible' and provider['model']=='claude-fable-5'
    provider.update(timeout=600,max_transport_attempts=1,stream=False)
    schedule=[1,3,9,0,2,4,5,6,7,8,10,11]
    files=['environment/independent_appraisal.py','environment/calibration.py','environment/appraisal_context.py',
           'environment/public_situation.py','scripts/compare_observed_evidence_backbone.py',
           'scripts/validate_state_context_samples.py','scripts/resume_state_context_validation.py',
           'prompts/environment_state_appraisal_v6_observed_evidence.md']
    freeze={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}
    v.save(OUT/'preregistration.json',{'source':str(SOURCE),'schedule':schedule,'fixed_count':10,'retests':[10,11],
        'change':'appraiser backbone only; existing approved Fable chat route; Fable has no Astra reasoning_effort option',
        'provider':public_provider_config(provider),'request_identity_asserted':True,'code_sha256':freeze,
        'gate':'all 12 observations complete and correct target recognition/update direction; no negative false positive; exact strength reported separately',
        'workers':3,'semantic_retries':0,'full_scale_authorized':False})
    v.save(OUT/'prepared_requests.json',frozen)
    v.OUTPUT=OUT;v.build_provider=DeadlineProvider
    report={'status':'running','rows':{},'full_scale_authorized':False};v.save(OUT/'results.json',report)
    print('Fable: identical 12 logical inputs verified; one predeclared comparison',flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(v.run_one,i,prepared[i],env,provider):i for i in schedule}
        for future in as_completed(futures):
            report['rows'][str(futures[future])]=future.result();v.save(OUT/'results.json',report)
    report['status']='completed'
    report['gate_passed']=all(r['status']=='completed' and r['call_complete'] and r['recognition_correct'] and r['direction_correct']
        and ((r['target_delta']!='similar') if r['case']['expected_judgment'] in v.NEW else r['target_delta']=='similar')
        for r in report['rows'].values())
    report['summary']={}
    for name,indices in [('fixed',range(10)),('retests',range(10,12))]:
        rows=[report['rows'][str(i)] for i in indices];done=[r for r in rows if r['status']=='completed']
        report['summary'][name]={'scheduled':len(rows),'complete':len(done),**{
            k:sum(bool(r.get(k)) for r in done) for k in ['recognition_correct','strength_correct','direction_correct','false_positive','false_negative','call_complete']}}
    report['code_freeze_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in freeze.items())
    assert report['code_freeze_unchanged'];v.save(OUT/'results.json',report)
    print(json.dumps({'gate_passed':report['gate_passed'],'summary':report['summary']},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
