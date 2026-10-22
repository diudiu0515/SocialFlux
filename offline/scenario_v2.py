"""Author 50 scene-specific v2 sets from allowlisted public legacy materials."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import time

from environment.state_ontology import STATE_VARIABLE_ONTOLOGY
from offline.choice_builder import save, save_text, sha, write_bundle
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider
from offline.reuse_audit import digest
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from tasks.offline_choice import VERSION_V2, public_instance, validate_item
from tasks.offline_design import grouped_record

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tasks/examples/offline_scenarios_v2'
PROMPT=ROOT/'prompts/offline_scenario_author_v2.md'
FORMS=[['current_state','evidence_support'],['interval_change','state_combination'],['evidence_support','state_combination'],['current_state','interval_change']]


def jobs():
    bank=ROOT/'tasks/examples/offline_gpt50_t1_t3/items.jsonl'
    old=list(map(json.loads,bank.read_text().splitlines()))
    dev=list(map(json.loads,(ROOT/'tasks/examples/offline_t1_t3_dev60/items.jsonl').read_text().splitlines()))
    audit={r['instance_id']:r for r in json.loads((ROOT/'tasks/examples/offline_legacy_api_audit/results.json').read_text())['items']}
    by_scene=defaultdict(list)
    for x in old:by_scene[x['story_id']].append(x)
    result=[]
    for scene,items in sorted(by_scene.items()):
        ordinal=int(scene.split('_')[-1])-1
        for task in ('T1','T2','T3'):
            previous=[x for x in items if x['task']==task]
            if task=='T2':previous=[x for x in dev if x['story_id']==scene and x['task']=='T2']
            source_item=(previous or items)[0]
            inp=deepcopy(source_item['input'])
            for action in inp.get('candidate_actions',[]):action['label']='行动 '+action['action_id'].split('_')[-1]
            source=deepcopy(source_item['authoring']['construction_source'])
            for kind in ('scenario','trajectory','replay'):
                if source.get(kind+'_path') and sha(ROOT/source[kind+'_path'])!=source[kind+'_sha256']:raise ValueError('source hash mismatch '+scene)
            payload={'scene':scene,'task':task,'public_input':inp,
                'paired_input':task=='T2' and 'history_a' in inp,
                'suggested_forms':FORMS[ordinal%4] if task=='T1' else (['history_comparison','expression_meaning'] if ordinal%2==0 else ['joint_comparison','history_evidence']) if task=='T2' else ['action_selection','consequence_explanation'],
                'suggested_second_horizon':['immediate','delayed','immediate_delayed'][ordinal%3] if task=='T3' else None,
                'ontology':{k:v['definition'] for k,v in STATE_VARIABLE_ONTOLOGY.items()},
                'old_questions':[{'instance_id':x['instance_id'],'question':x['question'],'options':x['options'],
                    'machine_issues':audit.get(x['instance_id'],{}).get('review',{}).get('issues',[])} for x in previous]}
            # Sources / private state / futures remain local and are never payload fields.
            result.append({'job_id':scene+'-'+task,'scene':scene,'task':task,'ordinal':ordinal,'payload':payload,
                           'source':source,'source_item':source_item,'previous_ids':[x['instance_id'] for x in previous],
                           'source_bank_sha256':sha(bank if not(task=='T2' and previous) else ROOT/'tasks/examples/offline_t1_t3_dev60/items.jsonl')})
    return result


def t2_input(job,raw):
    inp=deepcopy(job['payload']['public_input'])
    if job['payload']['paired_input']:return inp
    edit=raw['history_edit']
    if not all(isinstance(edit.get(k),str) and edit[k].strip() for k in ('factor','b_action','shared_response','rationale')):raise ValueError('missing T2 controlled edit')
    history=inp.pop('history')
    if edit['b_action']==history[-1]['evaluated_agent']:raise ValueError('T2 needs a real historical difference')
    for side in ('a','b'):
        turns=deepcopy(history)
        for t in turns:t['turn_id']=side.upper()+':'+t['turn_id']
        turns[-1].update(environment_character='（共同回应见 ending）',observable_expression={})
        if side=='b':turns[-1]['evaluated_agent']=edit['b_action']
        inp['history_'+side]=turns
    inp['shared_ending']={'turn_id':'ending','current_response':edit['shared_response'],'observable_expression':edit['shared_expression']}
    return inp


def branch_evidence(job):
    source=job['source'];path=source.get('replay_path')
    if not path:return {'status':'needs_branch_evidence','observed_responses':0,'common_initial_context':'shared t2 prefix','shared_external_conditions':True,'branch_ids':['action_1','action_2']}
    branches=json.loads((ROOT/path).read_text())
    actions=job['payload']['public_input']['candidate_actions']
    if [b['candidate_action']['text'] for b in branches]!=[a['text'] for a in actions]:raise ValueError('branch actions mismatch')
    if len({b['snapshot_sha256'] for b in branches})!=1 or len({b['external_event_plan_hash'] for b in branches})!=1:raise ValueError('branch controls mismatch')
    # Single-interaction sources legitimately have no scheduled external event.
    # Two null hashes alone do not establish control; check the frozen conditions.
    controls=[]
    for branch in branches:
        snapshot=branch['future_turns'][0]['environment_snapshot_before']
        controls.append({k:deepcopy(snapshot[k]) for k in (
            'elapsed_time','time_unit','current_segment','public_timeline','event_plan')})
    if len({digest(c) for c in controls})!=1:
        raise ValueError('frozen external conditions mismatch')
    # The retained factual trajectory may predate the branch-lock flag. For this
    # no-event window verify actual external timelines, rather than invent a lock.
    if controls[0]['event_plan']['selection']=='none':
        for branch in branches:
            if branch['crossed_event_nodes'] or branch['elapsed_time_end']!=branch['elapsed_time_start']:
                raise ValueError('unexpected external event or elapsed-time transition')
            for turn in branch['future_turns']:
                for key in ('environment_snapshot_before','environment_snapshot_after'):
                    if key not in turn:continue
                    snap=turn[key]
                    if any(snap[k]!=controls[0][k] for k in ('elapsed_time','time_unit','public_timeline','event_plan')):
                        raise ValueError('external timeline changed within no-event window')
    observed=min(b['actual_turns_observed'] for b in branches)
    return {'status':'validated' if observed>=5 else 'needs_branch_evidence','observed_responses':observed,
        'common_initial_context':branches[0]['snapshot_sha256'],'shared_external_conditions':True,
        'branch_ids':[a['action_id'] for a in actions],'external_event_plan_hash':branches[0]['external_event_plan_hash'],
        'external_conditions_sha256':digest(controls[0]),'external_plan_mode':controls[0]['event_plan']['selection'],
        'source_branch_lock_flags':[b['future_turns'][0]['environment_snapshot_before']['counterfactual_timeline_lock'] for b in branches],
        'note':'既有受控回放，仅制作侧使用；分支结果不等于必然规律或人工答案。'}


def assemble(job,raw,artifact):
    if len(raw['questions'])!=2:raise ValueError('need exactly two questions')
    task=job['task'];inp=t2_input(job,raw) if task=='T2' else deepcopy(job['payload']['public_input'])
    if task=='T3' and [q['subtype'] for q in raw['questions']]!=['action_selection','consequence_explanation']:raise ValueError('T3 must cover both forms')
    if len({q['question'] for q in raw['questions']})!=2:raise ValueError('duplicate question')
    output=[]
    for n,q in enumerate(raw['questions']):
        if q.get('state_owner',inp['target_character']['character_id'])!=inp['target_character']['character_id'] or q.get('state_target',inp['role']['character_id'])!=inp['role']['character_id']:raise ValueError('state_owner/state_target must identify the environment character judging the action role')
        if list(q['options'])!=list('ABCD'):raise ValueError('four ordered options required')
        if not set(q.get('based_on',[]))<=set(job['previous_ids']):raise ValueError('unknown previous item')
        spec={k:deepcopy(q[k]) for k in ('target_state_ids','time_scope','risk_event','risk_window','comparison_interval','horizon','comparison','goal') if k in q}
        spec.update(state_owner=inp['target_character']['character_id'],state_target=inp['role']['character_id'],checkpoint='ending' if task=='T2' else 't2')
        if task=='T3':
            if q['subtype']=='action_selection' and 'horizon' not in spec and any(t in spec['time_scope'] for t in ('下一次','随后一次','即时')):
                spec['horizon']='immediate'
                spec['time_scope']=spec['time_scope'].replace('下一次环境回应前','行动及下一次环境回应后')
            spec.update(delayed_horizon=5,immediate_anchor='next_environment_response')
        author={k:deepcopy(q[k]) for k in ('answer','evidence_ids','rationale','option_errors','option_variable_map')}
        author['counterevidence_ids']=deepcopy(q.get('counterevidence_ids',[]))
        author.update(review_status='pending_human_review',review_protocol='human_annotation' if task=='T3' else 'human_verification',
            construction_source=deepcopy(job['source']),replay_status='not_required',
            generation_source={'kind':raw.get('_author_kind','api_authored_public_sources'),'path':str(artifact.relative_to(ROOT)),'prompt_sha256':sha(PROMPT),'result_sha256':digest(raw)},
            review_notes='按新版重新编配；旧题与 API 参考均不作为人工批准。',
            source_admission={'formal_admitted':False,'reason':'pending_source_and_human_review'},history_dependence='required',nonverbal_history_relation='context_dependent')
        if raw.get('_curation'):
            author['generation_source']['curation']=deepcopy(raw['_curation'])
        if task=='T2':
            edits=[]
            for a,b in zip(inp['history_a'],inp['history_b']):
                for k in sorted((a.keys()|b.keys())-{'turn_id'}):
                    if a.get(k)!=b.get(k):edits.append({'a_id':a['turn_id'],'b_id':b['turn_id'],'field':k,'before':a.get(k),'after':b.get(k)})
            existing=job['payload']['paired_input']
            state_check={'status':'source_replay_available_pending_item_review','path':job['source'].get('replay_path'),'sha256':job['source'].get('replay_sha256')} if existing else {'status':'needs_controlled_state_replay','reason':'新编辑未执行状态更新；结构检查与公开证据审核不替代状态回放。'}
            author['history_control']={'factor':raw.get('history_edit',{}).get('factor','已存在的受控互动方式差异') if raw.get('history_edit') else '已存在的受控互动方式差异',
                'shared_external_conditions':True,'shared_expression':'single_shared_ending','edits':edits,'state_check':state_check}
            author['replay_status']='validated' if existing and job['source_item']['authoring']['replay_status']=='validated' else 'pending'
            if not existing:
                author['construction_source'].update(origin='controlled_history_edit_from_existing_public_rollout',original_public_input=deepcopy(job['payload']['public_input']),
                    history_edit=deepcopy(raw['history_edit']))
        elif task=='T3':
            author['branch_evidence']=branch_evidence(job);author['replay_status']='validated' if author['branch_evidence']['status']=='validated' else 'pending'
        analysis={k:deepcopy(q[k]) for k in ('primary_capability','design_difficulty')}
        analysis.update(auxiliary_capabilities=deepcopy(q.get('auxiliary_capabilities',[])),difficulty_reason=q.get('difficulty_reason',''))
        analysis.update(empirical_difficulty=None,state_bindings=[])
        for p in spec['target_state_ids']:
            b={'state_id':p,'owner':spec['state_owner'],'object':spec['state_target']}
            if p.startswith('consequence_risk.'):b.update(risk_event=spec.get('risk_event'),risk_window=spec.get('risk_window'))
            analysis['state_bindings'].append(b)
        item={'instance_id':f"SFV2-{job['ordinal']+1:03d}-{task}-{n+1:02d}",'benchmark_version':VERSION_V2,'task':task,'subtype':q['subtype'],
            'story_id':job['scene'],'pair_id':job['scene']+':v2:history' if task=='T2' else None,'modality':'text','input':deepcopy(inp),
            'question':q['question'],'options':deepcopy(q['options']),'target_spec':spec,'ground_truth':None,'label_status':'pending_human_annotation','analysis':analysis,'authoring':author,
            'metadata':{'source_trajectory_id':job['source']['trajectory_id'],'previous_instance_ids':q.get('based_on',[]),'source_bank_sha256':job['source_bank_sha256'],
                'replacement_scope':job['previous_ids']}}
        letters=list('ABCD');desired=(job['ordinal']*2+n)%4;shift=(desired-letters.index(author['answer']))%4
        mapping={k:letters[(i+shift)%4] for i,k in enumerate(letters)}
        for obj,key in ((item,'options'),(author,'option_errors'),(author,'option_variable_map')):obj[key]=dict(sorted((mapping[k],v) for k,v in obj[key].items()))
        author['answer']=mapping[author['answer']]
        validate_item(item);output.append(item)
    return output


def generate(job,run,config,timeout):
    artifact=run/'authored'/(job['job_id']+'.json')
    binding=digest({'payload':job['payload'],'prompt_sha256':sha(PROMPT),'provider':public_provider_config(config)})
    if artifact.exists():
        cached=json.loads(artifact.read_text())
        manual_binding='assistant-curation:'+digest(job['payload'])
        if cached['binding']!=binding and not (
            cached['binding']==manual_binding and cached['result'].get('_author_kind')=='assistant_curated_public_sources'
        ):raise ValueError('author cache mismatch')
        return assemble(job,cached['result'],artifact)
    calls=run/'calls'/job['job_id'];provider=OfflineLoggedProvider(OfflineSamplingProvider(build_provider({**config,'timeout':timeout})),calls)
    messages=[{'role':'system','content':PROMPT.read_text()},{'role':'user','content':json.dumps(job['payload'],ensure_ascii=False)}]
    for attempt in range(2):
        if len(list(calls.glob('*.json')))>=3:raise RuntimeError('bounded author retries exhausted')
        text=provider.complete(messages,temperature=0.2,max_tokens=6500)
        try:
            raw=json.loads(text);items=assemble(job,raw,artifact)
        except (ValueError,KeyError,TypeError) as exc:
            save(run/'invalid'/(job['job_id']+'-'+str(time.time_ns())+'.json'),{'output':text,'error':str(exc)})
            if attempt:raise
            messages.append({'role':'user','content':'请修正完整 JSON，仍输出两题。结构错误：'+str(exc)});continue
        save(artifact,{'binding':binding,'result':raw,'provider':public_provider_config(config)})
        return items


def export(run,all_jobs):
    items=[];pending=[]
    for job in all_jobs:
        path=run/'revised'/(job['job_id']+'.json')
        if not path.exists():path=run/'authored'/(job['job_id']+'.json')
        if path.exists():items.extend(assemble(job,json.loads(path.read_text())['result'],path))
        else:pending.append(job['job_id'])
    reviewed=0;flagged=[]
    for item in items:
        review_path=run/'blind_review'/(item['story_id']+'.json')
        if not review_path.exists():continue
        record=json.loads(review_path.read_text())
        row=next((r for r in record['result']['answers'] if r['instance_id']==item['instance_id'] and r['public_sha256']==digest(public_instance(item))),None)
        if row:
            reviewed+=1;row=deepcopy(row);row['author_agreement']=row['answer']==item['authoring']['answer']
            item['authoring']['api_screening']={**row,'reviewer_type':record['reviewer_type'],'model':record['provider']['model']}
            if row['issues'] or not row['author_agreement'] or len(row['plausible_answers'])!=1:flagged.append(item['instance_id'])
            if item['task']=='T2':item['authoring']['history_control']['public_evidence_check']={'path':str(review_path.relative_to(ROOT)),'status':'has_machine_concerns' if item['instance_id'] in flagged else 'blind_answer_consistent','note':'公开证据核验；不替代状态回放或人工核验。'}
    manifest=write_bundle(items,OUT)
    manifest.update(format=VERSION_V2,expected_items=300,requested_scenarios=50,complete=not pending,pending_jobs=pending,
        primary_capabilities=dict(Counter(x['analysis']['primary_capability'] for x in items)),design_difficulties=dict(Counter(x['analysis']['design_difficulty'] for x in items)),
        generation_source={'run':str(run.relative_to(ROOT)),'prompt_sha256':sha(PROMPT)},blind_reviewed_items=reviewed,machine_flagged_ids=flagged,
        scene_coverage=[{'scenario_id':f'GPT50_{i:03d}','tasks':dict(Counter(x['task'] for x in items if x['story_id']==f'GPT50_{i:03d}')),
                        'total':sum(x['story_id']==f'GPT50_{i:03d}' for x in items)} for i in range(1,51)])
    save(OUT/'manifest.json',manifest)
    save_text(OUT/'records.jsonl',''.join(json.dumps(grouped_record(x),ensure_ascii=False)+'\n' for x in items))
    save(run/'progress.json',manifest)
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='data/offline_scenarios_v2_20261020_main');p.add_argument('--workers',type=int,default=12);p.add_argument('--timeout',type=int,default=180);p.add_argument('--limit',type=int);p.add_argument('--failed-only',action='store_true');p.add_argument('--export-only',action='store_true');args=p.parse_args()
    run=(ROOT/args.run).resolve();run.mkdir(parents=True,exist_ok=True);all_jobs=jobs()
    config=ModelRoutes.load(ROOT/'configs/gpt50_experiment/model_routes.hybrid.v3_2.json').provider_config('quality_review');config.update(timeout=180,max_transport_attempts=1,retry_backoff_seconds=0)
    save(run/'manifest.json',{'provider':public_provider_config(config),'prompt_sha256':sha(PROMPT),'jobs':len(all_jobs),'scope':'synthetic public inputs and previous public questions only; no private state or future branches'})
    if not args.export_only:
        selected=all_jobs[:args.limit] if args.limit else all_jobs
        if args.failed_only:
            def retryable(j):
                if (run/'authored'/(j['job_id']+'.json')).exists():return False
                records=[json.loads(p.read_text()) for p in (run/'calls'/j['job_id']).glob('*.json')]
                return bool(records) and not any(r['status']=='running' for r in records) and len(records)<3
            selected=[j for j in selected if retryable(j)]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(generate,j,run,config,args.timeout):j for j in selected}
            for f in as_completed(futures):
                job=futures[f]
                try:f.result();print('completed',job['job_id'],flush=True)
                except Exception as e:save(run/'failures'/(job['job_id']+'-'+str(time.time_ns())+'.json'),{'type':type(e).__name__,'message':str(e)});print('failed',job['job_id'],type(e).__name__,str(e)[:180],flush=True)
                export(run,all_jobs)
    m=export(run,all_jobs);print(json.dumps({k:m[k] for k in ('item_count','scenario_count','tasks','pending_jobs')},ensure_ascii=False))


if __name__=='__main__':main()
