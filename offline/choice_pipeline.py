"""Author offline choice groups using existing sources and canonical replay.

Resumes only completed artifacts. Replayed futures remain in author-side files.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from offline.choice_builder import load, save, sha, source_input, author_call, assemble, write_bundle, freeze_authoring_source
from environment.delta_mapper import flatten_state
from environment.unified_appraisal import UnifiedEnvironmentFactory
from pipeline.runtime import build_environment_factory, build_policy
from rollout.configuration import load_rollout_config
from rollout.counterfactual import branch_counterfactuals
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from offline.provider_compat import OfflineSamplingProvider, OfflineRuntimeFactory
from scripts.resume_state_context_validation import route_config

QUESTION_SCHEMA = {
    'subtype': 'one permitted subtype', 'question': '中文问题，明确人物方向和时间',
    'target_spec': {'target_state_ids': ['canonical.path'], 'checkpoint': 't2',
                    'time_scope': '明确比较起止或预测窗口', 'comparison_horizon':'T3行动比较题明确immediate或delayed，其余省略', 'action_id':'T3单行动题的action_1或action_2，其他任务省略', 'risk_event': '风险题必须填写具体事件，其余为空'},
    'options': {'A': '选项', 'B': '选项', 'C': '选项'}, 'answer': 'A',
    'evidence_ids': ['t1', 't2'], 'rationale': '可见依据、排除竞争答案、边界',
    'option_errors': {'B': 'unsupported_inference', 'C': 'state_dimension_confusion'},
    'option_variable_map': {'A': {'canonical.path': 'increase'}, 'B': {'canonical.path': 'similar'}, 'C': {'canonical.path': 'decrease'}},
    'review_notes': '具体可审核问题', 'history_dependence': 'required',
    'nonverbal_history_relation': 'supports_history / masks_state / ambiguous_without_history / not_needed'}


def author_provider(config):
    route = ModelRoutes.load(config['model_routes']).provider_config('task_extraction')
    route.update(max_tokens=14000, timeout=config.get('request_timeout',600), max_transport_attempts=config.get('transport_attempts',1),retry_backoff_seconds=5)
    provider = OfflineSamplingProvider(build_provider(route))
    if config.get('call_log_dir'):
        from offline.provider_compat import OfflineLoggedProvider
        provider = OfflineLoggedProvider(provider, Path(config['call_log_dir'])/'author')
    return provider


def question_group(task, public, states, source, ordinal, output, config, *, replay_status='not_required'):
    path=output/(task+'.authored.json')
    curated=output/(task+'.curated.json')
    if curated.exists():
        path=curated
    instructions={
        'T1': '写4题：1 current_intensity、2 interval_change、1 joint_change。均限定已发生的t1→t2区间或t2当前强度。优先选择有公开证据的状态；四类state在整批题库覆盖，不要求每个场景都覆盖。组合两变量，不和强度混问。时间和变量需具体，只有1轮变化也可基本不变。',
        'T2': '写4题：2 history_comparison、1 expression_meaning、1 joint_comparison。所有题判断共同ending时环境角色的state。优先选择有公开依据的状态，四维在整个题库覆盖。至少1题问历史不同但某状态接近；解释题联系目标/资源/权力导致同一句话承担的功能，不把合作等于信任。共同ending的台词和可见表情全都相同。',
        'T3': '写4题：immediate_effect、delayed_effect、action_comparison、immediate_delayed各1。优先选择有公开依据的状态，四维在整个题库覆盖。即时是执行动作后的下一次环境回应；延迟为从候选动作开始的5轮环境回应（含即时一轮），比较t2基线至第5轮末。即时—延迟组合可以同一变量或两变量。比较题只问指定状态，不泛问最佳行动。未来模拟仅作标注交叉证据，公开材料不能支持的精确结果不可设答案。'
    }
    horizon=config.get('delayed_horizon',5)
    instructions['T3']=instructions['T3'].replace('5轮',f'{horizon}轮')
    payload={'request':instructions[task], 'output_schema':{'questions':[QUESTION_SCHEMA]},
             'public_input':public,'author_only_state_reference':states,
             'allowed_state_paths':list(states['initial_state']),
             'combination_pattern': ['同步变化或均基本不变','情绪缓和但关系/任务风险未修复','情绪紧张但仍愿合作','现实目标推动合作不等于信任','同步变化或均基本不变'][ordinal % 5]}
    if config.get('bank_id'):
        from environment.state_ontology import STATE_VARIABLE_ONTOLOGY
        payload['state_definitions'] = {p:STATE_VARIABLE_ONTOLOGY[p] for p in states['initial_state']}
        payload['coverage_priority'] = list(sorted(states['initial_state']))[ordinal % len(states['initial_state']):] or list(states['initial_state'])
        payload['request'] += ' 同组优先覆盖不同变量，优先选择公开证据充分的变量，不因覆盖要求虚构答案；主体单变量、组合恰好两项判断。'
        if task == 'T3':
            payload['request'] += (' 预测问的是在既有目标、约束与候选行动下最可能的变化方向，不要求未来事实已在输入中发生。'
                                  '承诺不等于已履约，但有明确机制且符合既往表现的行动计划可以改变结果的预期风险；'
                                  '不能仅因未来未发生就把所有延迟题设为证据不足。先选择可作有根据预测的变量；'
                                  '只有多种相反方向仍同样合理时才保留证据不足，不能用私有分支中的偶然结果排除合理选项。')
    def make_item(raw, index):
        identity = f"{config['bank_id']}-{source['scenario_id'].split('_')[-1]}-{task}-{index+1:02d}" if config.get('bank_id') else None
        return assemble(raw,task=task,source=source,public_input=public,ordinal=ordinal,index=index,
                        replay_status=replay_status,delayed_horizon=horizon,instance_id=identity)
    def validate(raw):
        if len(raw.get('questions',[])) != 4:
            raise ValueError('exactly four questions required')
        items=[make_item(x,i) for i,x in enumerate(raw['questions'])]
        if config.get('bank_id'):
            from collections import Counter
            expected = {'T1':{'current_intensity':1,'interval_change':2,'joint_change':1},
                        'T3':{'immediate_effect':1,'delayed_effect':1,'action_comparison':1,'immediate_delayed':1}}
            if task in expected and Counter(x['subtype'] for x in items) != expected[task]:
                raise ValueError('question group does not cover the requested subtypes')
        families={p.split('.')[0] for x in items for p in x['target_spec']['target_state_ids']}
        # Coverage is a bank-level requirement; a source need not supply every family.
        if not families <= {'emotion','behavioral_disposition','relationship','consequence_risk'}:
            raise ValueError('unknown state family')
        if not {p for x in items for p in x['target_spec']['target_state_ids']} <= set(states['initial_state']):
            raise ValueError('state path is not selected in source scenario')
        return raw
    if path.exists():
        raw=validate(load(path))
    else:
        raw=author_call(author_provider(config), payload,validate);save(path,raw)
    items=[make_item(x,i) for i,x in enumerate(raw['questions'])]
    freeze_authoring_source(items,path)
    save(output/(task+'.items.json'),items)
    print(source['scenario_id'],task,'4 questions ready',flush=True)
    return items


def runtime(config, scenario, index):
    cfg=load_rollout_config(config['rollout_config']);env=deepcopy(cfg['environment'])
    env['minimum_natural_turns']=10
    env['response_opportunity_guidance']=True
    env['state_appraisal_provider']=route_config(env,0 if index%2==0 else 4)
    env['interaction_appraisal_provider']=deepcopy(env['state_appraisal_provider'])
    # Retain the configured response failover: an empty upstream response must
    # be allowed to try the next existing route before discarding the turn.
    env['response_provider']['max_tokens']=6000
    env['response_sampling']['max_tokens']=6000
    policy=deepcopy(cfg['policies'][0]);policy.update(minimum_natural_turns=10)
    if config.get('request_timeout'):
        def transport(value):
            value.update(timeout=config['request_timeout'],max_transport_attempts=config.get('transport_attempts',1),retry_backoff_seconds=5)
            for child in value.get('candidates',[]): transport(child)
        for key in ('state_appraisal_provider','interaction_appraisal_provider','response_provider'):
            transport(env[key])
        transport(policy['provider'])
    def policy_factory():
        result=build_policy(policy)
        result.provider=OfflineSamplingProvider(result.provider)
        if config.get('call_log_dir'):
            from offline.provider_compat import OfflineLoggedProvider
            result.provider=OfflineLoggedProvider(result.provider,Path(config['call_log_dir'])/'policy')
        return result
    return OfflineRuntimeFactory(UnifiedEnvironmentFactory(build_environment_factory(scenario,env)),
                                 log_dir=config.get('call_log_dir')),policy_factory


def run_case(config, number, ordinal, replay=True):
    output=Path(config['output'])/'sources'/f'GPT50_{number:03d}';output.mkdir(parents=True,exist_ok=True)
    path=next(Path(config['source_root']).glob(f'*GPT50_{number:03d}_gpt/trajectory.json'))
    scenario_path=Path(config['scenario_root'])/f'gpt_{number:03d}.json'
    trajectory=load(path);scenario=load(scenario_path)
    reviews=load(Path(config['source_root'])/'gate3_followup/source_review.json')['candidates']
    review=next(x for x in reviews if x['scenario_id']==trajectory['scenario_id'])
    if review['model_semantic_review']['decision']!='approve' or review['latest_attempt']['artifact_sha256']!=sha(path):
        raise ValueError('source review/hash mismatch')
    source={'scenario_id':trajectory['scenario_id'],'trajectory_id':trajectory['trajectory_id'],
            'trajectory_path':str(path),'trajectory_sha256':sha(path),
            'scenario_path':str(scenario_path),'scenario_sha256':sha(scenario_path),
            'gate3_model_review':review['model_semantic_review'], 'origin':'source_rollout_with_controlled_interventions'}
    if (output/'source.json').exists() and load(output/'source.json')!=source:
        raise ValueError('frozen source changed')
    save(output/'source.json',source)
    public=source_input(trajectory,2)
    states={'initial_state':flatten_state(trajectory['initial_state']),
            'checkpoints':{f't{i+1}':flatten_state(t.get('state_after_public_events',t['state_after'])) for i,t in enumerate(trajectory['turns'][:2])}}
    items=question_group('T1',public,states,source,ordinal,output,config)
    plan_path=output/'interventions.json'
    if plan_path.exists():plan=load(plan_path)
    else:
        plan=author_call(author_provider(config),{
            'request':'为T2与T3设计受控干预。T2：保持背景与t1不变，仅改写t2受评者的台词为不同的有代价选择，不引入新事实；提供在原t2台词和改写台词之后都自然的共同中性回应（不能预设同意）。T3：在原t2之后提供2个真实取舍的行动，不要一好一坏的极端选项；每个行动180字以内，是受评者直接台词。所有中文。',
            'public_input':public,
            'temporal_guard':'history_b_action发生在t2环境回应之前：不得引用原t2回应首次提出或同意的事实、安排。t1是唯一共同前史。',
            'output_schema':{'history_b_action':'改写t2的行动','shared_ending':{'current_response':'共同台词','observable_expression':{'facial_expression':'可观察表情','gaze':'目光','speech_style':'语速','prosody':'音调','behavioral_cues':[]}},
                             'candidate_actions':[{'action_id':'action_1','text':'候选台词'},{'action_id':'action_2','text':'候选台词'}],
                             'edit_rationale':'改动位置、目的、保护事实，和两候选的真实取舍'}})
        if len(plan['candidate_actions'])!=2:raise ValueError('two candidates required')
        save(plan_path,plan)
    t2_input={k:deepcopy(v) for k,v in public.items() if k!='history'}
    for side in ('a','b'):
        hist=deepcopy(public['history'])
        for t in hist:t['turn_id']=side.upper()+':'+t['turn_id']
        hist[-1]['environment_character']='（共同回应见 ending）';hist[-1]['observable_expression']={}
        if side=='b':hist[-1]['evaluated_agent']=plan['history_b_action']
        t2_input['history_'+side]=hist
    t2_input['shared_ending']={'turn_id':'ending',**deepcopy(plan['shared_ending'])}
    t2_source={**source,'edits':[{'location':'history_b.t2.evaluated_agent','before':public['history'][1]['evaluated_agent'],'after':plan['history_b_action']},
                              {'location':'shared_ending','before':public['history'][1]['environment_character'],'after':plan['shared_ending']}],
               'edit_rationale':plan['edit_rationale']}
    factory,policy_factory=runtime(config,scenario,ordinal)
    save(output/'runtime.json',{'environment':factory.provenance,'source_environment':trajectory['environment_provenance'],
        'same_source_behavioral_settings':all(factory.provenance[k]==trajectory['environment_provenance'][k] for k in ('minimum_natural_turns','response_opportunity_guidance','state_calibration_profile','response_prompt','state_appraisal_prompt'))})
    t2_path=output/'t2_replay.json'
    if replay and not t2_path.exists():
        logs={}
        for side in ('a','b'):
            print(source['scenario_id'],'T2 replay',side,flush=True)
            env=factory();env.restore(trajectory['turns'][1]['environment_snapshot_before'],episode_id=f'offline-{number}-{side}')
            env.session['counterfactual_timeline_lock']=True
            action={'text':t2_input['history_'+side][-1]['evaluated_agent']}
            _,log=env.step(action,controlled_observation={**plan['shared_ending'],'media':[],'control_scope':'t2_shared_ending'})
            logs[side]=log
        if logs['a']['environment_response']!=logs['b']['environment_response'] or logs['a']['observable_expression']!=logs['b']['observable_expression']:
            raise ValueError('shared ending mismatch')
        save(t2_path,logs)
    t2_states=deepcopy(states)
    if t2_path.exists():
        replayed=load(t2_path)
        expected_snapshot=deepcopy(trajectory['turns'][1]['environment_snapshot_before'])
        expected_snapshot['counterfactual_timeline_lock']=True
        for side in ('a','b'):
            log=replayed[side]
            if (log['policy_action']['text'] != t2_input['history_'+side][-1]['evaluated_agent']
                    or log['environment_response'] != plan['shared_ending']['current_response']
                    or log['observable_expression'] != plan['shared_ending']['observable_expression']
                    or log['environment_snapshot_before'] != expected_snapshot):
                raise ValueError('cached T2 replay differs from current source/intervention; preserve it and rebuild')
        t2_states['replayed_pair']={s:flatten_state(log['state_after']) for s,log in replayed.items()}
        t2_source.update(replay_path=str(t2_path),replay_sha256=sha(t2_path))
    items+=question_group('T2',t2_input,t2_states,t2_source,ordinal,output,config,
                          replay_status='validated' if t2_path.exists() else 'pending')
    t3_input={**deepcopy(public),'candidate_actions':plan['candidate_actions']}
    horizon=config.get('delayed_horizon',5)
    branches_path=output/'t3_branches.json'
    if replay and not branches_path.exists():
        print(source['scenario_id'],'T3 branches starting',flush=True)
        progress_root=output/'branch_progress'
        prior={}
        # Each run owns a new directory. Earlier real provider records stay intact.
        directories=[progress_root]+sorted((progress_root/'runs').glob('*'))
        for directory in directories:
            grouped={}
            for path in directory.glob('*.json'):
                parts=path.stem.split('_')
                if len(parts)==3 and all(x.isdigit() for x in parts):
                    branch,attempt,step=map(int,parts)
                    grouped.setdefault((branch,attempt),{})[step]=load(path)
            for branch,attempt in sorted(grouped):
                steps=grouped[branch,attempt]
                if set(steps)==set(range(1,max(steps)+1)):
                    prior[branch]=[steps[i] for i in sorted(steps)]
        progress_dir=progress_root/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        for branch,logs in prior.items():
            for step,log in enumerate(logs,1):save(progress_dir/f'{branch}_0_{step}.json',log)
        branches=branch_counterfactuals(factory,trajectory['turns'][2],
                                       [{'text':a['text']} for a in plan['candidate_actions']],policy_factory,horizon,
                                       branch_workers=config.get('branch_workers',2),resume_logs=prior,
                                       audit_callback=lambda branch,attempt,step,log:save(progress_dir/f'{branch}_{attempt}_{step}.json',log))
        save(branches_path,branches)
    t3_states=deepcopy(states);t3_source=deepcopy(source)
    complete=False
    if branches_path.exists():
        branches=load(branches_path)
        import hashlib
        snapshot=trajectory['turns'][2]['environment_snapshot_before']
        expected_hash=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if (len(branches) != len(plan['candidate_actions'])
                or any(b['snapshot_sha256'] != expected_hash
                       or b['candidate_action']['text'] != a['text']
                       or b['delayed_horizon'] != horizon
                       or b['external_event_plan_hash'] != snapshot.get('event_plan',{}).get('plan_hash')
                       for b,a in zip(branches,plan['candidate_actions']))):
            raise ValueError('cached T3 branches differ from current source/intervention')
        complete=all(b['window_complete'] and b['actual_turns_observed']==horizon and len(b['future_turns'])==horizon for b in branches)
        t3_states['branches']=[{k:deepcopy(b[k]) for k in ('candidate_action','state_before','state_after_immediate_action_response','state_after_delayed','actual_turns_observed')} for b in branches]
        t3_states['future_evidence']=[[{'action':t['policy_action']['text'],'response':t['environment_response']} for t in b['future_turns']] for b in branches]
        t3_source.update(replay_path=str(branches_path),replay_sha256=sha(branches_path))
    if replay and not complete:
        raise ValueError('incomplete delayed branch; retained for review, cannot label delayed questions')
    items+=question_group('T3',t3_input,t3_states,t3_source,ordinal,output,config,
                          replay_status='validated' if complete else 'pending')
    return items


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/offline_choice_dev60.json')
    parser.add_argument('--scenarios',type=int,nargs='+',help='Subset of configured scenarios; stable original ordinals')
    parser.add_argument('--tasks',nargs='+',choices=['T1','T2','T3'],help='Task subset for a configured batch')
    parser.add_argument('--request-timeout',type=int,help='Batch transport timeout override, recorded per run')
    parser.add_argument('--workers',type=int,help='Batch scenario concurrency override, recorded per run')
    parser.add_argument('--transport-attempts',type=int,help='Bounded transport attempts per request, recorded per run')
    parser.add_argument('--recovery-attempts',type=int,help='Additional resumes after transport, empty or truncated provider responses; never content/source validation')
    parser.add_argument('--reuse-factual-continuation',action='store_true',help='Use a verified observed five-turn branch plus a newly authored alternative')
    parser.add_argument('--author-only',action='store_true',help='Explicit draft mode without counterfactual execution')
    parser.add_argument('--export-only',action='store_true')
    parser.add_argument('--pair-media',type=Path,help='Existing online media manifest; pair exact source asset IDs')
    args=parser.parse_args(argv);config=load(args.config);items=[];failures=[]
    if config.get('format') == 'socialflux_offline_choice_gpt50_v1':
        from offline.choice_batch import run_batch
        return run_batch(config,args)
    if args.tasks or args.request_timeout or args.workers or args.transport_attempts or args.recovery_attempts is not None or args.reuse_factual_continuation:
        parser.error('task/transport overrides require a batch configuration with an explicit task set')
    if not args.export_only:
        with ThreadPoolExecutor(max_workers=config['workers']) as pool:
            futures={pool.submit(run_case,config,n,i,not args.author_only):n for i,n in enumerate(config['scenario_numbers']) if not args.scenarios or n in args.scenarios}
            for f in as_completed(futures):
                try:items+=f.result()
                except Exception as e:
                    n=futures[f];error={'scenario':n,'error_type':type(e).__name__,'message':str(e)[:1800]}
                    failures.append(error);print(json.dumps(error,ensure_ascii=False),flush=True)
                    case_dir=Path(config['output'])/'sources'/f'GPT50_{n:03d}'
                    save(case_dir/'last_error.json',error)
                    with (case_dir/'failures.jsonl').open('a',encoding='utf-8') as log:
                        log.write(json.dumps(error,ensure_ascii=False)+'\n')
                    if getattr(e,'last_raw',None):
                        save(case_dir/'failed_author_output.json',{'raw':e.last_raw,'last_validation_error':str(getattr(e,'last_error',''))})
    # Export completed groups even after a case failed; never erase source errors.
    items=[]
    for ordinal,n in enumerate(config['scenario_numbers']):
        for task in ('T1','T2','T3'):
            p=Path(config['output'])/'sources'/f'GPT50_{n:03d}'/(task+'.items.json')
            if p.exists():
                cached=load(p)
                raw_path=p.with_name(task+'.curated.json')
                if not raw_path.exists():raw_path=p.with_name(task+'.authored.json')
                if raw_path.exists():
                    questions=load(raw_path)['questions']
                    if len(questions)!=len(cached):raise ValueError('author artifact/item count differs')
                    cached=[assemble(raw,task=task,source=old['authoring']['construction_source'],
                                     public_input=old['input'],ordinal=ordinal,index=i,
                                     replay_status=old['authoring']['replay_status'])
                            for i,(raw,old) in enumerate(zip(questions,cached))]
                    freeze_authoring_source(cached,raw_path)
                    save(p,cached)
                items+=cached
    manifest=write_bundle(sorted(items,key=lambda x:x['instance_id']),config['output'])
    save(Path(config['output'])/'run_status.json',{'failures':failures,'items':len(items),'expected':12*len(config['scenario_numbers']),
         'replay_ready':manifest['replay_ready_count'],'replay_pending_ids':manifest['replay_pending_ids'],
         'human_review':'pending'})
    from offline.choice_audit import audit_bundle
    audit_bundle(items,config['output'])
    if args.pair_media:
        from offline.choice_media import pair_assets
        manifest['pairing']=pair_assets(items,args.pair_media,Path(config['output']))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
