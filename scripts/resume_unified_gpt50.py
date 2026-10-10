#!/usr/bin/env python3
"""Resume one rollout per GPT50 scenario, with concurrency across scenarios."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_unified_gpt50 as batch
from scripts import run_unified_three_pilot as pilot
from scripts.recover_exploratory_response_budget import ReplayPrefixProvider
from scripts.validate_state_context_samples import load,save
from scripts.resume_state_context_validation import route_config
from providers.factory import public_provider_config

SOURCE=batch.OUT
OUT=SOURCE.with_name('unified_current_trust_v1_gpt50_resumed')
WORKERS=3
AUTHORIZATION='每个scenario去生成一个rollout；可以同时多生成几个场景，利用现有密钥和接口。'


def prepare():
    previous=load(SOURCE/'results.json')
    if previous['status']!='stopped_by_user' or previous['rows']:
        raise ValueError('This continuation requires the stopped batch with no completed rollouts')
    original=load(SOURCE/'preregistration.json')
    for path,digest in original['code_sha256'].items():
        if pilot.sha(ROOT/path)!=digest:
            raise ValueError('Original frozen input or runtime changed: '+path)
    selected=batch.plans()
    assert len(selected)==50 and len({p['case']['scenario_id'] for p in selected})==50
    for index,plan in enumerate(selected):
        env=plan['environment']
        # Same model and sampling; distribute work across existing credential routes.
        route=route_config(env if 'state_appraisal_provider' not in env else
                           {k:v for k,v in env.items() if k!='state_appraisal_provider'},
                           (0,2,4)[index%3])
        env['state_appraisal_provider']=route
        env['interaction_appraisal_provider']=deepcopy(route)
        policy=plan['policy']['provider']
        for key in ('api_key_env','api_key_file','endpoint','provider','use_proxy'):
            policy.pop(key,None)
            if key in route: policy[key]=route[key]
        response=env['response_provider']
        candidates=response['candidates']
        chosen=deepcopy(candidates[0 if index%2==0 else 2])
        response['candidates']=[chosen]
        response['max_candidates_per_request']=1
        assert plan['policy']['runs']==1
    logs={}
    for path in SOURCE.glob('*/calls/*/requests.json'):
        rows=load(path)
        # Only completed prefix + one interrupted request may be continued.
        if any('error' in row for row in rows):
            raise ValueError('Semantic/call failure requires separate review: '+str(path))
        if any('raw_output' not in row for row in rows[:-1]):
            raise ValueError('Incomplete saved prefix: '+str(path))
        logs[str(path.relative_to(SOURCE))]=pilot.sha(path)
    public=[{'case':p['case'],'environment':{k:public_provider_config(v) if k.endswith('provider') else v for k,v in p['environment'].items()},
             'policy':{**p['policy'],'provider':public_provider_config(p['policy']['provider'])},
             'initial_observation':p['observation']} for p in selected]
    prereg={**original,'plans':public,'user_authorization':AUTHORIZATION,'workers':WORKERS,
            'rollouts_per_scenario':1,'scenario_count':50,'continuation_source':str(SOURCE.relative_to(ROOT)),
            'source_call_sha256':logs,'reuse_completed_call_prefix':True,
            'transport_change':'Round-robin existing GPT credential routes 0/2/4 and Fable routes 0/2; no model/sampling change.',
            'code_sha256':{**original['code_sha256'],str(Path(__file__).relative_to(ROOT)):pilot.sha(__file__),
                           'scripts/recover_exploratory_response_budget.py':pilot.sha(ROOT/'scripts/recover_exploratory_response_budget.py')}}
    path=OUT/'preregistration.json'
    if path.exists():
        if load(path)!=prereg: raise ValueError('Continuation plan changed')
    else: save(path,prereg)
    return selected,prereg


def install_replay_logging():
    log_provider=pilot.RoleLogProvider
    def wrap(provider,directory,expected):
        relative=directory.relative_to(OUT)/'requests.json'
        old=SOURCE/relative
        if old.exists():
            rows=load(old)
            complete=[r for r in rows if 'raw_output' in r]
            interrupted=rows[-1] if rows and 'raw_output' not in rows[-1] else None
            provider=ReplayPrefixProvider(provider,complete,old,failed=interrupted)
        return log_provider(provider,directory,expected)
    pilot.RoleLogProvider=wrap


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    selected,prereg=prepare()
    if not args.run:
        print('Prepared 50 unique scenarios x 1 rollout; 3 concurrent scenarios; reuse saved policy calls.',flush=True)
        return
    if (OUT/'results.json').exists(): raise FileExistsError('Continuation already started')
    pilot.OUT=OUT
    batch.OUT=OUT
    install_replay_logging()
    report={'status':'running','user_authorization':AUTHORIZATION,'scheduled_scenarios':50,
            'rollouts_per_scenario':1,'workers':WORKERS,'rows':{},'formal_admission':False,
            'quality_review_status':'pending','continuation_source':str(SOURCE.relative_to(ROOT))}
    save(OUT/'results.json',report)
    print('START: 50 scenarios x 1 rollout; 3 concurrent scenarios; saved prefix replay enabled.',flush=True)
    batch.refresh()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(pilot.run_one,i,p):i for i,p in enumerate(selected)}
        for future in as_completed(futures):
            index=futures[future]
            try: row=future.result()
            except Exception as exc:
                row={'scenario_id':selected[index]['case']['scenario_id'],'policy':'gpt','status':'runner_failure',
                     'error_type':type(exc).__name__,'error':str(exc),'formal_admission':False}
                save(OUT/f"{index:02d}_{row['scenario_id']}_gpt"/'result.json',row)
            report['rows'][str(index)]=row
            save(OUT/'results.json',report)
            try: batch.refresh()
            except Exception as exc: print('Export error, raw records retained: '+repr(exc),flush=True)
    report['status']='completed'
    report['completed_scenarios']=sum(r['status']=='completed' for r in report['rows'].values())
    report['failed_scenarios']=50-report['completed_scenarios']
    report['code_freeze_unchanged']=all(pilot.sha(ROOT/p)==h for p,h in prereg['code_sha256'].items())
    save(OUT/'results.json',report)
    batch.refresh()
    print('END: '+str(report['completed_scenarios'])+' complete; '+str(report['failed_scenarios'])+' failed.',flush=True)

if __name__=='__main__': main()
