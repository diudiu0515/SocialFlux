#!/usr/bin/env python3
"""One user-authorized exploration attempt per GPT50 scenario, preserving failures."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_unified_three_pilot as pilot
from scripts.prepare_unified_gpt50 import prepare, OUT
from pipeline.runtime import appraisal_route_config as route_config
from scripts.validate_state_context_samples import load, save
from rollout.configuration import load_rollout_config
from pipeline.runtime import build_environment_factory
from environment.unified_appraisal import UnifiedEnvironmentFactory
from environment.observation import build_initial_policy_observation
from providers.factory import public_provider_config

AUTHORIZATION='那就扩大吧，咱们gpt不是本来就是50个场景吗，'
CONFIG=ROOT/'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json'
WORKERS=3


def plans():
    manifest=prepare()
    config=load_rollout_config(CONFIG)
    selected=[]
    for index,case in enumerate(manifest['cases']):
        candidate=ROOT/case['candidate']
        if pilot.sha(candidate)!=case['candidate_sha256']:
            raise ValueError('Reviewed candidate changed')
        scenario=load(candidate)
        env=deepcopy(config['environment'])
        env['minimum_natural_turns']=1
        env['response_opportunity_guidance']=False
        env['state_appraisal_provider']=route_config(env,0 if index%2==0 else 4)
        env['interaction_appraisal_provider']=deepcopy(env['state_appraisal_provider'])
        env['response_provider']['max_candidates_per_request']=1
        env['response_provider']['max_tokens']=6000
        env['response_sampling']['max_tokens']=6000
        policy=deepcopy(config['policies'][0])
        policy.update(policy_id='gpt_unified_v1_gpt50_'+case['scenario_id'], runs=1, minimum_natural_turns=1)
        if policy['provider']['provider']=='failover':
            policy['provider']['max_candidates_per_request']=1
        # Construct both adapters before any network call; schema/config problems
        # must fail during preparation, rather than after a paid policy request.
        UnifiedEnvironmentFactory(build_environment_factory(scenario,env))()
        selected.append({'case':case,'scenario':scenario,'environment':env,'policy':policy,
                         'observation':build_initial_policy_observation(scenario)})
    return selected


def preregister(selected):
    fixed=load(pilot.FIXED/'preregistration.json')['code_sha256']
    for path,expected in fixed.items():
        if pilot.sha(ROOT/path)!=expected:
            raise ValueError('State candidate changed since fixed validation: '+path)
    paths=[Path('scripts/run_unified_gpt50.py'),Path('scripts/prepare_unified_gpt50.py'),
           Path('scripts/run_unified_three_pilot.py'),Path('scripts/run_role_visible_shadow_pilot.py'),
           Path('scripts/validate_state_context_samples.py'),Path('scripts/resume_state_context_validation.py'),
           Path('scripts/export_shadow_pilot_review.py'),CONFIG.relative_to(ROOT)]
    for directory in ('environment','policies','providers','rollout','evaluation','pipeline','schemas'):
        paths.extend(p.relative_to(ROOT) for p in (ROOT/directory).rglob('*.py'))
    paths.extend(p.relative_to(ROOT) for p in (ROOT/'prompts').iterdir() if p.is_file())
    paths.extend(Path(p['case']['candidate']) for p in selected)
    paths.extend([OUT.relative_to(ROOT)/'manifest.json',Path('configs/state_trust_current_evidence_v1.json'),
                  Path('configs/gpt50_experiment/model_routes.hybrid.v3_2.json')])
    public=[{'case':p['case'],'environment':{k:public_provider_config(v) if k.endswith('provider') else v for k,v in p['environment'].items()},
             'policy':{**p['policy'],'provider':public_provider_config(p['policy']['provider'])},
             'initial_observation':p['observation']} for p in selected]
    prereg={'status':'prepared_not_started','mode':'explicit_user_authorized_gpt50_exploration',
            'user_authorization':AUTHORIZATION,'plans':public,'count':50,'workers':WORKERS,
            'code_sha256':{**fixed,**{str(p):pilot.sha(ROOT/p) for p in paths}},
            'first_pass_only':True,'semantic_resampling':False,'maximum_turns':20,
            'natural_stop_minimum':1,'target_turns':[10,20],'pad_short_trajectories':False,
            'response_max_tokens':6000,'original_fixed_gate_passed':False,
            'known_fixed_label_disputes_retained':True,'quality_review_status':'pending',
            'formal_human_annotation_status':'not_started','formal_admission':False,
            'automatic_scale_to_claude150':False}
    path=OUT/'preregistration.json'
    if path.exists():
        if load(path)!=prereg: raise ValueError('Prepared run changed')
    else: save(path,prereg)
    return prereg


def refresh():
    pilot.exporter.BASE=OUT
    # Export once per finished attempt; existing exporter prints all fifty rows.
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        pilot.exporter.main()
    path=OUT/'review_index.txt'
    path.write_text(path.read_text().replace('六条审核用轨迹','GPT50 五十条审核用轨迹'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    selected=plans()
    prereg=preregister(selected)
    if not args.run:
        print('GPT50 prepared: 50 valid role-visible scenarios; factories constructed; no API calls.',flush=True)
        return
    if (OUT/'results.json').exists():
        raise FileExistsError('Do not overwrite or automatically repeat previous batch attempts')
    pilot.OUT=OUT
    report={'status':'running','mode':prereg['mode'],'user_authorization':AUTHORIZATION,
            'scheduled_scenarios':50,'workers':WORKERS,'rows':{},'formal_admission':False,
            'quality_review_status':'pending','formal_human_annotation_status':'not_started'}
    save(OUT/'results.json',report)
    print('START GPT50: 50 scenarios, three concurrent attempts, max 20 turns, no padding.',flush=True)
    refresh()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(pilot.run_one,i,p):i for i,p in enumerate(selected)}
        for future in as_completed(futures):
            index=futures[future]
            try: row=future.result()
            except Exception as exc:
                row={'scenario_id':selected[index]['case']['scenario_id'],'policy':'gpt',
                     'status':'runner_failure','error_type':type(exc).__name__,'error':str(exc),'formal_admission':False}
                save(OUT/f"{index:02d}_{row['scenario_id']}_gpt"/'result.json',row)
            report['rows'][str(index)]=row
            save(OUT/'results.json',report)
            try: refresh()
            except Exception as exc:
                print('EXPORT ERROR (raw evidence retained): '+repr(exc),flush=True)
    report['status']='completed'
    report['completed_scenarios']=sum(r['status']=='completed' for r in report['rows'].values())
    report['failed_scenarios']=50-report['completed_scenarios']
    report['code_freeze_unchanged']=all(pilot.sha(ROOT/p)==h for p,h in prereg['code_sha256'].items())
    save(OUT/'results.json',report)
    refresh()
    print('END GPT50: '+str(report['completed_scenarios'])+' complete; '+str(report['failed_scenarios'])+' failed; review pending.',flush=True)

if __name__=='__main__': main()
