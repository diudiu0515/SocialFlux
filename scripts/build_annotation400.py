"""Freeze and author the English GPT50 annotation release; never promote human GT.

Resumable bounded calls reuse translation caches without modifying the concurrent
English migration or the old question bank. All additions use existing evidence.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.localization import CJK, atomic_json, digest, strings
from scripts.localize_current_data import provider_for, PROMPT as TRANSLATE, translate_tree, same_structure
from offline.provider_compat import OfflineLoggedProvider
from providers.structured import complete_json
from tasks.offline_choice import validate_item, public_instance, ERROR_TYPES, visible_evidence
from tasks.offline_design import grouped_record
from web.offline_review import item_digest, bound_video_materials

OUT = ROOT / 'data/offline_annotation400_en_20261022'
QUOTAS = {'T1': {'ordinary': 90, 'hard': 60}, 'T2': {'ordinary': 60, 'hard': 40}, 'T3': {'ordinary': 90, 'hard': 60}}

def addition_positions():
    ids=[f'SFA400-{i:03}-{task}-03' for i in range(1,51) for task in ('T1','T3')]
    ids.sort(key=lambda s:hashlib.sha256(('annotation400-en-20261022-v1:'+s).encode()).hexdigest())
    return {ident:'ABCD'[index%4] for index,ident in enumerate(ids)}

def option_references(text,mapping,task):
    # T2's bare A/B refer to histories. For T1/T3 they refer to answer
    # choices; exclude the indefinite article A followed by a noun phrase.
    if task!='T2':
        return re.sub(r'\b([ABCD])\b(?=\s+(?:is|also|instead|correctly|wrongly|overlooks|overstates|overreads|misreads|describes|captures|treats|retains|supports|incorrectly)\b|[,:.]|\s+(?:because|without)\b)',
                      lambda m:mapping[m[1]],text)
    return re.sub(r'(?i)(\b(?:option|choice|answer|competitor)\s+(?:is\s+)?)([ABCD])\b',
                  lambda m:m[1]+mapping[m[2].upper()],text)

def load(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, x): atomic_json(Path(p), x)
def jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))

def freeze():
    if (OUT / 'source.items.jsonl').exists(): return
    path = ROOT / 'tasks/examples/offline_scenarios_v2/items.jsonl'
    source_bank_sha = sha(path)
    rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    assert len(rows) == 300 and len({x['story_id'] for x in rows}) == 50
    bound = bound_video_materials(rows, 'scenarios-v2')
    save(OUT / 'source.media.json', bound)
    originals = deepcopy(rows)
    frozen = {}
    for x in rows:
        a = x['authoring']
        for obj, pkey, hkey in [(a['construction_source'], k + '_path', k + '_sha256') for k in ('scenario','trajectory','replay')] + [(a['oracle_reference'], 'packet_path', 'packet_sha256')]:
            if not obj.get(pkey): continue
            path = ROOT / obj[pkey]
            h = sha(path)
            if obj.get(hkey) and obj[hkey] != h: raise ValueError('Changed source: ' + str(path))
            dest = OUT / 'sources' / (h + '.json')
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(path.read_bytes())
            frozen[obj[pkey]] = str(dest.relative_to(ROOT))
            obj[pkey], obj[hkey] = str(dest.relative_to(ROOT)), h
    # Other replay pointers must refer to the same frozen evidence.
    def rebind(v):
        if isinstance(v, dict): return {k: rebind(x) for k,x in v.items()}
        if isinstance(v, list): return [rebind(x) for x in v]
        return frozen.get(v, v) if isinstance(v, str) else v
    rows = rebind(rows)
    jsonl(OUT / 'source.items.jsonl', rows)
    jsonl(OUT / 'original.items.jsonl', originals)
    # T3 adds 36 hard and 14 ordinary; distribute hard toward scenes lacking it.
    scenes = sorted({x['story_id'] for x in rows})
    t3_hard = sorted(scenes, key=lambda s: (sum(x['task']=='T3' and x['analysis']['design_difficulty']=='hard' for x in rows if x['story_id']==s), s))[:36]
    t2 = []
    for s in scenes:
        candidates = [x for x in rows if x['story_id']==s and x['task']=='T2' and x['analysis']['design_difficulty']=='ordinary']
        if candidates: t2.append(candidates[-1]['instance_id'])
        if len(t2)==4: break
    save(OUT / 'plan.json', {'release':'annotation400-en-20261022-v1', 'language':'en', 'source_bank_sha256':source_bank_sha, 'quotas':QUOTAS, 'per_scene':{'T1':3,'T2':2,'T3':3}, 't3_hard_scenes':t3_hard, 't2_rewrites':t2, 'source_map':frozen})

def translate(index, scene, value, name='translation'):
    directory = OUT / 'scenes' / scene
    cache_path = directory / 'translations.json'
    cache = load(cache_path) if cache_path.exists() else {}
    shared = ROOT / 'data/english_migration_20261022/scenes' / scene / 'cache.json'
    if shared.exists():
        for key,translation in load(shared).items():cache.setdefault(key,translation)
    for i in range(1,5): cache[digest(f'行动 {i}')] = f'Action {i}'
    needed = list(dict.fromkeys(s for s in strings(value) if CJK.search(s)))
    missing = [s for s in needed if digest(s) not in cache]
    provider = OfflineLoggedProvider(provider_for(index), directory / (name + '-calls'))
    while missing:
        chunk, length = [], 0
        while missing and len(chunk)<32 and (not chunk or length + len(missing[0]) < 5000):
            s=missing.pop(0); chunk.append(s); length+=len(s)
        def check(v):
            a=v.get('translations',[])
            if len(a)!=len(chunk):raise ValueError(f'Expected exactly {len(chunk)} translations, received {len(a)}; do not split a source string into multiple entries')
            if any(not isinstance(s,str) or not s.strip() or CJK.search(s) for s in a):raise ValueError('Every translation must be nonempty English without CJK characters')
            return v
        result=complete_json(provider,[{'role':'system','content':TRANSLATE},{'role':'user','content':json.dumps({'required_translation_count':len(chunk),'texts':chunk},ensure_ascii=False)}],{'temperature':0,'max_tokens':14000},check,context='annotation400 translation',max_attempts=3)
        cache.update({digest(a):b for a,b in zip(chunk,result['translations'])}); save(cache_path,cache)
    out=translate_tree(value,cache); same_structure(value,out)
    save(cache_path,cache)
    return out

AUTHOR = '''Author one English multiple-choice question for a synthetic social-reasoning annotation study, using the provided frozen public input and actual private evidence. The source may be Chinese; all your prose must be English. Do not change or invent any public material, shared ending, candidate action, event, or state observation. All answers remain machine proposals for human annotation.
The supplied original specifies the required ID, task, form, scope and desired design difficulty. Make this a SUBSTANTIVELY NEW question, distinct from existing_questions: test a different state judgment, evidence integration, or state tradeoff, not a paraphrase or a reordered answer. For a T2 rewrite, replace the ordinary item with real hard reasoning across controlled histories. Hard requires conflicting/distributed public evidence, distinguishing non-synchronous state dimensions, repair or temporal tradeoff; cite the specific tension in difficulty_reason. Ordinary requires direct, consistent evidence. Never simply relabel difficulty.
Use only allowed_state_paths. T1 state_combination needs exactly two recorded states, preferably different families including emotion if supported. T3 hard should distinguish two states or an action tradeoff, not assume all desirable states move together. For T3 ordinary choose a directly supported state/behavior prediction distinct from existing questions. Simulator scores are evidence, not population probabilities; a single branch cannot establish certainty. Never state a future response as already observed in an option. Derive the best answer from visible mechanisms; private records must be compatible. If public evidence cannot distinguish the proposed answer, rewrite it to a supportable judgment instead. Do not make insufficiency the routine answer. All four options should be plausible, similarly specific and similar in length, with one best answer.
Preserve checkpoint, state_owner, state_target, horizon, comparison, comparison_interval, delayed_horizon, immediate_anchor exactly as provided. You may change selected state paths, goal and risk event/window to fit the new question. Risk questions must explicitly state risk event and window in the English question. T3 must explicitly state the comparison and prediction window. Do not leak private numbers or future facts. T2 input has one identical shared ending.
Return JSON with fields: instance_id, subtype, question, options (A/B/C/D), target_spec (complete), answer, rationale (public reasoning), oracle_rationale (private evidence and strongest competing option), oracle_evidence_ids (from provided private evidence IDs), evidence_ids (from visible_evidence), counterevidence_ids, option_errors (exactly the three incorrect letters mapped to allowed_option_errors), option_variable_map (all four letters, each mapping every selected state path to an English judgment), changes, unresolved_issues (array), primary_capability (situational_evidence_integration, multidimensional_state_distinction, or temporal_dynamics_reasoning), auxiliary_capabilities (array; omit the primary), design_difficulty, difficulty_reason. Keep enum values and IDs unchanged. Never claim human approval.'''

def prepare_item(base, new_id, difficulty, task):
    x=deepcopy(base);x['instance_id']=new_id
    if task=='T1': x['subtype']='state_combination'; x['target_spec'].pop('comparison_interval',None)
    if task=='T3':
        x['subtype']='consequence_explanation';x['target_spec'].update(horizon='immediate',time_scope='After the action and the immediately following environment response.',comparison={'kind':'between_actions','action_ids':['action_1','action_2']})
    x['analysis']['design_difficulty']=difficulty
    x['metadata']['annotation400_parent_id']=base['instance_id']
    return x

def compact_packet(p, task):
    q=deepcopy(p)
    if task=='T3':
        for b in q['branches']: b['turns']=b['turns'][:1]
        q['evidence_ids']=[s for s in q['evidence_ids'] if ':step' not in s]
    q.pop('sources',None);q.pop('public_input',None)
    q['state_transition_table']={}
    for branch in q.get('branches',[]):
        t=branch['turns'][0]
        q['state_transition_table'][branch['action_id']]={k:{'before':v,'after':t['state_after'][k],'change':t['state_after'][k]-v} for k,v in t['state_before'].items() if k in t['state_after']}
    return q

def assemble(base, proposal, packet, artifact):
    from offline.oracle import patch_item
    x=deepcopy(base)
    if x['instance_id'].startswith('SFA400'):
        x['authoring']['answer']=addition_positions()[x['instance_id']]
    # New T1 combination questions may explicitly compare two already visible
    # checkpoints. This does not extend their public or private evidence window.
    interval=proposal.get('target_spec',{}).get('comparison_interval')
    if x['instance_id'].startswith('SFA400') and x['task']=='T1' and interval:
        order=[t['turn_id'] for t in x['input']['history']]
        start,end=(interval.get(k,'').split(':')[0] for k in ('start','end'))
        if start not in order or end!=x['target_spec']['checkpoint'] or order.index(start)>=order.index(end):
            raise ValueError('T1 interval must use ordered, visible checkpoints')
        x['target_spec']['comparison_interval']=deepcopy(interval)
    for k in ('primary_capability','auxiliary_capabilities','design_difficulty','difficulty_reason'): x['analysis'][k]=proposal[k]
    if proposal['design_difficulty']!=base['analysis']['design_difficulty']: raise ValueError('Difficulty quota changed')
    if CJK.search(json.dumps(proposal,ensure_ascii=False)): raise ValueError('Question must be fully English')
    result=patch_item(x,proposal,packet,artifact)
    letters='ABCD';shift=(letters.index(result['authoring']['answer'])-letters.index(proposal['answer']))%4
    mapping={letter:letters[(i+shift)%4] for i,letter in enumerate(letters)}
    result['authoring']['rationale']=option_references(result['authoring']['rationale'],mapping,x['task'])
    result['authoring']['oracle_reference']['rationale']=option_references(result['authoring']['oracle_reference']['rationale'],mapping,x['task'])
    result['authoring']['generation_source']['option_mapping']=mapping
    result['authoring']['generation_source']['prompt_sha256']=digest(AUTHOR)
    result['authoring']['generation_source']['kind']='annotation400_api_authored_existing_rollout_evidence'
    if proposal.get('_curation'):
        result['authoring']['generation_source']['kind']='annotation400_api_draft_with_documented_assistant_correction'
        result['authoring']['generation_source']['curation']=deepcopy(proposal['_curation'])
    return result

def author(index, scene, base, existing):
    folder=OUT/'scenes'/scene/base['instance_id']
    source=load(ROOT/base['authoring']['oracle_reference']['packet_path'])
    source['public_input']=deepcopy(base['input']); source['sources']=deepcopy(base['authoring']['construction_source'])
    save(folder/'evidence.json',source)
    artifact=folder/'result.json'
    if artifact.exists(): return assemble(base,load(artifact),source,artifact)
    payload={'original':{k:base[k] for k in ('instance_id','task','subtype','target_spec','analysis')},'public_input':base['input'],'private_evidence':compact_packet(source,base['task']),'allowed_state_paths':source['allowed_state_paths'],'visible_evidence':sorted(visible_evidence(base)),'allowed_option_errors':sorted(ERROR_TYPES),'existing_questions':[{k:x[k] for k in ('question','options','target_spec')} for x in existing]}
    backend=provider_for(index)
    backend.timeout=600
    for candidate in backend.candidates:candidate.timeout=600
    provider=OfflineLoggedProvider(backend,folder/'calls')
    def check(v): assemble(base,v,source,artifact);return v
    result=complete_json(provider,[{'role':'system','content':AUTHOR},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],{'temperature':0.2,'max_tokens':16000},check,context='annotation400 author',max_attempts=3)
    save(artifact,result)
    return assemble(base,result,source,artifact)

def scene_job(index,scene,rows,plan):
    folder=OUT/'scenes'/scene
    if (folder/'items.json').exists(): return load(folder/'items.json')
    translated=folder/'translated.items.json'
    items=load(translated) if translated.exists() else translate(index,scene,rows)
    for x in items: validate_item(x)
    save(translated,items)
    old=deepcopy(items)
    for task in ('T1','T3'):
        prior=[x for x in old if x['task']==task]
        base=prepare_item(prior[0],f"SFA400-{scene[-3:]}-{task}-03",'hard' if task=='T1' or scene in plan['t3_hard_scenes'] else 'ordinary',task)
        items.append(author(index,scene,base,prior))
    for i,x in enumerate(items[:6]):
        if x['instance_id'] in plan['t2_rewrites']:
            base=prepare_item(x,x['instance_id'],'hard','T2')
            items[i]=author(index,scene,base,[a for a in old if a['task']=='T2'])
    for x in items:
        x['metadata']['annotation_release']=plan['release'];x['metadata']['language']='en'
        x['metadata']['translation_status']='machine_translation_pending_human_review'
        validate_item(x)
        if CJK.search(json.dumps(public_instance(x),ensure_ascii=False)): raise ValueError('Public question contains CJK')
    items.sort(key=lambda x:(x['task'],x['instance_id']))
    save(folder/'items.json',items)
    print(json.dumps({'scene':scene,'status':'ready','items':len(items)}),flush=True)
    return items

def publish():
    plan=load(OUT/'plan.json');items=[]
    for i in range(1,51):
        scene=f'GPT50_{i:03}';folder=OUT/'scenes'/scene;rows=load(folder/'items.json');original=load(folder/'translated.items.json')
        for index,item in enumerate(rows):
            if not item['instance_id'].startswith('SFA400') and item['instance_id'] not in plan['t2_rewrites']:continue
            parent=next(x for x in original if x['task']==item['task']) if item['instance_id'].startswith('SFA400') else next(x for x in original if x['instance_id']==item['instance_id'])
            base=prepare_item(parent,item['instance_id'],item['analysis']['design_difficulty'],item['task'])
            artifact=folder/item['instance_id']/'result.json'
            revised=assemble(base,load(artifact),load(artifact.with_name('evidence.json')),artifact)
            revised['metadata'].update(item['metadata']);rows[index]=revised
        save(folder/'items.json',rows);items.extend(rows)
    counts=Counter((x['task'],x['analysis']['design_difficulty']) for x in items)
    assert counts==Counter({(t,d):n for t,q in QUOTAS.items() for d,n in q.items()}), counts
    assert len(items)==len({x['instance_id'] for x in items})==400
    assert Counter(x['authoring']['answer'] for x in items if x['instance_id'].startswith('SFA400'))==dict.fromkeys('ABCD',25)
    for scene in {x['story_id'] for x in items}: assert Counter(x['task'] for x in items if x['story_id']==scene)=={'T1':3,'T2':2,'T3':3}
    for x in items: validate_item(x)
    jsonl(OUT/'items.jsonl',items);jsonl(OUT/'public.jsonl',map(public_instance,items));jsonl(OUT/'records.jsonl',map(grouped_record,items))
    save(OUT/'manifest.json',{'release':plan['release'],'language':'en','items_sha256':sha(OUT/'items.jsonl'),'items':400,'scenes':50,'task_difficulty':QUOTAS,'per_scene':plan['per_scene'],'answer_positions':dict(Counter(x['authoring']['answer'] for x in items)),'formal_ground_truth':False,'label_status':'pending_human_annotation','source_bank_sha256':plan['source_bank_sha256']})
    print(json.dumps(load(OUT/'manifest.json')),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=6);p.add_argument('--scenes',nargs='*');p.add_argument('--exclude',nargs='*',default=[]);p.add_argument('--publish',action='store_true');p.add_argument('--freeze-only',action='store_true');a=p.parse_args()
    freeze()
    if a.freeze_only:return
    if a.publish:publish();return
    plan=load(OUT/'plan.json');rows=[json.loads(s) for s in (OUT/'source.items.jsonl').read_text().splitlines()]
    scenes=sorted({x['story_id'] for x in rows});errors=[]
    if a.scenes:scenes=[s for s in scenes if s in a.scenes]
    scenes=[s for s in scenes if s not in a.exclude]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs={pool.submit(scene_job,i,s,[x for x in rows if x['story_id']==s],plan):s for i,s in enumerate(scenes)}
        for f in as_completed(jobs):
            try:f.result()
            except Exception as e:
                row={'scene':jobs[f],'error':type(e).__name__,'message':str(e)[:800]};errors.append(row);print(json.dumps(row),flush=True)
    save(OUT/'errors.json',errors)
    if errors:raise SystemExit(1)
    if len(scenes)==50:publish()

if __name__=='__main__':main()
