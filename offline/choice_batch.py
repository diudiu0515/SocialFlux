"""Resume T1/T3 authoring for the fixed GPT50 scenario cohort.

Original failed/rejected sources stay intact. New source prefixes are separate
development artifacts, never replacements for the frozen rollout batch.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import fcntl
import os
from http.client import IncompleteRead
from time import sleep

from environment.delta_mapper import flatten_state
from offline.choice_builder import load, save, sha, source_input, author_call, write_bundle
from offline.choice_pipeline import author_provider, question_group, runtime
from rollout.counterfactual import branch_counterfactuals
from rollout.runner import RolloutRunner
from offline.factual_reference import factual_reference, assert_same_policy


def run_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def source_for(config, number):
    directory=Path(config['output'])/'sources'/f'GPT50_{number:03d}'
    directory.mkdir(parents=True,exist_ok=True)
    config={**config,'call_log_dir':str(directory/'calls')}
    scenario_path=Path(config['scenario_root'])/f'gpt_{number:03d}.json'
    scenario=load(scenario_path)
    source_dirs=list(Path(config['source_root']).glob(f'*GPT50_{number:03d}_gpt'))
    candidates=[d/name for d in source_dirs for name in ('trajectory.json','partial_trajectory.json')]
    path=next((p for p in candidates if p.exists() and len(load(p).get('turns',[]))>=3),None)
    review_path=Path(config['source_root'])/'gate3_followup/source_review.json'
    review=next((x for x in load(review_path)['candidates'] if x['scenario_id']==f'GPT50_{number:03d}'),{})
    origin='existing_complete_rollout' if path and path.name=='trajectory.json' else 'existing_partial_rollout'
    if path is None:
        origin='new_offline_source_prefix_original_failure_preserved'
        path=directory/'source_prefix.json'
        if not path.exists():
            attempt=directory/'source_attempts'/run_id()
            factory,policy_factory=runtime(config,scenario,number-1)
            policy=policy_factory()
            policy.policy_id += f'_offline_prefix_{number:03d}'
            scenario_digest=sha(scenario_path)
            runner=RolloutRunner(factory,checkpoint_writer=lambda t:save(attempt/'checkpoint.json',
                {**t,'offline_source_scenario_sha256':scenario_digest}))
            checkpoints=[(p,load(p)) for p in (directory/'source_attempts').glob('*/checkpoint.json')]
            checkpoints=[(p,t) for p,t in checkpoints if t.get('resume_snapshot') and t.get('turns')
                         and t.get('offline_source_scenario_sha256')==scenario_digest]
            previous=max(checkpoints,key=lambda pair:(len(pair[1]['turns']),pair[0].stat().st_mtime),default=None)
            try:
                trajectory=runner.run(policy,max_turns=3,**({'resume_from':previous[1]} if previous else {}))
            except Exception as exc:
                save(attempt/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
                raise
            if len(trajectory['turns'])<3:
                raise ValueError('new offline source prefix has fewer than three observed turns')
            trajectory['offline_source_status']='three_turn_development_prefix_not_formal_rollout'
            trajectory['original_failed_sources']=[str(p) for p in candidates if p.exists()]
            if previous:
                trajectory['source_resume_checkpoint']={'path':str(previous[0]),'sha256':sha(previous[0])}
            save(path,trajectory)
    trajectory=load(path)
    if origin.startswith('existing') and review.get('latest_attempt',{}).get('artifact_sha256') != sha(path):
        raise ValueError('source review hash does not match existing trajectory')
    source={'scenario_id':trajectory['scenario_id'],'trajectory_id':trajectory['trajectory_id'],
            'trajectory_path':str(path),'trajectory_sha256':sha(path),
            'scenario_path':str(scenario_path),'scenario_sha256':sha(scenario_path),
            'gate3_model_review':review.get('model_semantic_review'),
            'origin':origin,'source_complete':origin=='existing_complete_rollout',
            'source_review_status':review.get('model_semantic_review',{}).get('decision') if origin.startswith('existing') else 'not_reviewed',
            'source_review_record':{'path':str(review_path),'sha256':sha(review_path)},
            'original_failed_sources_preserved':True}
    saved=directory/'source.json'
    if saved.exists() and load(saved)!=source:
        raise ValueError('frozen source binding changed; do not overwrite prior question evidence')
    save(saved,source)
    return config,directory,scenario,trajectory,source


def reusable_source(config,source):
    old=Path(config['reuse_bank'])/'sources'/source['scenario_id']
    if not (old/'source.json').exists():return None
    previous=load(old/'source.json')
    if all(previous[k]==source[k] for k in ('trajectory_sha256','scenario_sha256','trajectory_id')):
        return old
    return None


def reuse_author(old,directory,task):
    if old is None or any((directory/(task+suffix)).exists() for suffix in ('.curated.json','.authored.json')):
        return
    for suffix in ('.curated.json','.authored.json'):
        path=old/(task+suffix)
        if path.exists():
            shutil.copyfile(path,directory/path.name)
            save(directory/(task+'.reused_from.json'),{'path':str(path),'sha256':sha(path)})
            return


def candidates_for(config,directory,source,public,old):
    path=directory/'t3_actions.json'
    existing=load(path) if path.exists() else None
    reuse_factual=config.get('reuse_factual_continuation') and not (
        (directory/'T3.items.json').exists() or (directory/'t3_branches.json').exists()
        or (old and (old/'t3_branches.json').exists()))
    factual=factual_reference(load(source['trajectory_path']),config['delayed_horizon'],source) if reuse_factual else None
    if existing and (not factual or existing.get('construction_strategy')=='factual_plus_counterfactual'):
        return existing
    if old and (old/'interventions.json').exists() and not factual:
        previous=load(old/'interventions.json')
        plan={k:previous[k] for k in ('candidate_actions','edit_rationale')}
        plan['reused_from']={'path':str(old/'interventions.json'),'sha256':sha(old/'interventions.json')}
    else:
        def validate(plan):
            actions=plan.get('candidate_actions',[])
            if len(actions)!=2 or [a.get('action_id') for a in actions]!=['action_1','action_2']:
                raise ValueError('two named candidate actions are required')
            if any(not isinstance(a.get('text'),str) or not a['text'].strip() for a in actions) or actions[0]['text']==actions[1]['text']:
                raise ValueError('candidate actions must be distinct direct dialogue')
            if factual and actions[0]['text']!=factual['candidate_action']['text']:
                raise ValueError('action_1 must preserve the provided factual action verbatim')
            return plan
        payload={
            'request':'只构造T3行动：在给定t2历史之后，写两种都合理但有真实取舍的直接台词。发言者必须是public_input.role；public_input.target_character是听者。核对职务权限：不能代替听者、第三方作决定；权限属于对方时须表达为请求或建议。不要一好一坏；目标、资源或权力约束应影响取舍；不能编造已发生的新事实、第三方决定或已完成的履约。每条180汉字以内。不要构造T2或任何历史改写。',
            'public_input':public,'output_schema':{'candidate_actions':[{'action_id':'action_1','text':'受评人物直接台词'},{'action_id':'action_2','text':'另一合理行动'}],'edit_rationale':'两行动的目标、成本与取舍'}}
        if factual:
            payload['fixed_action_1']=factual['candidate_action']['text']
            payload['request']+=' action_1必须逐字保留fixed_action_1（不受180字限制）；action_2使用与action_1相同的语言，只改变行动选择而不改变表达语言。只新写action_2，使其与原行动在目标、资源、边界或短长期后果上有真实取舍。不要只换措辞，不要把原行动写成明显错误的选择。'
        plan=author_call(author_provider(config),payload,validate)
    if factual:
        plan['construction_strategy']='factual_plus_counterfactual'
        plan['factual_reference']={'source_sha256':source['trajectory_sha256'],'start':'t3','environment_responses':config['delayed_horizon']}
        if existing:
            archive=directory/'t3_attempts'/run_id();archive.mkdir(parents=True)
            shutil.copyfile(path,archive/path.name)
            for name in ('branch_progress','T3.authored.json','T3.curated.json'):
                if (directory/name).exists():shutil.move(str(directory/name),str(archive/name))
            plan['superseded_construction']=str(archive)
    save(path,plan)
    return plan


def validate_branches(branches,trajectory,actions,horizon):
    snapshot=trajectory['turns'][2]['environment_snapshot_before']
    expected=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if len(branches)!=len(actions):raise ValueError('branch count differs from candidate action count')
    for branch,action in zip(branches,actions):
        if (branch['snapshot_sha256']!=expected or branch['candidate_action']['text']!=action['text']
                or branch['delayed_horizon']!=horizon
                or branch['external_event_plan_hash']!=snapshot.get('event_plan',{}).get('plan_hash')):
            raise ValueError('branch source/action/horizon binding mismatch')
        if not branch['window_complete'] or branch['actual_turns_observed']!=horizon or len(branch['future_turns'])!=horizon:
            raise ValueError('delayed branch is incomplete')
    return branches


def branch_reference(config,directory,scenario,trajectory,actions,number,old):
    horizon=config['delayed_horizon']
    path=directory/'t3_branches.json'
    if not path.exists() and old and (old/'t3_branches.json').exists():
        candidate=old/'t3_branches.json'
        validate_branches(load(candidate),trajectory,actions,horizon)
        return candidate,load(candidate)
    if path.exists():return path,validate_branches(load(path),trajectory,actions,horizon)
    factory,policy_factory=runtime(config,scenario,number-1)
    progress=directory/'branch_progress'
    completed={}
    plan=load(directory/'t3_actions.json')
    if plan.get('construction_strategy')=='factual_plus_counterfactual':
        source=load(directory/'source.json')
        factual=factual_reference(trajectory,horizon,source)
        if factual is None:raise ValueError('factual continuation no longer eligible')
        assert_same_policy(factual,policy_factory())
        completed[0]=factual
    for p in (progress/'complete').glob('*.json'):
        completed[int(p.stem)]=load(p)
    prior={}
    for run in sorted((progress/'runs').glob('*')):
        groups={}
        for p in run.glob('*.json'):
            b,attempt,step=map(int,p.stem.split('_'))
            groups.setdefault((b,attempt),{})[step]=load(p)
        for (b,_),steps in groups.items():
            if sorted(steps)==list(range(1,max(steps)+1)):
                logs=[steps[i] for i in sorted(steps)]
                if len(logs)>len(prior.get(b,[])):prior[b]=logs
    run=progress/'runs'/run_id()
    # A resumed run writes only its replayed suffix. Copy the retained prefix
    # so another failure still leaves a contiguous, independently reusable log.
    for branch,logs in prior.items():
        if branch in completed:continue
        retained = logs if logs[-1].get('environment_snapshot_after') else logs[:-1]
        for step,log in enumerate(retained,1):
            save(run/f'{branch}_0_{step}.json',log)
    prior={b:logs for b,logs in prior.items() if b not in completed}
    print(source_name(number),f'T3 replay: {len(completed)} saved branches, {len(actions)-len(completed)} to run; five responses each',flush=True)
    def record_step(branch,attempt,step,log):
        save(run/f'{branch}_{attempt}_{step}.json',log)
        print(source_name(number),f'T3 action_{branch+1}: response {step}/{horizon} saved',flush=True)
    branches=branch_counterfactuals(factory,trajectory['turns'][2],
        [{'text':a['text']} for a in actions],policy_factory,horizon,
        branch_workers=config.get('branch_workers',2),resume_logs=prior,completed_branches=completed,
        branch_callback=lambda b,row:save(progress/'complete'/f'{b}.json',row),
        audit_callback=record_step)
    validate_branches(branches,trajectory,actions,horizon)
    save(path,branches)
    return path,branches


def source_name(number):
    return f'GPT50_{number:03d}'


def generate_with_recovery(config, number, tasks, *, replay, run, retries=0):
    """Retry provider failures only; never bypass source or content validation."""
    from providers.openai_compatible import OpenAICompatibleProvider
    from providers.anthropic import AnthropicProvider
    from providers.base import IncompleteModelOutputError
    directory = Path(config['output'])/'sources'/source_name(number)
    attempts = []
    for attempt in range(retries+1):
        try:
            row = generate_case(config, number, tasks, replay=replay)
            return {**row, 'recovered_failures': attempts}
        except Exception as exc:
            failure = {'scenario_id':source_name(number), 'attempt':attempt+1,
                       'type':type(exc).__name__, 'message':str(exc)[:1800],
                       'last_raw':getattr(exc,'last_raw',None),
                       'last_validation_error':str(getattr(exc,'last_error',''))}
            save(directory/'failures'/f'{run}_attempt_{attempt+1}.json',failure)
            transient = (OpenAICompatibleProvider._is_transient(exc)
                         or AnthropicProvider._is_transient(exc)
                         or isinstance(exc, (ConnectionError, IncompleteRead, IncompleteModelOutputError))
                         or (type(exc) is ValueError and str(exc)=='provider returned empty content')
                         or (type(exc) is RuntimeError and str(exc)=='all failover provider candidates are temporarily circuit-open'))
            if not transient or attempt == retries:
                raise
            attempts.append({k:v for k,v in failure.items() if not k.startswith('last_')})
            print(source_name(number),f'provider failed ({type(exc).__name__}); resume {attempt+1}/{retries}',flush=True)
            sleep(min(30*(attempt+1),120))


def generate_case(config,number,tasks,*,replay=True):
    config,directory,scenario,trajectory,source=source_for(config,number)
    public=source_input(trajectory,2)
    states={'initial_state':flatten_state(trajectory['initial_state']),
            'checkpoints':{f't{i+1}':flatten_state(t.get('state_after_public_events',t['state_after'])) for i,t in enumerate(trajectory['turns'][:2])}}
    old=reusable_source(config,source)
    for task in tasks:
        if task=='T1':
            reuse_author(old,directory,task)
            question_group(task,public,states,source,number-1,directory,config)
        elif task=='T3':
            plan=candidates_for(config,directory,source,public,old)
            t3_public={**deepcopy(public),'candidate_actions':plan['candidate_actions']}
            t3_source=deepcopy(source);t3_states=deepcopy(states)
            if replay:
                path,branches=branch_reference(config,directory,scenario,trajectory,plan['candidate_actions'],number,old)
                t3_source.update(replay_path=str(path),replay_sha256=sha(path))
                t3_states['branches']=[{k:deepcopy(b[k]) for k in ('candidate_action','state_before','state_after_immediate_action_response','state_after_delayed','actual_turns_observed')} for b in branches]
                t3_states['future_evidence']=[[{'action':t['policy_action']['text'],'response':t['environment_response']} for t in b['future_turns']] for b in branches]
            t3_source['action_construction']={'path':str(directory/'t3_actions.json'),'sha256':sha(directory/'t3_actions.json')}
            if plan.get('construction_strategy')!='factual_plus_counterfactual':
                reuse_author(old,directory,task)
            question_group(task,t3_public,t3_states,t3_source,number-1,directory,config,replay_status='validated' if replay else 'pending')
        else:raise ValueError('T2 is paused for this batch')
    return {'scenario_id':source['scenario_id'],'completed_tasks':list(tasks),'source_origin':source['origin'],'source_review_status':source['source_review_status']}


def export_batch(config):
    output=Path(config['output']);output.mkdir(parents=True,exist_ok=True)
    with (output/'.export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _export_batch(config)


def _export_batch(config):
    items=[];coverage=[]
    for n in config['scenario_numbers']:
        directory=Path(config['output'])/'sources'/source_name(n)
        row={'scenario_id':source_name(n),'tasks':{}}
        for task in config['tasks']:
            path=directory/(task+'.items.json')
            group=load(path) if path.exists() else []
            items.extend(group);row['tasks'][task]={'items':len(group),'complete':len(group)==4}
        if (directory/'source.json').exists():
            source=load(directory/'source.json');row.update(source_origin=source['origin'],source_review_status=source['source_review_status'])
        coverage.append(row)
    manifest=write_bundle(sorted(items,key=lambda i:i['instance_id']),config['output'])
    manifest.update(bank_id=config['bank_id'],requested_scenarios=len(config['scenario_numbers']),
                    expected_items=4*len(config['tasks'])*len(config['scenario_numbers']),paused_tasks=['T2'],scenario_coverage=coverage)
    manifest['complete']=len(items)==manifest['expected_items'] and manifest['replay_ready_count']==len(items)
    save(Path(config['output'])/'manifest.json',manifest)
    return items,manifest


def run_batch(config,args):
    if config.get('tasks')!=['T1','T3']:raise ValueError('GPT50 batch must explicitly pause T2')
    tasks=args.tasks or config['tasks']
    if not set(tasks)<=set(config['tasks']):raise ValueError('T2 is paused; choose T1 and/or T3')
    numbers=args.scenarios or config['scenario_numbers']
    if not set(numbers)<=set(config['scenario_numbers']):raise ValueError('scenario outside fixed cohort')
    output=Path(config['output']);output.mkdir(parents=True,exist_ok=True)
    freeze={'config':config,'scenario_ids':[source_name(n) for n in config['scenario_numbers']]}
    frozen=output/'batch_spec.json'
    if frozen.exists() and load(frozen)!=freeze:raise ValueError('batch specification changed; create a new output')
    save(frozen,freeze)
    overrides={key:getattr(args,key,None) for key in ('request_timeout','workers','transport_attempts','recovery_attempts')}
    overrides={key:value for key,value in overrides.items() if value is not None}
    if any(value<=0 for key,value in overrides.items() if key!='recovery_attempts') or overrides.get('recovery_attempts',0)<0:
        raise ValueError('transport timeout and worker count must be positive')
    config={**config,**overrides}
    if getattr(args,'reuse_factual_continuation',False):
        config['reuse_factual_continuation']=True
    failures=[];rows=[]
    status={'status':'running','pid':os.getpid(),'run_id':run_id(),'tasks':tasks,'requested_scenarios':numbers,'transport_overrides':overrides,'reuse_factual_continuation':config.get('reuse_factual_continuation',False),'rows':rows,'failures':failures,'formal_admission':False}
    def checkpoint():
        save(output/'run_status.json',status)
        save(output/('run_status_'+'-'.join(tasks)+'.json'),status)
        save(output/'runs'/(status['run_id']+'.json'),status)
    if not args.export_only:
        checkpoint()
        with ThreadPoolExecutor(max_workers=config['workers']) as pool:
            futures={pool.submit(generate_with_recovery,config,n,tasks,replay=not args.author_only,
                                 run=status['run_id'],retries=config.get('recovery_attempts',0)):n for n in numbers}
            for future in as_completed(futures):
                n=futures[future]
                try:rows.append(future.result())
                except Exception as exc:
                    row={'scenario_id':source_name(n),'type':type(exc).__name__,'message':str(exc)[:1800]}
                    failures.append(row)
                    save(output/'sources'/source_name(n)/'failures'/(status['run_id']+'.json'),{**row,'last_raw':getattr(exc,'last_raw',None),'last_validation_error':str(getattr(exc,'last_error',''))})
                    print(json.dumps(row,ensure_ascii=False),flush=True)
                checkpoint()
                export_batch(config)
    items,manifest=export_batch(config)
    if items:
        from offline.choice_audit import audit_bundle
        audit_bundle(items,output)
    if args.pair_media:
        from offline.choice_media import pair_assets
        manifest['pairing']=pair_assets(items,args.pair_media,output)
    status.update(status='completed' if manifest['complete'] else 'incomplete',item_count=len(items),expected=manifest['expected_items'])
    if args.export_only:
        save(output/'export_status.json',status)
    else:
        checkpoint()
    print(json.dumps({k:v for k,v in manifest.items() if k!='scenario_coverage'},ensure_ascii=False,indent=2))
    if failures:raise SystemExit(1)
