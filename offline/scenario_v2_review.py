"""Blind public-only check of new scene sets; never promote machine labels."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import json
from pathlib import Path
import time

from offline.choice_builder import save
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider
from offline.reuse_audit import digest
from offline.scenario_v2 import ROOT, assemble, jobs
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from tasks.offline_choice import public_instance

PROMPT='''你盲试答SocialFlux新版社会理解题，未提供作者答案。依据每题指定的公开历史和候选行动独立判断，不把其他题选项当事实。每题状态主体均为材料中的target_character，关系方向指向role。T1只判断截至t2的现状或t1到t2变化；T2比较同一共同表达的A/B具体前史，部分状态可相近；T3根据行动机制做有依据的概率预测，不需要已经看到未来。已有材料支持的内在状态可以推断；不强求数值状态。基本不变需持续性证据，不能等同证据不足。不要把合作当信任、表情当状态、承诺当履约。请只返回JSON：{"answers":[{"instance_id":"...","answer":"A","plausible_answers":["A"],"issues":[],"reason":"50字内"}]}。每题一次，plausible_answers列出所有实质难以区分的最佳候选。issues仅记实际问题：subject_mismatch（题干主体反向）、ambiguous（无唯一可辩护答案）、unsupported（正确判断依赖未给出的事实）、history_independent（T2只看共同表达即可选对）、wrong_form（如证据题选项实际都是状态判断）、time_scope（比较对象/风险时间不清）、option_cue（正确项明显更长谨慎、错项极端）。没有实质问题则空，不为挑错强造问题。'''


def payload(items):
    shared={};questions=[]
    for x in items:
        p=public_instance(x)
        if x['task'] in shared and shared[x['task']]!=p['input']:raise ValueError('task input drift')
        shared[x['task']]=p['input']
        questions.append({'instance_id':x['instance_id'],'task':x['task'],'question':p['question'],'options':p['options']})
    return {'shared_inputs':shared,'questions':questions}


def review(scene,items,run,config):
    public=payload(items);binding=digest(public);path=run/'blind_review'/(scene+'.json')
    if path.exists():
        x=json.loads(path.read_text())
        if x['binding']==binding and {r['instance_id'] for r in x['result']['answers']}=={i['instance_id'] for i in items}:return x
    provider=OfflineLoggedProvider(OfflineSamplingProvider(build_provider(config)),run/'review_calls'/scene)
    messages=[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(public,ensure_ascii=False)}]
    for attempt in range(2):
        try:
            raw=provider.complete(messages,temperature=0,max_tokens=3000)
            data=json.loads(raw);rows=data['answers'];index={r['instance_id']:r for r in rows}
            if len(rows)!=len(index) or set(index)!={x['instance_id'] for x in items}:raise ValueError('review IDs missing')
            for x in items:
                r=index[x['instance_id']]
                if r['answer'] not in x['options'] or not set(r['plausible_answers'])<=x['options'].keys() or r['answer'] not in r['plausible_answers']:raise ValueError('review answer invalid')
                if not isinstance(r['issues'],list):raise ValueError('review issues invalid')
                r.update(public_sha256=digest(public_instance(x)),author_answer_at_review=x['authoring']['answer'],author_agreement=r['answer']==x['authoring']['answer'])
            record={'binding':binding,'result':data,'reviewer_type':'blind_model_screen_not_human','provider':public_provider_config(config)}
            if path.exists():
                previous=json.loads(path.read_text())
                if previous['binding']!=binding:
                    save(run/'review_history'/(scene+'-'+previous['binding']+'.json'),previous)
            save(path,record);return record
        except Exception as e:
            save(run/'review_failures'/(scene+'-'+str(time.time_ns())+'.json'),{'type':type(e).__name__,'message':str(e)})
            if attempt:raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='data/offline_scenarios_v2_20261020_main');p.add_argument('--follow',action='store_true');p.add_argument('--workers',type=int,default=6);p.add_argument('--refresh-items',action='store_true');args=p.parse_args()
    run=ROOT/args.run;groups=defaultdict(list)
    for j in jobs():groups[j['scene']].append(j)
    config=ModelRoutes.load(ROOT/'configs/gpt50_experiment/model_routes.hybrid.v3_2.json').provider_config('quality_review');config.update(timeout=100,max_transport_attempts=1,retry_backoff_seconds=0)
    if args.refresh_items:
        return refresh_items(groups,run,config,args.workers)
    submitted=set();active={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while True:
            for scene,js in groups.items():
                paths=[run/('revised' if (run/'revised'/(j['job_id']+'.json')).exists() else 'authored')/(j['job_id']+'.json') for j in js]
                if scene in submitted or not all(p.exists() for p in paths):continue
                items=[x for j,path in zip(js,paths) for x in assemble(j,json.loads(path.read_text())['result'],path)]
                active[pool.submit(review,scene,items,run,config)]=scene;submitted.add(scene)
            for future,scene in list(active.items()):
                if not future.done():continue
                try:future.result();print('reviewed',scene,flush=True)
                except Exception as e:print('review failed',scene,type(e).__name__,flush=True)
                del active[future]
            if not active and (len(submitted)==50 or not args.follow or (run/'author_complete.json').exists()):break
            time.sleep(3)
    print('reviewed/submitted scenes',len(submitted),flush=True)


def refresh_items(groups,run,config,workers):
    """Retain exact-content checks; retry only changed or missing items individually."""
    scene_items={};rows={};pending=[]
    for scene,js in groups.items():
        items=[]
        for j in js:
            path=run/'revised'/(j['job_id']+'.json')
            if not path.exists():path=run/'authored'/(j['job_id']+'.json')
            items.extend(assemble(j,json.loads(path.read_text())['result'],path))
        scene_items[scene]=items
        path=run/'blind_review'/(scene+'.json')
        old=json.loads(path.read_text()) if path.exists() else None
        rows[scene]={}
        for item in items:
            row=next((r for r in (old or {}).get('result',{}).get('answers',[])
                if r['instance_id']==item['instance_id'] and r['public_sha256']==digest(public_instance(item))),None)
            if row:rows[scene][item['instance_id']]=row
            else:pending.append((scene,item))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        from concurrent.futures import as_completed
        active={pool.submit(review,x['instance_id'],[x],run/'individual',config):(scene,x) for scene,x in pending}
        for f in as_completed(active):
            scene,item=active[f]
            try:
                record=f.result();rows[scene][item['instance_id']]=record['result']['answers'][0]
                print('checked',item['instance_id'],flush=True)
            except Exception as e:print('item check pending',item['instance_id'],type(e).__name__,flush=True)
    for scene,items in scene_items.items():
        path=run/'blind_review'/(scene+'.json')
        if path.exists():
            old=json.loads(path.read_text())
            save(run/'review_history'/(scene+'-'+digest(old)+'.json'),old)
        save(path,{'binding':digest(payload(items)),'result':{'answers':[rows[scene][x['instance_id']] for x in items if x['instance_id'] in rows[scene]]},
            'reviewer_type':'blind_model_screen_not_human','provider':public_provider_config(config),
            'composition_mode':'exact_public_content_retained_or_individually_refreshed','individual_artifacts':str((run/'individual').relative_to(ROOT)),
            'missing_ids':[x['instance_id'] for x in items if x['instance_id'] not in rows[scene]]})
    print('individual items attempted',len(pending),flush=True)


if __name__=='__main__':main()
