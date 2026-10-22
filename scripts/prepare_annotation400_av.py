"""English, exact-dialogue audio/video requests bound to the 400-question release.

Each scene freezes its shared public inputs before question authoring finishes.
Final bindings are rebuilt against the completed release and checked separately.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import OUT, load, save, jsonl, sha
from offline.talking_head import prepare, generate, public_nodes, summary
from prompts.loader import render_prompt

AV=OUT/'audio_video'

def prepare_scene(scene):
    directory=AV/scene
    manifest_path=directory/'manifest.json'
    if manifest_path.exists():return manifest_path
    rows=load(OUT/'scenes'/scene/'translated.items.json')
    bank=directory/'source_bank'
    jsonl(bank/'items.jsonl',rows)
    empty=directory/'no_historical_references.json'
    save(empty,{'batch_root':'.','requests':[]})
    m=prepare(bank=bank,output=directory,source_manifest=empty)
    m['speech_language']='en'
    m['scope']='complete_public_environment_dialogue_t1_t2_shared_ending'
    m['annotation_release']='annotation400-en-20261022-v1'
    for node in m['nodes']:node.update(speech_language='en',spoken_text=node['source_public_response'])
    # The first segment creates the new fictional identity; subsequent segments
    # receive its exact reference through the existing resumable queue.
    anchor=m['requests'][0]
    p=ROOT/anchor['request_file'];r=load(p)
    node=next(n for n in m['nodes'] if n['node_id']==anchor['node_id'])
    r['prompt_id']='offline_talking_head_english_v1'
    r['prompt']=render_prompt(r['prompt_id'],identity_json=r['identity'],spoken_line=anchor['source_public_response'],expression_json=node['source_observable_expression'])
    r['audio']['language']='en'
    save(p,r);save(manifest_path,m)
    return manifest_path

def main():
    p=argparse.ArgumentParser();p.add_argument('--scenes',nargs='+',required=True);p.add_argument('--run',action='store_true');p.add_argument('--anchor-only',action='store_true');p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    for scene in a.scenes:
        path=prepare_scene(scene);m=load(path)
        print(json.dumps({'scene':scene,**summary(m)}),flush=True)
        if a.run:
            selected=[m['requests'][0]['request_id']] if a.anchor_only else None
            print(json.dumps(generate(path,submit_new=True,workers=a.workers,request_ids=selected)),flush=True)

if __name__=='__main__':main()
