"""Development-set checks and source-boundary diagnostics; not human approval."""
from collections import Counter
import json
from pathlib import Path
from offline.choice_builder import load, sha, save
from tasks.offline_choice import validate_item, public_instance, FAMILIES


def audit_bundle(items, output):
    ids=[x['instance_id'] for x in items]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate item IDs')
    rows=[]
    for item in items:
        validate_item(item)
        source=item['authoring']['construction_source']
        for kind in ('trajectory','scenario'):
            if sha(source[kind+'_path'])!=source[kind+'_sha256']:
                raise ValueError('source artifact changed: '+item['instance_id'])
        if item['story_id']!=source['scenario_id'] or item['metadata']['source_trajectory_id']!=source['trajectory_id']:
            raise ValueError('source identity mismatch')
        answer=item['authoring']['answer'];judgments=item['authoring']['option_variable_map'][answer]
        lengths=[len(v) for v in item['options'].values()]
        rows.append({'instance_id':item['instance_id'],
                     'clear_actor_and_time':'present_structurally',
                     'visible_evidence':'IDs_valid_semantic_review_pending',
                     'answer_separability':'adjacent_answers_accepted' if item['authoring'].get('acceptable_answers') else 'author_proposal_pending_human_review',
                     'analysis_fields':'complete',
                     'insufficient_evidence_components':[k for k,v in judgments.items() if v=='cannot_determine'],
                     'option_length_ratio':round(max(lengths)/min(lengths),2),
                     'assistant_editorial_revision':bool(item['authoring'].get('editorial_review')),
                     'replay_status':item['authoring']['replay_status']})
    report={'items':len(items),'tasks':dict(Counter(i['task'] for i in items)),
            'state_coverage':{task:sorted({FAMILIES[p.split('.')[0]] for i in items if i['task']==task for p in i['target_spec']['target_state_ids']}) for task in ('T1','T2','T3')},
            'combination_count':sum(len(next(iter(i['authoring']['option_variable_map'].values())))>1 for i in items),
            'insufficient_answer_components_by_task':dict(Counter(i['task'] for i,r in zip(items,rows) if r['insufficient_evidence_components'])),
            'option_error_types_in_bank':dict(Counter(v for i in items for v in i['authoring']['option_errors'].values())),
            'accepted_neighbor_items':[i['instance_id'] for i in items if i['authoring'].get('acceptable_answers')],
            'formal_admitted':0,'human_approval':False,'rows':rows}
    save(Path(output)/'development_audit.json',report)
    files=['tasks/offline_choice.py','evaluation/offline_choice.py','offline/choice_builder.py','offline/choice_media.py',
           'offline/choice_audit.py','offline/choice_pipeline.py','offline/choice_batch.py','offline/factual_reference.py','offline/provider_compat.py','scripts/build_offline_choice_dev.py','scripts/evaluate_offline_choice.py',
           'rollout/counterfactual.py','pipeline/cli.py','prompts/offline_choice_author_v1.md','prompts/offline_choice_answer_v1.md']
    save(Path(output)/'implementation_manifest.json',{'files':{f:sha(f) for f in files}})
    state_reference_crosscheck(items,output)
    return report


def state_reference_crosscheck(items, output):
    """Compare proposals with private machine states without treating them as GT."""
    from environment.delta_mapper import flatten_state
    trajectories, replays = {}, {}
    rows=[]
    for item in items:
        source=item['authoring']['construction_source'];task=item['task'];spec=item['target_spec']
        path=source['trajectory_path']
        if path not in trajectories:
            trajectory=load(path)
            trajectories[path]=[flatten_state(t.get('state_after_public_events',t['state_after'])) for t in trajectory['turns'][:2]]
        pair=trajectories[path]
        replay_path=source.get('replay_path')
        if task in {'T2','T3'}:
            if not replay_path:
                rows.append({'instance_id':item['instance_id'],'status':'replay_pending'});continue
            if replay_path not in replays:replays[replay_path]=load(replay_path)
        comparisons=[]
        for coordinate,judgment in item['authoring']['option_variable_map'][item['authoring']['answer']].items():
            variable=coordinate.split('@')[0]
            if task=='T1':
                left,right=[x[variable] for x in pair];direction='time'
            elif task=='T2':
                left,right=[flatten_state(replays[replay_path][side]['state_after'])[variable] for side in ('a','b')];direction='history'
            else:
                by_action=dict(zip([a['action_id'] for a in item['input']['candidate_actions']],replays[replay_path]))
                if item['subtype']=='action_comparison':
                    key='state_after_immediate_action_response' if spec['comparison_horizon']=='immediate' else 'state_after_delayed'
                    left,right=[flatten_state(by_action[a][key])[variable] for a in spec['comparison_actions']];direction='history'
                else:
                    branch=by_action[spec['action_id']]
                    key='state_after_immediate_action_response' if item['subtype']=='immediate_effect' or coordinate.endswith('@immediate') else 'state_after_delayed'
                    left=flatten_state(branch['state_before'])[variable];right=flatten_state(branch[key])[variable];direction='time'
            delta=right-left
            opposite=(judgment=='increase' and direction=='time' and delta<0) or (judgment=='decrease' and direction=='time' and delta>0) or (judgment=='higher_in_a' and direction=='history' and delta>0) or (judgment=='higher_in_b' and direction=='history' and delta<0)
            comparisons.append({'coordinate':coordinate,'author_judgment':judgment,'machine_values':[left,right],
                                'opposite_direction':opposite,'machine_changed_despite_similar':judgment=='similar' and delta!=0})
        rows.append({'instance_id':item['instance_id'],'status':'machine_reference_only','comparisons':comparisons})
    result={'status':'not_human_ground_truth','items_sha256':sha(Path(output)/'items.jsonl'),'rows':rows}
    save(Path(output)/'state_reference_crosscheck.json',result)
    return result
