"""Rewrite flagged new questions with frozen public inputs and retained drafts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import time

from offline.choice_builder import save,sha
from offline.provider_compat import OfflineLoggedProvider,OfflineSamplingProvider
from offline.reuse_audit import digest
from offline.scenario_v2 import ROOT,PROMPT,assemble,jobs
from providers.factory import build_provider,public_provider_config
from providers.model_routes import ModelRoutes

REVISION='''这是修订轮。下面的盲试答意见可能错，先依据公开证据判断，再重写有问题的题；不要机械改答案迎合意见。必须修复真正的歧义、错主体、泛化选项与过长正确项。保留两题、同一主体、同一材料和任务。T2的A/B历史和共同表达已冻结，不得重写；history_edit仍原样返回（代码核对）。即使状态相近，题目仍须具体历史才能区分正确项，不能只看共同结尾。选项可通过引用不同真实细节与合理误读实现接近的长度和具体程度，避免三个强行恢复/全面拒绝项配一个有条件正确项。严重含糊时重新选公开材料支持的判断目标，不能只改答案字母。输出原 JSON 结构的完整两题。'''


def revise(job,run,feedback,config):
    source=run/'authored'/(job['job_id']+'.json');dest=run/'revised'/(job['job_id']+'.json')
    if dest.exists():return
    record=json.loads(source.read_text());raw=record['result'];items=assemble(job,raw,source)
    request=deepcopy(job['payload'])
    if job['task']=='T2':request.update(public_input=items[0]['input'],paired_input=True)
    request.update(draft=raw,blind_feedback=[{'question':x['question'],'issues':feedback[x['instance_id']]['issues'],
        'reason':feedback[x['instance_id']]['reason'],'blind_selected_text':x['options'][feedback[x['instance_id']]['answer']],
        'ambiguous_texts':[x['options'][a] for a in feedback[x['instance_id']]['plausible_answers']]} for x in items if x['instance_id'] in feedback])
    provider=OfflineLoggedProvider(OfflineSamplingProvider(build_provider(config)),run/'revision_calls'/job['job_id'])
    messages=[{'role':'system','content':PROMPT.read_text()+'\n'+REVISION},{'role':'user','content':json.dumps(request,ensure_ascii=False)}]
    for attempt in range(2):
        try:
            response=provider.complete(messages,temperature=0.2,max_tokens=6000);new=json.loads(response)
            # Only questions are editable in this pass; the material remains identical.
            new['history_edit']=deepcopy(raw.get('history_edit'))
            revised=assemble(job,new,dest)
            if any(a['input']!=b['input'] for a,b in zip(items,revised)):raise ValueError('revision changed public input')
            save(dest,{'binding':record['binding'],'result':new,'provider':public_provider_config(config),'revision_of':{'path':str(source.relative_to(ROOT)),'sha256':sha(source)},'feedback_sha256':digest(request['blind_feedback'])});return
        except Exception as e:
            save(run/'revision_failures'/(job['job_id']+'-'+str(time.time_ns())+'.json'),{'type':type(e).__name__,'message':str(e)})
            if attempt:raise
            messages.append({'role':'user','content':'请修正完整 JSON：'+str(e)})


def main():
    p=argparse.ArgumentParser();p.add_argument('--follow',action='store_true');p.add_argument('--workers',type=int,default=4);args=p.parse_args()
    run=ROOT/'data/offline_scenarios_v2_20261020_main';all_jobs={j['job_id']:j for j in jobs()};submitted=set();active={}
    config=ModelRoutes.load(ROOT/'configs/gpt50_experiment/model_routes.hybrid.v3_2.json').provider_config('quality_review');config.update(timeout=150,max_transport_attempts=1,retry_backoff_seconds=0)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while True:
            for path in (run/'blind_review').glob('*.json'):
                rows=json.loads(path.read_text())['result']['answers'];flags=[r for r in rows if r['issues'] or not r['author_agreement'] or len(r['plausible_answers'])!=1]
                feedback={r['instance_id']:r for r in rows}
                for r in flags:
                    _,ordinal,task,index=r['instance_id'].split('-');key=f'GPT50_{ordinal}-{task}'
                    if key in submitted:continue
                    submitted.add(key);active[pool.submit(revise,all_jobs[key],run,feedback,config)]=key
            for future,key in list(active.items()):
                if not future.done():continue
                try:future.result();print('revised',key,flush=True)
                except Exception as e:print('revision failed',key,type(e).__name__,flush=True)
                del active[future]
            if not active and (not args.follow or (run/'review_complete.json').exists()):break
            time.sleep(3)
    print('revision jobs',len(submitted),flush=True)


if __name__=='__main__':main()
