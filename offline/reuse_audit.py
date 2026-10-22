"""API audit of legacy content against v2 design; never human ground truth."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from offline.choice_builder import save, sha
from offline.provider_compat import OfflineLoggedProvider, OfflineSamplingProvider
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes
from tasks.offline_choice import public_instance, visible_evidence
from tasks.offline_design import CAPABILITIES

ROOT=Path(__file__).resolve().parents[1]
BANKS={'dev60':'offline_t1_t3_dev60','gpt50-t1-t3':'offline_gpt50_t1_t3'}
BLIND='''你是SocialFlux离线题目的独立试答者。只根据公开材料判断，不会收到作者答案、隐藏状态或未来。共同材料下每题分别判断，不把其他题选项当新事实。情绪、合作倾向、关系和风险分别判断；基本不变需要正面依据；有机制支持的未来可以预测，不要求未来已发生。输出纯JSON：{"answers":[{"instance_id":"...","answer":"B","plausible_answers":["B"],"evidence_ids":["t1"],"rationale":"100字内"}]}。每题恰好一次；answer必须为已有选项，plausible_answers列所有难以区分的合理选项，证据只引用公开定位。'''
REVIEW='''你审核旧题能否迁移到新版SocialFlux-Eval，重点是新版任务设计适配性，不是仅检查试答是否命中旧答案。机器审核不能替代人工真值。
新版总体目标：动态社会理解与适应。三种被测能力为情境证据整合、多维状态区分、跨时动态推理；Emotion、Behavioral Disposition、Relationship、Interaction Risk是判断对象。每题一个主能力，四维在题库层面覆盖。
T1：根据截至指定时点已发生的公开历史理解当前状态或明确区间变化；支持当前判断、变化、证据支持、状态组合。明确主体、关系方向、变化起点、风险事件与窗口；当前风险以现有安排为条件，新行动比较属于T3。
T2：共同背景、人物角色、外部条件和焦点台词/表情/语气一致，比较集中于某历史因素的A/B。支持状态比较、表达解释、状态组合/行为原因、支持与反证/修复整合。答案与干扰项依赖具体历史；仅说历史重要、只看共同结尾能选对均不足。可只改变部分状态，其他相近。
T3：同一起点2–4个合理可执行且实质不同的行动。基本形式为选择行动（必须有明确目标）或选择后果解释。比较对象清楚；即时为行动及下一次环境回应后；延迟默认含即时5轮、最多10轮；可考跨时取舍、多维后果。公开材料支持概率预测，不能据偶然未来写必然规律。行动数字、答案字母。
通常四选一，纯方向可三项，需要时单列证据不足。旧强度题不自动报废，但精确档位缺公开可区分依据需重写；能够保留旧判断目标、只改表述的与需要重选变量/时间的须区分。选项长度/具体度/语气接近，错项有局部合理性；避免三个极端项配一个长谨慎项。不要把友好等同信任、合作等同没有不满、承诺等同履约或气氛改善等同风险降低。基本不变与证据不足不同。
普通题证据直接一致；Hard需整合分散/冲突证据、区分不同步状态或累积/反证/修复/跨时取舍。一维可Hard，多维可普通。
给出迁移等级：metadata_only=题面答案可保留，只补能力/难度/字段；editorial=同一判断目标可保留，仅需中性措辞、行动编号、选项平衡等轻改；substantive=需要重定状态/时间/正确答案/问题形式或重建选项；source_only=旧题目标不成立，仅材料值得另出题。
不要因缺少能力标签就要求重写；不要因没有新题型就废掉旧题型；不要用已命中旧答案作为质量合格的充分条件。参考答案与盲试答都可能错。只引用公开证据，不编造分支或人工审核。
输出纯JSON：{"reviews":[{"instance_id":"...","migration_level":"metadata_only|editorial|substantive|source_only","new_form":"T1/current_state|T1/interval_change|T1/evidence_support|T1/state_combination|T2/history_comparison|T2/expression_meaning|T2/joint_comparison|T2/history_evidence|T3/action_selection|T3/consequence_explanation","best_answer":"已有选项或null","acceptable_answers":["B"],"public_evidence_sufficient":true,"evidence_ids":["t1"],"counterevidence_ids":[],"issues":["具体问题，无则空"],"rationale":"120字内，说明具体证据与新版适配性","revision":"80字内，具体改法，无则空","primary_capability":"situational_evidence_integration|multidimensional_state_distinction|temporal_dynamics_reasoning","design_difficulty":"ordinary|hard","difficulty_reason":"Hard必填具体依据"}]}。每题恰好一项。无唯一可支持选项时best_answer可null。'''


def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def groups():
    result={}
    for bank,name in BANKS.items():
        path=ROOT/'tasks/examples'/name/'items.jsonl';bank_sha=sha(path)
        for line in path.read_text().splitlines():
            x=json.loads(line);key=bank+'-'+x['task']+'-'+digest(x['input'])[:16]
            group=result.setdefault(key,dict(group_id=key,bank=bank,bank_sha256=bank_sha,items=[]));group['items'].append(x)
    return list(result.values())


def validate(raw,group,phase):
    obj=json.loads(raw);rows=obj['answers' if phase=='blind' else 'reviews'];by_id={r['instance_id']:r for r in rows}
    if len(rows)!=len(by_id) or set(by_id)!={x['instance_id'] for x in group['items']}:raise ValueError('item IDs missing or duplicated')
    for x in group['items']:
        r=by_id[x['instance_id']];answer=r['answer' if phase=='blind' else 'best_answer'];accepted=r['plausible_answers' if phase=='blind' else 'acceptable_answers']
        if answer not in x['options'] and not(phase=='review' and answer is None):raise ValueError('answer outside options')
        if not isinstance(accepted,list) or len(set(accepted))!=len(accepted) or not set(accepted)<=x['options'].keys():raise ValueError('invalid acceptable answers')
        if answer is not None and answer not in accepted:raise ValueError('best answer missing from acceptable answers')
        if not isinstance(r['evidence_ids'],list) or not set(r['evidence_ids'])<=visible_evidence(x):raise ValueError('invisible evidence')
        if phase=='review':
            from tasks.offline_design import TEMPLATES
            if r['migration_level'] not in {'metadata_only','editorial','substantive','source_only'}:raise ValueError('invalid migration level')
            if r['new_form'] not in TEMPLATES or not r['new_form'].startswith(x['task']+'/'):raise ValueError('invalid task form')
            if r['primary_capability'] not in CAPABILITIES or r['design_difficulty'] not in {'ordinary','hard'}:raise ValueError('invalid capability or difficulty')
            if r['design_difficulty']=='hard' and not r['difficulty_reason'].strip():raise ValueError('Hard needs concrete reason')
            if not isinstance(r['public_evidence_sufficient'],bool) or not isinstance(r['issues'],list):raise ValueError('invalid review fields')
            if not set(r['counterevidence_ids'])<=visible_evidence(x):raise ValueError('invisible counterevidence')
            if r['migration_level']=='metadata_only' and (not r['public_evidence_sufficient'] or len(accepted)!=1):raise ValueError('metadata-only reuse requires unambiguous public support')
    return obj


def call(group,phase,config,run,blind=None,request_timeout=300):
    path=run/'groups'/group['group_id']/(phase+'.json')
    binding=digest({'items':group['items'],'prompt':BLIND if phase=='blind' else REVIEW,'config':public_provider_config(config)})
    if path.exists():
        saved=json.loads(path.read_text())
        if saved['binding']!=binding or saved['blind_sha256']!=(digest(blind) if blind else None):raise ValueError('cached input mismatch')
        return saved['result']
    visible=[public_instance(x) for x in group['items']]
    payload={'shared_input':visible[0]['input'],'questions':[{k:x[k] for k in ('instance_id','question','options')} for x in visible]}
    if phase=='review':payload.update(task=group['items'][0]['task'],blind_diagnostic=blind,old_labels=[{'instance_id':x['instance_id'],'answer':x['authoring']['answer'],'acceptable_answers':x['authoring'].get('acceptable_answers',[x['authoring']['answer']]),'target_spec':x['target_spec']} for x in group['items']])
    messages=[{'role':'system','content':BLIND if phase=='blind' else REVIEW},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    transport_config={**config,'timeout':request_timeout}
    provider=OfflineLoggedProvider(OfflineSamplingProvider(build_provider(transport_config)),run/'calls'/group['group_id']/phase)
    for attempt in range(2):
        past=[json.loads(p.read_text()) for p in (run/'calls'/group['group_id']/phase).glob('*.json')]
        if sum(r['status'] in {'completed','failed'} for r in past)>=2:
            raise RuntimeError('phase retry budget exhausted; previous failures retained')
        raw=provider.complete(messages,temperature=0,max_tokens=5000 if phase=='blind' else 7000)
        try:result=validate(raw,group,phase)
        except (ValueError,KeyError,TypeError) as e:
            save(run/'invalid'/group['group_id']/(phase+f'-{time.time_ns()}.json'),{'raw':raw,'error':str(e)})
            if attempt:raise
            messages.append({'role':'user','content':'输出结构校验失败：'+str(e)+'。按相同材料重输出完整纯JSON。'});continue
        save(path,{'binding':binding,'blind_sha256':digest(blind) if blind else None,'result':result,'transport_timeout':request_timeout,'completed_at_utc':datetime.now(timezone.utc).isoformat()})
        return result


def checks(item):
    src=item['authoring']['construction_source'];out={}
    for kind in ('scenario','trajectory','replay'):
        if src.get(kind+'_path'):
            p=ROOT/src[kind+'_path'];out[kind]=p.is_file() and sha(p)==src.get(kind+'_sha256')
    return out


def run_group(group,config,run,request_timeout):
    blind=call(group,'blind',config,run,request_timeout=request_timeout);call(group,'review',config,run,blind,request_timeout=request_timeout)


def export(run,all_groups):
    rows=[];pending=[];pending_items=[]
    config=json.loads((run/'manifest.json').read_text())['provider']
    blind_completed=0
    for g in all_groups:
        path=run/'groups'/g['group_id']/'review.json'
        blind_path=path.parent/'blind.json'
        blind_cache=json.loads(blind_path.read_text()) if blind_path.exists() else {}
        review_cache=json.loads(path.read_text()) if path.exists() else {}
        blind_done=bool(blind_cache) and blind_cache.get('binding')==digest({'items':g['items'],'prompt':BLIND,'config':config})
        if blind_done:blind_completed+=len(g['items'])
        review_done=blind_done and bool(review_cache) and review_cache.get('binding')==digest({'items':g['items'],'prompt':REVIEW,'config':config}) and review_cache.get('blind_sha256')==digest(blind_cache['result'])
        if not review_done:
            phase='review' if blind_done else 'blind'
            attempts=[json.loads(p.read_text()) for p in (run/'calls'/g['group_id']/phase).glob('*.json')]
            latest=max(attempts,key=lambda r:r['started_at_unix']) if attempts else {}
            status=latest.get('status','not_started')
            reason=('api_timeout' if latest.get('error',{}).get('type')=='TimeoutError' else 'api_error') if status=='failed' else ('invalid_output' if status=='completed' else status)
            if (blind_cache and not blind_done) or review_cache:reason='cached_input_mismatch'
            for x in g['items']:
                pending.append(x['instance_id'])
                pending_items.append({'bank':g['bank'],'instance_id':x['instance_id'],'item_sha256':digest(x),
                    'task':x['task'],'migration_status':'pending','pending_phase':phase,
                    'pending_reason':reason,'blind_completed':blind_done,'formal_usable':False})
            continue
        r={x['instance_id']:x for x in review_cache['result']['reviews']}
        a={x['instance_id']:x for x in blind_cache['result']['answers']}
        for x in g['items']:
            iid=x['instance_id'];review=r[iid];accepted=x['authoring'].get('acceptable_answers',[x['authoring']['answer']]);source=checks(x)
            level=review['migration_level'];notes=[]
            if level in {'metadata_only','editorial'} and review['best_answer'] not in accepted:
                level='substantive';notes.append('新建议答案不在原可接受集合内，需要答案实质修订。')
            if level=='metadata_only' and len(x['options'])>4:
                level='editorial';notes.append('内容可留，但需把旧六档格式收束到新版通常四选一。')
            if level=='metadata_only' and len(accepted)>1:
                level='editorial';notes.append('原标签接受多个选项，需要人工收束为新版可区分的单一最佳判断。')
            pending_replay=x['task'] in {'T2','T3'} and x['authoring'].get('replay_status')!='validated'
            rows.append({'bank':g['bank'],'instance_id':iid,'bank_sha256':g['bank_sha256'],'item_sha256':digest(x),'task':x['task'],
                'migration_status':'reviewed','migration_level':level,'decision_notes':notes,'source_checks':source,'replay_pending':pending_replay,
                'source_review_status':x['authoring']['construction_source'].get('source_review_status'),
                'review':review,'blind_answer':a[iid],'old_answer':x['authoring']['answer'],
                'blind_agrees_with_old':a[iid]['answer'] in accepted,'review_agrees_with_old':review['best_answer'] in accepted,
                'reviewer_type':'model_review_not_human','formal_usable':False})
    summary={'reviewed_items':len(rows),'blind_completed_items':blind_completed,'planned_items':sum(len(g['items']) for g in all_groups),'pending_ids':pending,
       'migration_levels':dict(Counter(x['migration_level'] for x in rows)),
       'pending_reasons':dict(Counter(x['pending_reason'] for x in pending_items)),
       'pending_by_task':dict(Counter(x['task'] for x in pending_items)),
       'by_task':{t:dict(Counter(x['migration_level'] for x in rows if x['task']==t)) for t in ('T1','T2','T3')},
       'replay_pending':sum(x['replay_pending'] for x in rows),'source_hash_failures':sum(not all(x['source_checks'].values()) for x in rows),
       'blind_agreement_count':sum(x['blind_agrees_with_old'] for x in rows),'review_agreement_count':sum(x['review_agrees_with_old'] for x in rows),
       'note':'按共同材料分组盲试答，再由同模型对照新版任务标准复核；不是benchmark准确率或人工批准。'}
    save(run/'results.json',{'summary':summary,'items':rows,'pending_items':pending_items});save(run/'progress.json',summary);return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=5);p.add_argument('--limit-groups',type=int);p.add_argument('--export-only',action='store_true');p.add_argument('--request-timeout',type=int,default=300);args=p.parse_args()
    run=Path(args.output);run.mkdir(parents=True,exist_ok=True)
    config=ModelRoutes.load(ROOT/'configs/gpt50_experiment/model_routes.hybrid.v3_2.json').provider_config('quality_review');config.update(timeout=120,max_transport_attempts=1,retry_backoff_seconds=0)
    all_groups=groups();selected=all_groups[:args.limit_groups] if args.limit_groups else all_groups
    manifest={'format':'socialflux_legacy_v2_api_audit_v1','provider':public_provider_config(config),'group_count':len(all_groups),'item_count':sum(len(g['items']) for g in all_groups),'rubric_sha256':digest([BLIND,REVIEW])}
    if (run/'manifest.json').exists() and json.loads((run/'manifest.json').read_text())!=manifest:raise ValueError('audit config changed')
    save(run/'manifest.json',manifest)
    if not args.export_only:
        save(run/'executions'/(str(time.time_ns())+'.json'),{'request_timeout':args.request_timeout,'workers':args.workers,'selected_groups':len(selected)})
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs={pool.submit(run_group,g,config,run,args.request_timeout):g for g in selected}
            for f in as_completed(jobs):
                g=jobs[f]
                try:f.result();print('completed',g['group_id'],flush=True)
                except Exception as e:
                    save(run/'failures'/(g['group_id']+f'-{time.time_ns()}.json'),{'type':type(e).__name__,'status':getattr(e,'status',None),'message':str(e)})
                    print('failed',g['group_id'],type(e).__name__,getattr(e,'status',''),flush=True)
                export(run,all_groups)
    summary=export(run,all_groups);print(json.dumps({k:v for k,v in summary.items() if k!='pending_ids'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
