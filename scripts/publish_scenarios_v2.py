"""Finalize scene coverage, retained media and legacy replacement ledger."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from offline.choice_builder import save, save_text, sha
from offline.scenario_v2 import OUT, ROOT, export, jobs
from tasks.offline_choice import public_instance


def main():
    run=ROOT/'data/offline_scenarios_v2_20261020_main';all_jobs=jobs();manifest=export(run,all_jobs)
    items=list(map(json.loads,(OUT/'items.jsonl').read_text().splitlines()))
    job_index={(j['scene'],j['task']):j for j in all_jobs}
    maps={bank:json.loads((ROOT/'data'/bank/'media.json').read_text()) for bank in ('offline_gpt50_t1_t3','offline_t1_t3_dev60')}
    pairs=[];media={};gaps=[];hashes={}
    for item in items:
        job=job_index[item['story_id'],item['task']]
        old=job['source_item'];bank='offline_t1_t3_dev60' if old['instance_id'].startswith('SFO-') else 'offline_gpt50_t1_t3'
        records=deepcopy(maps[bank].get(old['instance_id']+'-video',[]))
        valid=[]
        for r in records:
            r.pop('frames',None)
            p=Path(r['path'])
            if str(p) not in hashes:hashes[str(p)]=sha(p) if p.exists() else None
            if hashes[str(p)]!=r['sha256']:continue
            if item['task']=='T2':
                if set(r['evidence_ids']) not in ({'t1'},{'A:t1','B:t1'}):continue
                r['evidence_ids']=['A:t1','B:t1']
            valid.append(r)
        if not valid:gaps.append({'instance_id':item['instance_id'],'reason':'no_matching_verified_source_media'});continue
        text,video=deepcopy(item),deepcopy(item)
        for x in (text,video):x['metadata']['modality_pair_id']=item['instance_id'];x['authoring']['media_human_review']='pending'
        video['instance_id']+='-video';video['modality']='text+video';pairs.extend([text,video]);media[video['instance_id']]=valid
    save_text(OUT/'paired.items.jsonl',''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in pairs))
    save_text(OUT/'paired.public.jsonl',''.join(json.dumps(public_instance(x),ensure_ascii=False)+'\n' for x in pairs))
    save(OUT/'media.json',media);save(OUT/'pairing_report.json',{'logical_pairs':len(pairs)//2,'gaps':gaps,'note':'T2 仅使用 A/B 未改动的共同 t1 片段；共同焦点表达保持同一份文字，未新增焦点音视频。'})
    rows=[]
    for name in ('offline_gpt50_t1_t3','offline_t1_t3_dev60'):
        p=ROOT/'tasks/examples'/name/'items.jsonl'
        for x in map(json.loads,p.read_text().splitlines()):
            replacements=[i['instance_id'] for i in items if i['story_id']==x['story_id'] and i['task']==x['task']]
            rows.append({'old_id':x['instance_id'],'old_bank_sha256':sha(p),'scene':x['story_id'],'task':x['task'],'disposition':'removed_from_active_bank_replaced_by_v2','replacement_ids':replacements})
    save(OUT/'replacement_ledger.json',{'archived_old_items':len(rows),'active_v2_items':len(items),'items':rows})
    manifest.update(modality_pairs=len(pairs)//2,media_missing=len(gaps),legacy_replaced=len(rows));save(OUT/'manifest.json',manifest)
    lines=['# 50 场景新版离线题库 · 2026-10-20','',
        f"当前编配 {len(items)} 题，{manifest['scenario_count']} 个场景。每个场景 T1/T2/T3 各 2 题；旧 460 题退出默认题库，原始快照保留用于溯源。",'',
        '[网站 Demo](http://127.0.0.1:8000/offline-demo) · [完整题面](../../tasks/examples/offline_scenarios_v2/examples.md) · [三组字段](../../tasks/examples/offline_scenarios_v2/records.jsonl) · [旧题替换清单](../../tasks/examples/offline_scenarios_v2/replacement_ledger.json)','',
        '| 场景 | T1 | T2 | T3 | 合计 |','|---|---:|---:|---:|---:|']
    for s in manifest['scene_coverage']:lines.append('| '+s['scenario_id']+' | '+' | '.join(str(s['tasks'].get(t,0)) for t in ('T1','T2','T3'))+' | '+str(s['total'])+' |')
    lines+=['','任务形式：`'+json.dumps(manifest['subtypes'],ensure_ascii=False)+'`。','',
        '状态维度覆盖：`'+json.dumps(manifest['task_state_coverage'],ensure_ascii=False)+'`。','',
        '主要能力：`'+json.dumps(manifest['primary_capabilities'],ensure_ascii=False)+'`；设计难度：`'+json.dumps(manifest['design_difficulties'],ensure_ascii=False)+'`。','',
        '答案位置：`'+json.dumps(manifest['answer_positions'],ensure_ascii=False)+'`。','',
        f"已有公开材料的独立 API 盲试答覆盖 {manifest['blind_reviewed_items']} 题；机器指出问题或答案存在争议的题号：{json.dumps(manifest['machine_flagged_ids'],ensure_ascii=False)}。",'',
        'T3 复用 50 组已有相同起点的完整五轮分支。本批为连续互动窗口，无额外排定的外部事件（event_plan.selection=none）；核对共同起始时间、事件计划、公开时间线及窗口内未跨越外部事件，并保存条件哈希。部分事实轨迹的原始分支锁标志为 false，原样保留，未冒称两侧均开启锁定。分支结构和窗口核对不等于逐题答案已获人工批准。未来内容与隐藏状态未发送给出题/试答接口，也不进入被测输入。T2 的 5 组已有受控历史保留原回放；其余 45 组只编辑一处历史表达并记录原文和修改，公开证据核验与环境状态回放状态分开，后者仍待完成。', '',
        f"保留 {len(pairs)//2} 对文字／文字+视频条件，题干、选项与答案相同；{len(gaps)} 题无匹配素材，未用其他场景的视频补位。T2 焦点表达没有新增音视频。",'',
        '全部为新版开发题。T1/T2 人工核验、T3 人工标注均待完成，ground_truth=null；API 一致不等于人工通过，旧来源审核状态也保留。', '',
        '生成来源：144 个场景／任务组由接口生成初稿；6 个接口超时组依据同一公开材料由助手补写。后续 API 修订与助手编辑均保留原稿及内容哈希，不伪称人工审阅。', '',
        '复现：`python -m offline.scenario_v2 --export-only`；仅补查改动或缺失题面：`python -m offline.scenario_v2_review --refresh-items`；发布数据及报告：`python -m scripts.publish_scenarios_v2`。`curate_scenarios_v2.py`、`refine_scenarios_v2.py`、`finalize_scenarios_v2.py` 记录公开证据补写与修订配方，按顺序使用；原始 API 记录不覆盖。','']
    save_text(ROOT/'reports/experiments/2026-10-20_scenarios_v2.md','\n'.join(lines))
    print(json.dumps({k:manifest[k] for k in ('item_count','scenario_count','tasks','blind_reviewed_items','machine_flagged_ids','modality_pairs')},ensure_ascii=False))


if __name__=='__main__':main()
