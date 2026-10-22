"""Read-only, allowlisted experiment summaries; never return trajectories or calls."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from evaluation.quality_gates import ENVIRONMENT_EVIDENCE
from web.live_rollouts import ROOT, ACTIVE, load_live
from web.dataset_counts import load_dataset_counts
from web.t4_accounting import execution_accounting

METRICS=('goal_achievement','state_adaptation','risk_management','recovery','relationship_outcome','five_dimension_mean')
RUNS=(
    ('t4_persistent41_20261022','41 场景持续补齐配对 · 2026-10-22','persistent_pair_recovery'),
    ('t4_claude_retry41_20261021','41 场景 Claude 空响应补调 · 2026-10-21','empty_retry_continuation'),
    ('t4_full41_continuation_20261021','41 场景总量续跑 · 2026-10-21','full_cohort_continuation'),
    ('t4_reliable41_20261021','41 场景完整对照 · 2026-10-21','reliable_cohort'),
    ('t4_transport_recovery_20261021','六场景诊断的传输恢复 · 2026-10-21','transport_recovery'),
    ('t4_expanded_api_20261020','8 模型 × 6 诊断场景 · 2026-10-20','diagnostic_run'),
    ('t4_gpt33_parallel_20261020','33 场景并行续跑 · 2026-10-20','current'),
    ('t4_gpt39_continuation_20261020','39 场景续跑 · 2026-10-20（含移交槽位）','separate_run'),
    ('t4_gpt41_paired_20261020','41 场景首批尝试 · 2026-10-20','stopped_run'),
    ('t4_gpt50_20261008','原 GPT 轨迹终局评分 · 2026-10-08','historical_scoring'),
)
GATE_NAMES=(
    ('Gate 1','场景质量','社会合理性、双方动机、真实取舍、历史作用与任务适用性；核验冻结的初始状态。','全场景审核；1 名审核人。'),
    ('Gate 2','环境有效性','E1–E9：状态更新、整段合理性、历史干预、释义稳健性、局部分支、骨干敏感性、人格干预、视频一致性和变化速度。','实验提供证据；规定样本仍需人工确认。'),
    ('Gate 3','轨迹质量','连贯性、历史依赖、人物一致性、状态与回应一致性、互动推进、自然性；单条轨迹准入。','主审核覆盖全部，另设 20% 确定性审计样本；不按多条候选择优。'),
    ('Gate 4','任务质量','新版 T1 检查公开证据和状态判断；T2 检查受控历史与共同表达；T3 检查合理行动、比较基准和即时／延迟后果。','两名独立审核人检查同一每任务 10% 样本（至少 2 题）；只对分歧增加第三人。'),
)
E_NAMES=('状态更新一致性','完整轨迹合理性','历史干预','释义稳健性','局部反事实','环境骨干敏感性','仅人格干预','视频与状态一致性','变化速度有效性')


def metric(value):
    return {k:value.get(k) for k in ('n','mean','sd','bootstrap_ci95')}


def model_summary(value):
    return {
        'status_counts':{k:v for k,v in value.get('status_counts',{}).items() if isinstance(v,int)},
        'conditions':{c:{'n':v.get('n',0),'metrics':{k:metric(v.get('metrics',{}).get(k,{})) for k in METRICS}}
                      for c,v in value.get('conditions',{}).items() if c in ('text_only','text_video')},
        'matched_scenarios':value.get('matched_scenarios',0),
        'paired_differences':{k:metric(value.get('paired_text_video_minus_text',{}).get(k,{})) for k in METRICS},
        'human_validation_status':value.get('human_validation_status','not_human_validated'),
    }


def process_alive(pid,run_id):
    if not isinstance(pid,int) or pid<1:return False
    try:
        cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
        return (run_id.encode() in cmd and any(script in cmd for script in (
                    b'run_t4_multimodal_experiment.py', b'resume_t4_transport.py', b'continue_t4_pairs.py', b'run_s0_mechanism_ablation.py',
                    b'continue_s0_mechanism_ablation.py', b'continue_s0_mechanism_ablation_v2.py',
                    b'scripts.run_gate2_followup', b'run_gate2_followup.py', b'resume_s0_empty_compat.py', b'scripts.resume_gate2_supplements', b'resume_gate2_supplements.py',
                    b'scripts.resume_gate2_reliable', b'resume_gate2_reliable.py'))
                and Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[0]!='Z')
    except (OSError,IndexError):return False


def discover_run_pid(run_id):
    """Some runners have no process.json; match the exact script/output arguments."""
    expected=str(ROOT/'build'/run_id/'run')
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            args=directory.joinpath('cmdline').read_bytes().decode().split('\0')
            if (any(Path(arg).name in ('run_t4_multimodal_experiment.py', 'resume_t4_transport.py', 'continue_t4_pairs.py') for arg in args)
                    and '--output' in args and args[args.index('--output')+1]==expected
                    and process_alive(int(directory.name),run_id)):
                return int(directory.name)
        except (OSError,ValueError,IndexError,UnicodeError):
            continue
    return None


def load_experiment_status():
    sources=[];errors=[]
    def read(path):
        if not path.is_file():return {}
        try:
            raw=path.read_bytes();value=json.loads(raw)
            sources.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest()})
            return value
        except (OSError,ValueError) as exc:
            errors.append({'path':str(path.relative_to(ROOT)),'error':type(exc).__name__});return {}
    live=load_live()
    plan=read(ROOT/'configs/human_review_plan.json')
    current_root=ROOT/'data/gate2_machine_20261020_complete'
    root=current_root/'gate2' if (current_root/'gate2/manifest.json').exists() else ACTIVE/'gate2_followup/gate2'
    gm=read(root/'manifest.json')
    machine_progress=read(current_root/'progress.json')
    raw=read(root/'experiments/environment_interventions.json').get('records',[])
    partial={key:{'records':sum(isinstance(r.get(key),dict) for r in raw),
                  'screen_passed':sum(r.get(key,{}).get('automatic_screen_passed') is True for r in raw)}
             for key in ('e3','e4','e5','e7')}
    checks=gm.get('formal_gate2_audit',{}).get('checks',{})
    experiments=[]
    for i,(key,filename) in enumerate(ENVIRONMENT_EVIDENCE.items(),1):
        media_path=ROOT/'data/gate_media_machine_20261020/video_state_consistency.json'
        artifact_path=media_path if i==8 and media_path.exists() else root/filename
        artifact=read(artifact_path);record=artifact.get('record',{})
        experiments.append({'id':f'E{i}','name':E_NAMES[i-1],'status':checks.get(key,{}).get('status','pending'),
            'source':str(artifact_path.relative_to(ROOT)),
            'evidence_present':bool(artifact),'review_items':len(artifact.get('review_items',[])),
            'human_attestation':record.get('human_attestation',False),'raw_partial':partial.get(f'e{i}'),
            'machine_record':{k:v for k,v in record.items() if k in (
                'matched_checkpoint_count','pair_count','checkpoint_count','automatic_screen_passed_count',
                'direction_consistency','active_union_direction_agreement','machine_screen_passed',
                'machine_coverage_ready','matched_node_count','generated_video_count','machine_reviewed_nodes',
                'visual_passed_nodes','llm_review_status','audio_semantic_review','direction_agreement',
                'replay_failure_count','matched_variable_count','candidate_variable_count','transition_count',
                'trajectory_count','passed','successful_matched_checkpoint_count',
                'mean_active_union_direction_agreement','mean_true_sign_reversal_rate','backbone_activity_passed')},
            'report_metrics':{k:v for k,v in record.items() if k in (
                'agreement','scores','annotator_count','matched_variable_count','candidate_variable_count',
                'timescale_families','direction_consistency','active_union_dimension_count',
                'mean_active_union_direction_agreement','record_pass_fraction','thresholds',
                'machine_unchanged_fraction','source_status_counts','review_sample_zero_change_fraction',
                'review_sample_zero_change_count','non_degenerate','automatic_screen_pass_fraction')},
            'machine_records':len(artifact.get('records',[]))})
    g3=read(ACTIVE/'gate3_followup/gate3/model_reviews.json')
    g1=read(ROOT/'data/gate_media_machine_20261020/gate1.json')
    g3_secondary=read(ROOT/'data/gate3_machine_20261020/progress.json')
    oracle=read(ROOT/'data/offline_oracle_20261020_complete/progress.json')
    bank=read(ROOT/'tasks/examples/offline_scenarios_v2/manifest.json')
    items_path=ROOT/'tasks/examples/offline_scenarios_v2/items.jsonl'
    items=[json.loads(line) for line in items_path.read_text().splitlines()] if items_path.exists() else []
    gates=[{'id':i,'name':name,'purpose':purpose,'review_setting':setting,'formal_status':'pending'}
           for i,name,purpose,setting in GATE_NAMES]
    gates[0]['reviewer_count']=plan.get('gate1',{}).get('reviewers_required')
    gates[0]['machine_audit']={k:g1.get(k) for k in ('scenario_count','schema_passed','formal_passed')}
    gate2_executed=bool(machine_progress and machine_progress.get('intervention_groups')==machine_progress.get('expected_readable_sources')
                        and machine_progress.get('backbone_groups')==machine_progress.get('expected_readable_sources'))
    gates[1].update(run_status=('machine_checks_executed' if gate2_executed else 'machine_checks_in_progress' if machine_progress else live['gate2']['status']),
        machine_evidence_ready=gm.get('machine_evidence_ready',False),
        source_contract_status=gm.get('gate2',{}).get('status'),
        experiments=experiments,raw_intervention_records=len(raw),raw_execution_errors=sum(bool(r.get('error')) for r in raw),
        machine_progress={k:v for k,v in machine_progress.items() if k!='records'})
    gates[2].update(machine_reviewed=g3.get('reviewed_count',0),machine_decisions=g3.get('decision_counts',{}),
        missing_sources=live['expected_count']-g3.get('reviewed_count',0),human_status=g3.get('human_review_status','pending'),
        audit_fraction=plan.get('gate3',{}).get('secondary_audit_fraction'),
        independent_audit={k:g3_secondary.get(k) for k in ('expected_audit_count','reviewed','decision_counts','disagreements')})
    gates[3].update(sample_fraction=plan.get('gate4',{}).get('sample_fraction_per_task_type'),
        reviewers=plan.get('gate4',{}).get('independent_reviewers'),
        oracle_check={k:oracle.get(k) for k in ('source_items','authored_items','independently_checked_items',
                                               'public_blind_checked_items','oracle_agreement_items','machine_concern_ids')})
    offline={k:bank.get(k) for k in ('item_count','scenario_count','tasks','blind_reviewed_items','machine_flagged_ids','modality_pairs','design_difficulties','answer_positions')}
    offline.update(formal_admitted=sum(bool(x['authoring'].get('source_admission',{}).get('formal_admitted')) for x in items),
        human_labeled=sum(x.get('ground_truth') is not None for x in items),
        t2_replay_pending_scenes=len({x['story_id'] for x in items if x['task']=='T2' and x['authoring']['replay_status']!='validated'}),
        oracle_progress={k:v for k,v in oracle.items() if k not in ('pending_groups',)},
        annotation_url='/offline-annotation',
        interpretation='出题与盲试答筛查，不是独立模型能力测试；上帝视角机器候选与人工 GT 分开。')
    runs=[]
    for run_id,title,kind in RUNS:
        directory=ROOT/'build'/run_id/'run'
        summary=read(directory/'summary.json')
        if not summary:continue
        status=read(directory/'status.json');proc=read(directory/'process.json')
        models={'gpt_source':model_summary(summary)} if kind=='historical_scoring' else {
            k:model_summary(v) for k,v in summary.items() if isinstance(v,dict) and 'conditions' in v and 'status_counts' in v}
        run_plan=read(directory/'plan.json') if kind!='historical_scoring' else {}
        accounting=execution_accounting(run_plan,read(directory/'results.json'),models) if run_plan else []
        pid=proc.get('pid')
        alive=process_alive(pid,run_id)
        if not alive and status.get('status')=='running':
            pid=discover_run_pid(run_id)
            alive=pid is not None
        runs.append({'id':run_id,'title':title,'kind':kind,'reported_status':status.get('status','historical_complete'),
            'process_alive':alive,'updated_at':status.get('updated_at'),
            'finished_slots':status.get('finished'),'planned_slots':status.get('planned'),
            'api_requests':status.get('api_requests',summary.get('api_request_count')),'models':models,
            'execution_accounting':accounting,
            'note':'继承已成功结果，优先补齐缺失的一侧；截断请求提高输出额度，临时故障退避重试，格式失败保留记录后补调。恢复采用新的重试规则，成绩与首次尝试分开解释；继承结果不增加独立样本。' if kind=='persistent_pair_recovery' else
                   '进度为 25 条传输故障的恢复进度；评分表包含继承的原批次完整轨迹，不是新增独立样本。原始失败另存，API 数仅计新增请求。' if kind=='transport_recovery' else
                   '继承 full41 的原始结果并逐字重放成功回答；Claude 空响应只补第二次，继续其余场景。原始失败留存，不与前批重复计数。模型、提示词、视频与评分规则不变。' if kind=='empty_retry_continuation' else
                   '继承 reliable41 的 16 条记录（含 3 条失败），补跑剩余 148 条；不是独立新样本，勿与前批重复计数。失败率仅告警，累计请求上限 10000；视频与评分规则不变。' if kind=='full_cohort_continuation' else
                   '全部 41 个视频素材齐全场景，2 模型 × 2 条件；前两场景检查可靠性，按两场景逐批继续。独立于旧 33 场景成绩。' if kind=='reliable_cohort' else
                   '固定 6 个失败诊断场景，不代表 50 场景总体；视频传输随模型能力使用原生视频或帧，不支持的条件单列。' if kind=='diagnostic_run' else
                   '移交槽位不等于完成轨迹；各 run 分开统计，不跨 run 拼接配对。' if kind=='separate_run' else
                   '单一 GPT 策略轨迹的历史终局评分；不属于新多策略配对成绩。' if kind=='historical_scoring' else
                   '视频条件使用 4 个带时间戳的视频帧，不含音频；未送达视频与不支持视频单列。'})
    history=read(ROOT/'reports/experiments/2026-09-26_gpt50_gate2_record.json')
    historical={'date':history.get('record_date_utc'),'status':history.get('formal_status'),
        'note':'旧批次实验；不得作为当前环境配置的通过证明。',
        'checks':{k:{a:b for a,b in v.items() if a in ('records','automatic_pass','automatic_fail','direction_consistency','direction_agreement','replay_failure_count','effective_preliminary_visual_pass','human_matches','candidates')}
                  for k,v in history.get('checks',{}).items()}}
    s0_source=read(ROOT/'data/gate2_s0_mechanism_20261021/summary.json')
    s0={k:s0_source[k] for k in ('run_id','version','updated_at','status','pid','target_scenarios',
        'expected_condition_runs','expected_turns_per_condition','saved_turns','frozen_checked_turns',
        'human_review','scope') if k in s0_source}
    if s0:
        diagnosis=read(ROOT/'data/gate2_s0_mechanism_20261021/diagnostic_status.json')
        s0['diagnostics']={k:diagnosis[k] for k in ('updated_at','reason','failure_counts',
            'execution_counts','bounds_preflight','provider_probe') if k in diagnosis}
        correction=read(ROOT/'data/gate2_s0_mechanism_20261021/bounds_recovery.json')
        s0['bounds_recovery']={k:correction[k] for k in ('status','revision','pilot_scenario',
            'changed_scenarios','source_cohort_unchanged','replacement_rule','note') if k in correction}
        compatibility=read(ROOT/'data/gate2_s0_mechanism_20261021/empty_error_compat.json')
        s0['empty_error_compat']={k:compatibility[k] for k in ('status','workers',
            'maximum_additional_retries_per_condition','backoff_seconds','outcomes') if k in compatibility}
        continuation=read(ROOT/'data/gate2_s0_mechanism_20261021/supplement_continuation_20261022.json')
        s0['supplement_continuation']={k:continuation[k] for k in ('status','created_at','updated_at','workers',
            'pilot_scenario','pilot_status','planned_condition_jobs','finished_condition_jobs','new_saved_turns',
            'preserved_terminal_counts','source_cohort_unchanged','original_failures_resampled','current_jobs',
            'stop_reason','original_terminal_hashes_verified','token_budget_amendment') if k in continuation}
        reliable=read(ROOT/'data/gate2_s0_mechanism_20261021/reliable_continuation_20261022.json')
        s0['reliable_continuation']={k:reliable[k] for k in ('status','created_at','updated_at','workers',
            'pilot_scenario','pilot_expected_turns','pilot_status','planned_condition_jobs','finished_condition_jobs',
            'new_saved_turns','current_jobs','budget_policy','previous_results_archived','original_prefixes_preserved',
            'recovered_operational_conditions','original_archives_and_prefixes_verified','stop_reason') if k in reliable}
        prompt_audit=read(ROOT/'data/gate2_s0_mechanism_20261021/prompt_ablation_audit.json')
        s0['prompt_audit']={'scenario_id':prompt_audit.get('scenario_id'),'turn':prompt_audit.get('turn'),
            'checks':{k:v for k,v in prompt_audit.get('checks',{}).items() if k in (
                'repeat_identical_state_request','repeat_identical_interaction_request',
                'frozen_state_request_count','frozen_update_policy_present')}} if prompt_audit else {}
        recovery=read(ROOT/'data/gate2_s0_mechanism_20261021/recovery.json')
        s0['transport_recovery']={k:recovery[k] for k in ('status','registered_timeout_seconds',
            'initial_effective_timeout_seconds','inputs_unchanged','scene_order_unchanged',
            'exact_completed_call_reuse','maximum_transport_resumes_per_condition',
            'maximum_empty_response_resumes_per_condition',
            'semantic_rejections_resampled','protocol_amendment') if k in recovery}
        if recovery:
            initial=read(ROOT/'data/gate2_s0_mechanism_20261021/summary.before_transport_recovery.json')
            s0['transport_recovery']['initial_failure_counts']=dict(Counter(
                row.get('error_type','unknown') for row in initial.get('failures',[])))
        s0_manifest=read(ROOT/'data/gate2_s0_mechanism_20261021/manifest.json')
        cohort=s0_manifest.get('sources',[])
        s0['source_status_counts']=dict(Counter(row.get('source_status','unknown') for row in cohort))
        s0['source_turn_range']=[min((row.get('turns',0) for row in cohort),default=0),
                                 max((row.get('turns',0) for row in cohort),default=0)]
        s0['process_alive']=process_alive(s0.get('pid'),s0.get('run_id','gate2_s0_mechanism_20261021'))
        if s0.get('status') in ('running','pilot_running') and not s0['process_alive']:
            s0['status']='interrupted'
        allowed=('dynamic_state','dynamic_repeat','replaced_s0','fixed_s0_no_update_prompt')
        s0['conditions']={c:{k:v for k,v in values.items() if k in ('completed','failed','saved_turns')}
                          for c,values in s0_source.get('conditions',{}).items() if c in allowed}
        s0['execution_counts']={}
        active_s0_jobs={tuple(job) for job in (s0.get('reliable_continuation') or s0.get('supplement_continuation',{})).get('current_jobs',[])} if s0['process_alive'] else set()
        for condition in allowed:
            counts=Counter()
            for sid in s0_manifest.get('scenario_ids',[]):
                record=read(ROOT/'data/gate2_s0_mechanism_20261021/results'/sid/condition/'result.json')
                phase=record.get('status','not_started')
                if phase not in ('completed','failed') and (sid,condition) in active_s0_jobs:
                    phase='running'
                counts[phase]+=1
                counts['saved_turns']+=len(record.get('turns',[]))
            s0['execution_counts'][condition]=dict(counts)
        s0['pairs']={c:{'n':value.get('n',0),'metrics':{k:v for k,v in value.get('metrics',{}).items()
                    if k in ('state_delta_mae','state_level_mae','response_text_distance')}}
                    for c,value in s0_source.get('pairs',{}).items() if c in allowed}
        s0['failures']=[{k:v for k,v in row.items() if k in ('scenario_id','condition','error_type','failed_turn_index')}
                        for row in s0_source.get('failures',[])]
    followup_path = ROOT/'data/gate2_followup_final_20261022/summary.json'
    followup = read(followup_path)
    if followup:
        followup['matched_controls'] = read(ROOT/'data/gate2_followup_final_20261022/matched_controls.json')
        followup['process_alive'] = process_alive(followup.get('pid'), followup.get('run_id'))
        budget = read(ROOT/'data/gate2_followup_20261022/request_budget.json')
        followup['api_requests'] = budget.get('request_count', followup.get('api_requests'))
        followup['intermediate_attempt'] = read(ROOT/'data/gate2_followup_budget_20261022/summary.json')
        followup['initial_attempt'] = read(ROOT/'data/gate2_followup_20261022/summary.json')
    dataset_counts = load_dataset_counts(ROOT)
    sources.extend(dataset_counts['sources'])
    errors.extend(dataset_counts['read_errors'])
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'gates':gates,'s0_ablation':s0,
        'dataset_counts':dataset_counts, 'gate2_followup':followup,
        'rollouts':{'expected':live['expected_count'],'counts':live['counts'],'status':live['status']},
        'offline':offline,'t4_runs':runs,'historical_gate2':historical,
        'score_note':'五维各 0–10 原始整数；恢复无机会为 N/A。展示保留两位小数。五维均分只计五维均适用的轨迹；每项显示 n。配对差值仅用同 run、同场景、同模型且视频实际送达的完整配对。机器评分尚未经人工校准。',
        'sources':sources,'read_errors':errors}
