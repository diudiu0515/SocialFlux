"""Independent answer-hidden check of additions and substantive T2 rewrites."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import OUT,load,save,provider_for,digest
from offline.provider_compat import OfflineLoggedProvider
from providers.structured import complete_json

PROMPT='''Independently audit newly authored English social-reasoning questions. Author answers are withheld. Use only the public input to solve; private records are for checking compatibility, never a reason to expect participants to know hidden events. Return JSON {"reviews":[{"instance_id":"...","answer":"A","plausible_answers":["A"],"issues":[],"reason":"...","difficulty_supported":true}]}. Issues may include state_conflict, private_only, future_leakage, wrong_subject, risk_event_mismatch, ambiguous, duplicate, option_cue, difficulty_mismatch. Read numeric state_before/state_after literally: equal values do not support a decrease/increase, and equal branch values do not support an ordering. Distinguish an absolute change from comparison between actions. An action's public mechanism may support a prediction, but unseen quoted future responses cannot be presupposed. A single branch is not a population probability. For risk, the named event and window must match the measured variable and question. Verify the required design difficulty arises from real conflicting/distributed evidence or a state/temporal tradeoff. Examine every option including hidden facts in distractors. Compare against existing questions to identify mere paraphrases. All prose in your answer must be English.'''

def evidence(item):
    p=load(ROOT/item['authoring']['oracle_reference']['packet_path'])
    selected=set(item['target_spec']['target_state_ids'])
    def turn(t):return {k:({s:v for s,v in value.items() if s in selected} if k in ('state_before','state_after') else value) for k,value in t.items() if k in ('evidence_id','action','response','state_before','state_after')}
    q={'initial_state':{s:v for s,v in p['initial_state'].items() if s in selected},'prefix':[turn(t) for t in p['prefix']]}
    if 'replays' in p:q['replays']={k:turn(v) for k,v in p['replays'].items()}
    if 'branches' in p:q['branches']=[{'action_id':b['action_id'],'turns':[turn(t) for t in (b['turns'][:1] if item['target_spec'].get('horizon')=='immediate' else b['turns'])]} for b in p['branches']]
    return q

def run(scene,index=0):
    folder=OUT/'scenes'/scene;rows=load(folder/'items.json');plan=load(OUT/'plan.json')
    selected=[x for x in rows if x['instance_id'].startswith('SFA400') or x['instance_id'] in plan['t2_rewrites']]
    payload={'questions':[{**{k:x[k] for k in ('instance_id','task','subtype','question','options','input','target_spec')},'design_difficulty':x['analysis']['design_difficulty'],'private_evidence':evidence(x)} for x in selected],
             'existing_questions':[{k:x[k] for k in ('instance_id','task','question','options')} for x in rows if x not in selected]}
    h=digest(payload);artifact=folder/'independent_review.json'
    if artifact.exists() and load(artifact)['input_sha256']==h:return load(artifact)
    provider=OfflineLoggedProvider(provider_for(index),folder/'independent-review-calls')
    def check(v):
        if {x['instance_id'] for x in v.get('reviews',[])}!={x['instance_id'] for x in selected}:raise ValueError('Review IDs mismatch')
        for x in v['reviews']:
            if x['answer'] not in 'ABCD' or not x['reason'] or not isinstance(x['issues'],list) or not isinstance(x['difficulty_supported'],bool):raise ValueError('Malformed review')
        return v
    result=complete_json(provider,[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],{'temperature':0,'max_tokens':12000},check,context='annotation400 independent audit',max_attempts=2)
    result.update(input_sha256=h,author_answers_withheld=True,human_review='pending')
    save(artifact,result)
    print(json.dumps({'scene':scene,'issues':{r['instance_id']:r['issues'] for r in result['reviews'] if r['issues']}}),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scenes',nargs='*');p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    scenes=a.scenes or sorted(p.parent.name for p in (OUT/'scenes').glob('*/items.json'))
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        fs=[pool.submit(run,s,i) for i,s in enumerate(scenes)]
        for f in as_completed(fs):
            try:f.result()
            except Exception as e:print(json.dumps({'review_error':str(e),'error_type':type(e).__name__}),flush=True)
