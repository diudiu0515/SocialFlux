#!/usr/bin/env python3
"""GPT50 with the established 10–20 turn rollout contract and current state candidate."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import resume_unified_gpt50 as previous
from scripts import run_unified_gpt50 as batch
from scripts import run_unified_three_pilot as pilot
from scripts.validate_state_context_samples import load,save
from rollout.configuration import load_rollout_config
from pipeline.runtime import build_environment_factory,build_policy
from environment.unified_appraisal import UnifiedEnvironmentFactory
from providers.factory import public_provider_config

OUT=previous.OUT.with_name('unified_current_trust_v1_gpt50_corrected_horizon')


def corrected_plans():
    plans,prior=previous.prepare()
    config=load_rollout_config(batch.CONFIG)
    for p in plans:
        p['environment']['minimum_natural_turns']=config['environment']['minimum_natural_turns']
        p['environment']['response_opportunity_guidance']=config['environment'].get('response_opportunity_guidance',True)
        p['policy']['minimum_natural_turns']=config['policies'][0]['minimum_natural_turns']
        env=UnifiedEnvironmentFactory(build_environment_factory(p['scenario'],p['environment']))()
        policy=build_policy(p['policy'])
        assert env.minimum_natural_turns==env.response_generator.minimum_natural_turns==policy.minimum_natural_turns==10
        assert env.response_opportunity_guidance
        assert p['policy']['runs']==1
    return plans,prior


def prepare():
    plans,prior=corrected_plans()
    public=[{'case':p['case'],'environment':{k:public_provider_config(v) if k.endswith('provider') else v for k,v in p['environment'].items()},
             'policy':{**p['policy'],'provider':public_provider_config(p['policy']['provider'])},
             'initial_observation':p['observation']} for p in plans]
    prereg={**prior,'plans':public,'natural_stop_minimum':10,'minimum_natural_turns':10,
            'response_opportunity_guidance':True,'reuse_completed_call_prefix':False,
            'configuration_repair':'Restore configured minimum 10 for policy/response/termination and v31 opportunity context.',
            'invalid_configuration_source':str(previous.OUT.relative_to(ROOT)),
            'verification_first_scenario':'GPT50_002','remaining_scenarios_after_verification':49,
            'source_call_sha256':{},'code_sha256':{**prior['code_sha256'],
            str(Path(__file__).relative_to(ROOT)):pilot.sha(__file__)}}
    path=OUT/'preregistration.json'
    if path.exists():
        if load(path)!=prereg: raise ValueError('Corrected run changed')
    else: save(path,prereg)
    return plans,prereg


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    plans,prereg=prepare()
    if not args.run:
        print('50 corrected plans: minimum 10, maximum 20, v31 context enabled; no model calls.');return
    if (OUT/'results.json').exists(): raise FileExistsError('Corrected generation already started')
    pilot.OUT=OUT;batch.OUT=OUT
    report={'status':'verifying_corrected_horizon','scheduled_scenarios':50,'rollouts_per_scenario':1,
            'workers':3,'rows':{},'formal_admission':False,'quality_review_status':'pending',
            'configuration_repair':prereg['configuration_repair']}
    save(OUT/'results.json',report)
    # The known one-turn failure is the first of the same fifty slots, not an extra rollout.
    first=1
    print('START corrected GPT50: verify scenario 002 once, then remaining 49 with 3 scenario workers.',flush=True)
    row=pilot.run_one(first,plans[first]);report['rows'][str(first)]=row
    valid=row['status']=='completed' and 10<=row.get('turns',0)<=20 and row.get('ending',{}).get('reason')=='natural_completion'
    if not valid:
        report['status']='stopped_verification_failed';save(OUT/'results.json',report);batch.refresh();return
    report['status']='running';save(OUT/'results.json',report);batch.refresh()
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(pilot.run_one,i,p):i for i,p in enumerate(plans) if i!=first}
        for future in as_completed(futures):
            i=futures[future]
            try: row=future.result()
            except Exception as exc:
                row={'scenario_id':plans[i]['case']['scenario_id'],'policy':'gpt','status':'runner_failure',
                     'error_type':type(exc).__name__,'error':str(exc),'formal_admission':False}
                save(OUT/f"{i:02d}_{row['scenario_id']}_gpt"/'result.json',row)
            report['rows'][str(i)]=row;save(OUT/'results.json',report)
            try: batch.refresh()
            except Exception as exc:print('Export error: '+repr(exc),flush=True)
    report['status']='completed'
    report['completed_scenarios']=sum(r['status']=='completed' for r in report['rows'].values())
    report['failed_scenarios']=50-report['completed_scenarios']
    report['code_freeze_unchanged']=all(pilot.sha(ROOT/p)==h for p,h in prereg['code_sha256'].items())
    save(OUT/'results.json',report);batch.refresh()

if __name__=='__main__':main()
