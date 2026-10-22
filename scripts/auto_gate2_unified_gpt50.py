#!/usr/bin/env python3
"""Run Gate2 after this GPT50 batch, retaining every required human judgment."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import continue_unified_gpt50_corrected as generation
from scripts import prepare_batch_gate2 as gate
from scripts import run_environment_interventions as interventions
from scripts import run_backbone_sensitivity as backbone
from scripts import run_unified_three_pilot as pilot
from scripts.validate_state_context_samples import load,save
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory
from rollout.configuration import load_rollout_config
from pipeline.localization import EnglishOutputProvider

SOURCE=generation.OUT
DEST=SOURCE/'gate2_followup'
JOB=SOURCE/'automatic_gate2_job.json'


def turn_id(value):
    return str(value).lstrip('t')


def project_history(snapshot):
    """A history-removal experiment must also remove copies in evidence and ledger."""
    result=deepcopy(snapshot)
    visible={turn_id(item.get('turn_id')) for item in result.get('history',[])}
    removed={turn_id(item.get('turn_id')) for item in result.get('turns',[])}-visible
    def clean(value):
        if isinstance(value,list):
            return [clean(item) for item in value if not isinstance(item,dict) or turn_id(item.get('turn_id')) not in removed]
        if isinstance(value,dict):
            if turn_id(value.get('turn_id')) in removed:
                return None
            return {key:clean(item) for key,item in value.items()}
        return value
    result['turns']=clean(result.get('turns',[]))
    result['interaction_ledger']=clean(result.get('interaction_ledger',{}))
    # The held numerical state/dynamics are the controlled condition in E3.
    return result


def interpret(environment,action):
    frame=environment._begin_turn(action)
    result=environment._run_state_update(frame)
    transition=result['transition']
    return {'appraisal':transition['appraisal'],'evidence_turn_ids':transition['evidence_turn_ids'],
            'calibration':transition.get('calibration',{}),'numeric_state_delta':result['state_numeric'],
            'numeric_dynamics_delta':result['dynamics_numeric'],
            'appraisal_context':result['appraisal_context'],
            'state_appraisal_call':transition.get('state_appraisal_call',{}),
            'interaction_appraisal_call':transition.get('interaction_appraisal_call',{})}


class UnifiedReplay:
    def __init__(self,plans,output):
        self.plans={p['case']['scenario_id']:p for p in plans}
        self.output=Path(output);self.counter=0

    def factory(self,scenario,*args,backbone_spec=None,**kwargs):
        env=deepcopy(self.plans[scenario['scenario_id']]['environment'])
        if backbone_spec is not None:
            provider=deepcopy(backbone_spec['provider']);provider['max_tokens']=6000
            env['state_appraisal_provider']=deepcopy(provider)
            env['interaction_appraisal_provider']=deepcopy(provider)
            for key in ('state_appraisal_sampling','interaction_appraisal_sampling'):
                env[key].update(backbone_spec.get('sampling',{}))
        # Do not discard independent appraisal, actor binding, trust rules or context.
        wrapped=UnifiedEnvironmentFactory(build_environment_factory(scenario,env))
        def create():
            self.counter+=1
            directory=self.output/'calls'/f"{self.counter:05d}_{scenario['scenario_id']}"
            environment=wrapped()
            state=environment.state_updater.state_appraiser
            state.provider.provider=pilot.RoleLogProvider(state.provider.provider,directory/'state',None)
            interaction=environment.state_updater.interaction_appraiser
            interaction.provider=pilot.RoleLogProvider(interaction.provider,directory/'interaction',None)
            if (SOURCE/'language_migration/amendment.json').exists():
                state.provider.provider.provider=EnglishOutputProvider(state.provider.provider.provider)
                interaction.provider.provider=EnglishOutputProvider(interaction.provider.provider)
            environment.state_updater.provider=state.provider
            save(directory/'runtime.json',{'scenario_id':scenario['scenario_id'],
                 'unified_profile':'unified_current_trust_schema_v1','backbone_model':env['state_appraisal_provider']['model'],
                 'response_calls':0,'factory_provenance':wrapped.provenance})
            return environment
        return create

    def replay(self,factory,snapshot,action):
        environment=factory();environment.restore(project_history(snapshot))
        return interpret(environment,action)

    def backbone(self,scenario,spec,checkpoint,**kwargs):
        return self.replay(self.factory(scenario,backbone_spec=spec),
                           checkpoint['environment_snapshot_before'],checkpoint['policy_action'])


def materialize(plans):
    coverage=[]
    for index,plan in enumerate(plans):
        case=plan['case'];name=f"{index:02d}_{case['scenario_id']}_gpt"
        directory=SOURCE/name
        path=next((directory/filename for filename in ('trajectory.json','partial_trajectory.json','checkpoint.json') if (directory/filename).exists()),None)
        result=load(directory/'result.json') if (directory/'result.json').exists() else {}
        number=case['scenario_id'].rsplit('_',1)[-1]
        save(DEST/'scenarios'/f'scenario_{number}'/f'scenario_{number}.json',plan['scenario'])
        row={'scenario_id':case['scenario_id'],'generation_status':result.get('status','not_generated'),
             'included':False,'source_path':str(path) if path else None}
        if path:
            trajectory=load(path)
            if trajectory.get('turns'):
                trajectory['gate2_audit_input']={'source_status':'completed_unreviewed' if path.name=='trajectory.json' else 'generation_error',
                    'source_path':str(path),'source_sha256':pilot.sha(path),'retained_without_deletion':True}
                save(DEST/'rollouts'/f'scenario_{number}'/'trajectory.json',trajectory)
                row.update(included=True,turns=len(trajectory['turns']),trajectory_id=trajectory['trajectory_id'])
        coverage.append(row)
    save(DEST/'input_coverage.json',{'scheduled_scenarios':50,'included_count':sum(x['included'] for x in coverage),
                                  'records':coverage,'missing_scenarios':[x['scenario_id'] for x in coverage if not x['included']]})
    config=load_rollout_config(ROOT/'configs/gpt50_experiment/rollout.state_observed_evidence_v6_candidate.json')
    config.pop('model_routes',None)
    config['environment']=deepcopy(plans[0]['environment'])
    # This is one logical policy per scenario, not fifty samples of one scenario.
    # Replay resolves scenario-specific environments through UnifiedReplay.plans.
    config['policies']=[deepcopy(plans[0]['policy'])]
    save(DEST/'rollout.runtime.json',config)
    return coverage


def execute(plans):
    coverage=materialize(plans)
    count=sum(x['included'] for x in coverage)
    if not count:return {'status':'blocked_no_retained_turns','included_scenarios':0,'human_review_status':'pending'}
    args=['--batch-root',str(DEST),'--scenario-root',str(DEST/'scenarios'),
          '--rollout-root',str(DEST/'rollouts'),'--rollout-config',str(DEST/'rollout.runtime.json'),
          '--all-scenarios','--allow-pending-video']
    # Freeze human packets before any machine experiment. Existing signed files are protected by the helper.
    gate.main(args+['--prepare-only'])
    if count<10:
        return {'status':'blocked_insufficient_trajectories','included_scenarios':count,
                'human_packets_prepared':True,'human_review_status':'pending'}
    runtime=UnifiedReplay(plans,DEST/'gate2')
    def run(command):
        module=interventions if Path(command[1]).name=='run_environment_interventions.py' else backbone
        try:
            with patch.object(sys,'argv',command[1:]):module.main()
            return 0
        except SystemExit as exc:return int(exc.code or 0)
    with patch.object(gate,'run',run),patch.object(interventions,'ModelEnvironmentFactory',runtime.factory), \
         patch.object(interventions,'_replay',runtime.replay),patch.object(backbone,'replay_transition',runtime.backbone):
        try:gate.main(args);returncode=0
        except SystemExit as exc:returncode=int(exc.code or 0)
    path=DEST/'gate2/manifest.json';manifest=load(path)
    # Replace legacy combined-appraisal assumptions with the actual tested candidate.
    manifest['state_transition_repair']={'status':'current_unified_candidate_automatic_audit',
        'pre_fix_trajectory_evidence_only':False,'factory_adapter':'UnifiedEnvironmentFactory',
        'state_prompt':'environment_state_appraisal_v6_observed_evidence',
        'state_calibration_profile':plans[0]['environment']['state_calibration_profile'],
        'trust_policy_sha256':pilot.sha(ROOT/'configs/state_trust_current_evidence_v1.json'),
        'human_review_status':'pending'}
    manifest['batch_input_coverage']=load(DEST/'input_coverage.json')
    manifest['human_review_required']=True
    if (SOURCE/'language_migration/amendment.json').exists():
        manifest['output_language']='en'
        manifest['language_amendment']=str(SOURCE/'language_migration/amendment.json')
    save(path,manifest)
    return {'status':'automatic_finished','returncode':returncode,'included_scenarios':count,
            'machine_evidence_ready':manifest['machine_evidence_ready'],
            'execution_status':manifest['execution_status'],'human_review_status':'pending',
            'manifest':str(path),'missing_scenarios':[x['scenario_id'] for x in coverage if not x['included']]}


def main():
    global SOURCE,DEST,JOB
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true')
    parser.add_argument('--source-root',type=Path,default=SOURCE)
    args=parser.parse_args()
    SOURCE=args.source_root.resolve();DEST=SOURCE/'gate2_followup';JOB=SOURCE/'automatic_gate2_job.json'
    plans,_=generation.prepare()
    registered=load(SOURCE/'preregistration.json')
    if registered.get('minimum_natural_turns')!=10 or len(registered.get('plans',[]))!=50:
        raise ValueError('Gate2 source must be the corrected fifty-scenario candidate')
    job={'status':'waiting_for_rollouts','source':str(SOURCE),'output':str(DEST),
         'automatic_experiments':['E3 history','E4 paraphrase','E5 local counterfactual','E6 backbone','E7 persona'],
         'human_pending':['E1 state directions','E2 trajectory plausibility','E4 equivalence','E5 causal interpretation','E7 persona interpretation','E9 timescale validity'],
         'E8':'awaiting_video_api','human_review_status':'pending','scheduled_scenarios':50,
         'script_sha256':pilot.sha(__file__),'pid':os.getpid()}
    if JOB.exists() and load(JOB).get('status') not in ('waiting_for_rollouts',):
        raise ValueError('Gate2 job already executed; do not overwrite reviews or rerun experiments')
    save(JOB,job)
    if not args.watch:print('Gate2 follow-up configured; launch --watch to await generation.');return
    while True:
        result=load(SOURCE/'results.json')
        if result['status'] in ('completed','stopped_verification_failed'):break
        if result['status'].startswith('stopped'):
            save(JOB,{**job,'status':'blocked_generation_stopped'});return
        time.sleep(30)
    save(JOB,{**job,'status':'running_gate2'})
    DEST.mkdir(parents=True,exist_ok=True)
    try:
        import contextlib
        with (DEST/'gate2.log').open('a') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            outcome=execute(plans)
        save(JOB,{**job,**outcome})
    except Exception as exc:
        save(JOB,{**job,'status':'gate2_error','error_type':type(exc).__name__,'error':str(exc)});raise
    print(json.dumps(outcome,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
