"""Run or score offline choice responses through configured providers.

Each requested item is called once. Malformed answers are recorded, never repaired.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from offline.choice_builder import save, sha
from tasks.offline_choice import answer_prompt, validate_item
from evaluation.offline_choice import score_items
from evaluation.t4_media import video_blocks, provider_messages, compact_media
from providers.factory import build_provider, public_provider_config
from providers.model_routes import ModelRoutes


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def call_item(item, provider_config, *, diagnostic=False, media=None, transport=None):
    start=time.monotonic()
    record={'instance_id':item['instance_id'],'provider':public_provider_config(provider_config),
            'diagnostic':diagnostic,'transport':transport}
    try:
        messages=[{'role':'user','content':answer_prompt(item,diagnostic)}]
        if item['modality']=='text+video':
            if not media or not transport:
                raise ValueError('video condition requires verified media and explicit transport')
            content=[{'type':'text','text':messages[0]['content']}]
            for asset in media:
                content.append({'type':'text','text':'以下视频对应公开历史定位：'+', '.join(asset.get('evidence_ids', []))})
                content += video_blocks(asset,transport)
            messages[0]['content']=content
            messages=provider_messages(messages,provider_config['provider'])
        record['messages']=compact_media(messages)
        provider=build_provider(provider_config)
        record['raw_output']=provider.complete(messages,temperature=0)
    except Exception as e:
        record['call_error']={'type':type(e).__name__,'message':str(e)[:1000]}
    record['elapsed_seconds']=round(time.monotonic()-start,3)
    return record


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--items',type=Path,required=True)
    p.add_argument('--responses',type=Path,help='Score saved responses without any provider calls')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model-routes',default='configs/gpt50_experiment/model_routes.hybrid.v3_2.json')
    p.add_argument('--limit',type=int)
    p.add_argument('--per-task',type=int,help='First n items per T1/T2/T3 for a balanced smoke run')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--formal',action='store_true',help='Require approved human GT and source/replay admission')
    p.add_argument('--check-only',action='store_true')
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--timeout',type=float,default=180,help='Timeout per provider call in seconds; no automatic retries')
    p.add_argument('--media-manifest',type=Path)
    p.add_argument('--transport',choices=['native_video','video_frames'])
    args=p.parse_args(argv);items=read_jsonl(args.items)
    if args.per_task:
        items=[i for task in ('T1','T2','T3') for i in [x for x in items if x['task']==task][:args.per_task]]
    if args.limit:items=items[:args.limit]
    for item in items:validate_item(item,formal=args.formal)
    if args.check_only:
        print(json.dumps({'validated':len(items),'formal':args.formal,'provider_calls':0}));return
    args.output.mkdir(parents=True,exist_ok=True)
    if not args.responses and (args.output/'responses.jsonl').exists():
        raise FileExistsError('response log already exists; use a new output directory or --responses to score it')
    if args.responses:
        responses=read_jsonl(args.responses)
    else:
        routes=ModelRoutes.load(args.model_routes)
        media=json.loads(args.media_manifest.read_text()) if args.media_manifest else {}
        responses=[]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[]
            for item in items:
                config=routes.provider_config(item['task'].lower()+'_answer')
                config.update(max_tokens=1000,timeout=args.timeout,max_transport_attempts=1)
                futures.append(pool.submit(call_item,item,config,diagnostic=args.diagnostic,
                                           media=media.get(item['instance_id']),transport=args.transport))
            for f in as_completed(futures):
                row=f.result();responses.append(row)
                with (args.output/'responses.jsonl').open('a',encoding='utf-8') as out:
                    out.write(json.dumps(row,ensure_ascii=False)+'\n')
                print(row['instance_id'],'call_failure' if row.get('call_error') else row['raw_output'],flush=True)
    result=score_items(items,responses,diagnostic=args.diagnostic,formal=args.formal)
    result['items_sha256']=sha(args.items)
    save(args.output/'scores.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
