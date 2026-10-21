#!/usr/bin/env python3
"""Six first-pass, review-only trajectories. Never grant formal admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from environment.observation import build_initial_policy_observation
from environment.delta_mapper import flatten_state
from environment.policy_context import policy_background
from evaluation.rollout_gate import audit_rollout
from pipeline.runtime import build_environment_factory, build_policy
from providers.factory import public_provider_config
from rollout.configuration import load_rollout_config
from rollout.runner import RolloutRunner
from schemas.validate import validate_scenario
from scripts.validate_state_context_samples import save, load, LoggedProvider, BASE
from pipeline.runtime import appraisal_route_config as route_config

PREP=BASE/'observed_evidence_v6_pilot_preparation'
OUT=BASE/'observed_evidence_v6_shadow_six'
CONFIG=ROOT/'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json'

class RoleLogProvider(LoggedProvider):
    def complete(self,messages,**generation):
        if not self.requests:
            self.expected={'messages':deepcopy(messages),'generation':deepcopy(generation)}
        return super().complete(messages,**generation)

def assemble():
    manifest=load(PREP/'manifest.json')
    base=load_rollout_config(CONFIG)
    claude=load_rollout_config(ROOT/'configs/claude150_v1/rollout.state_v3.json')
    plans=[]
    for index,case in enumerate(manifest['cases']):
        assert hashlib.sha256((ROOT/case['candidate']).read_bytes()).hexdigest()==case['candidate_sha256'], 'candidate changed after visibility review'
        scenario=load(ROOT/case['candidate']);validate_scenario(scenario)
        if not policy_background(scenario):
            raise ValueError('Missing reviewed policy background')
        env=deepcopy(base['environment']);env['minimum_natural_turns']=1
        env['response_opportunity_guidance']=False
        env['state_appraisal_provider']=route_config(env,0 if index%2==0 else 4)
        env['interaction_appraisal_provider']=deepcopy(env['state_appraisal_provider'])
        env['response_provider']['max_candidates_per_request']=1
        spec=deepcopy((base if case['policy']=='gpt' else claude)['policies'][0])
        spec['minimum_natural_turns']=1;spec['runs']=1
        spec['policy_id']=f"{case['policy']}_v6_shadow_{case['scenario_id']}"
        if spec['provider']['provider']=='failover':
            spec['provider']['max_candidates_per_request']=1
        observation=build_initial_policy_observation(scenario)
        assert observation['background']==policy_background(scenario)
        # Building the factory is a configuration-only check; no API calls.
        build_environment_factory(scenario,env)
        plans.append({'case':case,'scenario':scenario,'environment':env,'policy':spec,'observation':observation})
    return plans

def review_text(plan,trajectory):
    lines=[plan['case']['scenario_id']+' / '+plan['case']['policy'],'人工待审核；不进入正式数据。',
           'policy 可见背景：'+plan['observation']['background'],'']
    for turn in trajectory.get('turns',[]):
        lines.extend([str(turn['turn_id']), '被测方：'+turn.get('policy_action',{}).get('text',''),
                      '环境方：'+str(turn.get('environment_response',''))])
        delta=flatten_state(turn.get('numeric_state_delta',{}))
        for judgment in turn.get('state_judgments',[]):
            variable=judgment['variable']
            if delta.get(variable) or variable.startswith('relationship.'):
                lines.append(f"{variable}: delta={delta.get(variable,0)}; {judgment['judgment']}; {judgment.get('evidence_span','')}; {judgment.get('rationale','')}")
        lines.append('')
    lines.extend(['结束：'+str(trajectory.get('ending')), '短轨迹不补写。', '',
                  '环境角色实际可见背景：',plan['scenario']['environment_background'],
                  '初始共同背景：',plan['scenario']['shared_background'],
                  '原始作者背景（只供审核，可能含未发生结果，不是模型实际背景）：',plan['scenario']['background'],
                  '环境目标：'+plan['scenario']['environment_agent']['explicit_goal'],
                  '环境私有意图：'+plan['scenario']['environment_agent']['hidden_intention']])
    return '\n'.join(lines)+'\n'

def run_one(index,plan):
    directory=OUT/f"{index:02d}_{plan['case']['scenario_id']}_{plan['case']['policy']}"
    factory=build_environment_factory(plan['scenario'],plan['environment'])
    def logged_factory():
        env=factory()
        for role,owner in [('state_appraisal',env.state_updater.state_appraiser),
                           ('interaction_appraisal',env.state_updater.interaction_appraiser),
                           ('response',env.response_generator)]:
            owner.provider=RoleLogProvider(owner.provider,directory/'calls'/role,None)
        env.state_updater.provider=env.state_updater.state_appraiser.provider
        return env
    policy=build_policy(plan['policy'])
    policy.provider=RoleLogProvider(policy.provider,directory/'calls'/'policy',None)
    def checkpoint(trajectory):
        trajectory['review_only']=True;trajectory['human_review_status']='pending'
        save(directory/'checkpoint.json',trajectory)
        (directory/'review.txt').write_text(review_text(plan,trajectory))
    result={'scenario_id':plan['case']['scenario_id'],'policy':plan['case']['policy'],
            'human_review_status':'pending','formal_admission':False}
    try:
        trajectory=RolloutRunner(logged_factory,checkpoint_writer=checkpoint).run(policy,max_turns=20)
        save(directory/'trajectory.json',trajectory)
        save(directory/'gate.json',audit_rollout(trajectory))
        result.update(status='completed',turns=len(trajectory['turns']),ending=trajectory.get('ending'),
                      review=str(directory/'review.txt'))
    except Exception as exc:
        result.update(status='call_or_validation_failure',error_type=type(exc).__name__,error=str(exc))
        partial=getattr(exc,'partial_trajectory',None)
        if partial is not None:
            save(directory/'partial_trajectory.json',partial)
    save(directory/'result.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--allow-known-semantic-errors',action='store_true',help='Requires an explicit decision to run review-only despite the failed fixed-set gate')
    args=parser.parse_args()
    plans=assemble()
    public=[{'case':p['case'],'environment':{k:(public_provider_config(v) if k.endswith('provider') else v) for k,v in p['environment'].items()},
             'policy':{**p['policy'],'provider':public_provider_config(p['policy']['provider'])},'initial_observation':p['observation']} for p in plans]
    paths=['environment/policy_context.py','environment/observation.py','environment/public_situation.py',
           'environment/independent_appraisal.py','environment/calibration.py','environment/env.py','environment/state_updater.py',
           'environment/state_transition_contract.py','environment/state_ontology.py','environment/response_generator.py',
           'environment/factory.py','policies/model_policy.py','pipeline/runtime.py',
           'rollout/runner.py','scripts/run_role_visible_shadow_pilot.py','prompts/manifest.json',
           'schemas/validate.py','schemas/scenario.schema.json',str(CONFIG.relative_to(ROOT))]
    paths += [plan['case']['candidate'] for plan in plans]
    paths += [str((PREP/'manifest.json').relative_to(ROOT))]
    freeze={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    prereg={'status':'prepared_not_started','plans':public,'code_sha256':freeze,'workers':2,'first_pass_only':True,
            'target_turns':[10,20],'natural_stop_minimum':1,'maximum_turns':20,'pad_short_trajectories':False,
            'human_review_status':'pending','full_scale_authorized':False}
    target=OUT/'preregistration.json'
    if target.exists():
        assert load(target)==prereg,'prepared run configuration changed'
    else:
        save(target,prereg)
    print('Prepared six first-pass review-only slots; zero model calls during preparation',flush=True)
    if not args.run:
        return
    gate=load(BASE/'observed_evidence_v6_fixed/results.json')
    if not gate.get('gate_passed') and not args.allow_known_semantic_errors:
        raise ValueError('Fixed-set gate failed; an explicit review-only decision is required')
    if (OUT/'results.json').exists():
        raise FileExistsError('No automatic reruns or overwriting earlier attempts')
    report={'status':'running','rows':{},'known_semantic_errors_acknowledged':args.allow_known_semantic_errors,
            'human_review_status':'pending','full_scale_authorized':False}
    save(OUT/'results.json',report)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(run_one,i,p):i for i,p in enumerate(plans)}
        for future in as_completed(futures):
            report['rows'][str(futures[future])]=future.result();save(OUT/'results.json',report)
    report['status']='completed';save(OUT/'results.json',report)

if __name__=='__main__':
    main()
