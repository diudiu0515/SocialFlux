"""Read-only current GPT50 generation, with explicitly labelled historical artifacts."""
from datetime import datetime,timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary'
ACTIVE=BASE/'unified_current_trust_v1_gpt50_active'
SCENARIOS=BASE/'unified_current_trust_v1_gpt50'
SOURCES=[
    ('current','当前批次',ACTIVE,False),
    ('transport_history','修正版历史 · 接口中断',BASE/'unified_current_trust_v1_gpt50_corrected_transport',False),
    ('corrected_history','修正版首次验证 · 超时',BASE/'unified_current_trust_v1_gpt50_corrected_horizon',False),
    ('invalid_horizon','旧配置记录 · 已排除',BASE/'unified_current_trust_v1_gpt50_resumed',True),
]


def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (FileNotFoundError,json.JSONDecodeError):return default


def artifact(directory):
    return next((directory/name for name in ('trajectory.json','partial_trajectory.json','checkpoint.json') if (directory/name).is_file()),None)


def versions(index,scenario_id):
    rows=[]
    for key,label,root,invalid in SOURCES:
        directory=root/f'{index:02d}_{scenario_id}_gpt'
        path=artifact(directory)
        if path is None:continue
        result=read(directory/'result.json',{})
        count=result.get('turns',result.get('completed_turns'))
        if count is None:count=len(read(path,{}).get('turns',[]))
        rows.append({'key':key,'label':label,'invalid_configuration':invalid,
                     'current':key=='current','turn_count':count,
                     'status':result.get('status','running' if key=='current' else 'interrupted'),
                     'ending':result.get('ending'),'error':result.get('error'),
                     'artifact_kind':path.name,'modified_at':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),
                     '_path':path})
    return rows


def safe_version(row):return {k:v for k,v in row.items() if not k.startswith('_')}


@lru_cache(maxsize=256)
def source_identity(path, modified_ns, size):
    # Hash unchanged artifacts once; never attach a review merely by scenario ID.
    content=path.read_bytes()
    return json.loads(content).get('trajectory_id'),hashlib.sha256(content).hexdigest()


def review_indexes():
    gate3=read(ACTIVE/'gate3_followup/gate3/model_reviews.json',{})
    gate2=read(ACTIVE/'gate2_followup/gate2/experiments/environment_interventions.json',{})
    return ({r['scenario_id']:r for r in gate3.get('records',[])},
            {r['scenario_id']:r for r in gate2.get('records',[])})


def scenario_reviews(row, scenario_id, indexes, *, details=False):
    review={'status':'pending','human_review_status':'pending'}
    if row is None:
        return {**review,'status':'no_trajectory'},[]
    if not row['current']:
        return {**review,'status':'historical_not_reviewed'},[]
    gate3,gate2=indexes
    record=gate3.get(scenario_id)
    experiment=gate2.get(scenario_id,{})
    if record is None and not experiment.get('error'):
        return review,[]
    path=row['_path'];stat=path.stat()
    trajectory_id,source_hash=source_identity(path,stat.st_mtime_ns,stat.st_size)
    if record is not None:
        if record.get('trajectory_id')!=trajectory_id or record.get('source_sha256')!=source_hash:
            review['status']='source_changed'
        else:
            review.update(status='reviewed',decision=record['decision'],
                          partial=record.get('source_status')=='generation_error',
                          reviewed_at_utc=record.get('reviewed_at_utc'),model=record.get('model'))
            if details:
                review.update({k:record.get(k) for k in ('scores','hard_reject_reasons','evidence','rationale')})
    errors=[]
    if experiment.get('error') and experiment.get('source_trajectory_id')==trajectory_id:
        number=scenario_id.rsplit('_',1)[-1]
        audit=read(ACTIVE/'gate2_followup/rollouts'/f'scenario_{number}'/'trajectory.json',{})
        if audit.get('gate2_audit_input',{}).get('source_sha256')==source_hash:
            error=experiment['error'];kind=error.get('type','ExecutionError')
            # Public explanations only; provider errors can contain raw request data.
            message=('模型输出未通过 JSON/结构校验' if kind=='StructuredOutputError'
                     else '接口不支持 top_p 参数' if 'top_p' in error.get('message','')
                     else '模型调用或实验执行出错，尚无通过结论')
            errors.append({'stage':'Gate2 干预实验','type':kind,'message':message,
                           'checkpoint_turn_id':experiment.get('checkpoint_turn_id')})
    return review,errors


def gate2_summary():
    job=read(ACTIVE/'automatic_gate2_job.json',{})
    root=ACTIVE/'gate2_followup/gate2'
    manifest=read(root/'manifest.json',{})
    packets=[]
    for key,name in [('E1','state_transition_agreement.json'),('E2','trajectory_plausibility.json'),('E9','timescale_validity.json')]:
        value=read(root/name,{})
        packets.append({'id':key,'items':len(value.get('review_items',[])),
                        'status':value.get('record',{}).get('review_status','尚未生成'),
                        'human_attestation':value.get('record',{}).get('human_attestation',False)})
    return {'status':job.get('status','not_started'),'machine_ready':manifest.get('machine_evidence_ready',False),
            'human_review_required':True,'packets':packets,'error':job.get('error'),
            'execution_status':manifest.get('execution_status'),'source':'current'}


def load_live(scenario_id=None):
    manifest=read(SCENARIOS/'manifest.json',{})
    cases=manifest.get('cases',[])
    indexes=review_indexes()
    if scenario_id is not None:
        match=next(((i,c) for i,c in enumerate(cases) if c['scenario_id']==scenario_id),None)
        if match is None:return None
        index,case=match
        scenario=read(ROOT/case['candidate'],{})
        items=[]
        for row in versions(index,scenario_id):
            gate3,gate2_errors=scenario_reviews(row,scenario_id,indexes,details=True)
            trajectory=read(row['_path'],{})
            localized=read(row['_path'].parent/'english/review.json',{}) if row['current'] else {}
            english=localized.get('rollout',{})
            original_turns=trajectory.get('turns',[])
            english_turns=english.get('turns',[])
            # A checkpoint can advance while its translation is still running.
            # Only expose a translated prefix whose IDs and numeric states agree.
            compatible=(bool(english_turns) and english.get('trajectory_id')==trajectory.get('trajectory_id')
                        and len(english_turns)<=len(original_turns)
                        and all(all(a.get(k)==b.get(k) for k in ('turn_id','state_before','state_after','dynamics_before','dynamics_after'))
                                for a,b in zip(english_turns,original_turns)))
            if compatible:
                trajectory=english
                scenario=localized.get('scenario',scenario)
                row={**row,'label':row['label']+' · English',
                     'language':'en','source_turn_count':len(original_turns),
                     'turn_count':len(english_turns),
                     'translation_review':localized.get('localization',{}).get('semantic_equivalence_review','pending'),
                     'modified_at':row['modified_at']+'|'+str((row['_path'].parent/'english/review.json').stat().st_mtime)}
                if len(english_turns)<len(original_turns):
                    row['label']+=f" · {len(english_turns)}/{len(original_turns)} 轮已翻译"
            turns=[]
            for turn_index,t in enumerate(trajectory.get('turns',[])):
                turns.append({k:t.get(k) for k in ('turn_id','policy_action','environment_response','state_before',
                  'state_after','numeric_state_delta','dynamics_before','dynamics_after','numeric_dynamics_delta',
                  'state_judgments','dynamics_judgments')})
                # Read trigger evidence from the original log, not a translation
                # or an audit of another rollout. Never expose provider requests.
                source_turn=original_turns[turn_index]
                events=source_turn.get('trigger_events')
                turns[-1]['trigger_events']=([
                    {k:event.get(k) for k in (
                        'media_event_id','trigger_id','trigger_mode','trigger_variables',
                        'media_asset_id','event_family','source_state_variable',
                        'source_direction','trigger_policy_profile','video_api_status')}
                    for event in events if isinstance(event,dict)
                ] if isinstance(events,list) else None)
            items.append({**safe_version(row),'trajectory_id':trajectory.get('trajectory_id'),
                          'gate3':gate3,'gate2_errors':gate2_errors,
                          'turns':turns,'ending':trajectory.get('ending'),'initial_state':trajectory.get('initial_state',scenario.get('initial_state')),
                          'initial_dynamics':trajectory.get('initial_dynamics',scenario.get('initial_dynamics'))})
        return {'scenario':scenario,'versions':items,'gate2':gate2_summary(),'human_review_status':'pending'}
    batch=read(ACTIVE/'results.json',{})
    result_rows=batch.get('rows',{})
    entries=[]
    for index,case in enumerate(cases):
        scenario=read(ROOT/case['candidate'],{})
        items=versions(index,case['scenario_id'])
        current=next((x for x in items if x['current']),None)
        directory=ACTIVE/f"{index:02d}_{case['scenario_id']}_gpt"
        result=result_rows.get(str(index),read(directory/'result.json',{}))
        state=result.get('status','running' if directory.exists() else 'queued')
        gate3,gate2_errors=scenario_reviews(current,case['scenario_id'],indexes)
        entries.append({'scenario_id':case['scenario_id'],'title':scenario.get('title',''),
                        'policy_name':scenario.get('evaluated_agent_role',{}).get('name',''),
                        'environment_name':scenario.get('environment_agent',{}).get('persona',{}).get('name',''),
                        'status':state,'turn_count':current['turn_count'] if current else 0,
                        'gate3':gate3,'gate2_errors':gate2_errors,
                        'readable':bool(current and current['turn_count']),'history_available':bool(items),
                        'versions':[safe_version(v) for v in items]})
    counts={name:sum(x['status']==name for x in entries) for name in ('completed','running','queued')}
    counts['failed']=sum(x['status'] in ('call_or_validation_failure','runner_failure') for x in entries)
    counts['readable']=sum(x['readable'] for x in entries)
    counts['history_readable']=sum(x['history_available'] for x in entries)
    counts['gate3_rejected']=sum(x['gate3'].get('decision')=='reject' for x in entries)
    counts['gate2_errors']=sum(bool(x['gate2_errors']) for x in entries)
    return {'batch':'GPT50 · 当前统一 state 候选','status':batch.get('status','not_started'),
            'updated_at':datetime.now(timezone.utc).isoformat(),'expected_count':50,'counts':counts,
            'scenarios':entries,'gate2':gate2_summary(),'human_review_status':'pending'}
