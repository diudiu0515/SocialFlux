"""Resume only missing translation/authoring work after active builders finish."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import OUT,load,save,scene_job,publish

def alive(pid):
    try:
        # A reused PID must not keep this queue waiting on an unrelated job.
        return b'build_annotation400.py' in Path(f'/proc/{pid}/cmdline').read_bytes()
    except FileNotFoundError:return False

def builders_running():
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=path.read_bytes().split(b'\0')
            if any(a==b'scripts/build_annotation400.py' or a.endswith(b'/scripts/build_annotation400.py') for a in args):return True
        except OSError:pass
    return False

def main():
    p=argparse.ArgumentParser();p.add_argument('--wait-for',nargs='*',type=int,default=[]);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    while builders_running() or any(alive(pid) for pid in a.wait_for):time.sleep(15)
    source=[json.loads(s) for s in (OUT/'source.items.jsonl').read_text().splitlines()];plan=load(OUT/'plan.json')
    attempts=[]
    for cycle in range(3):
        missing=[f'GPT50_{i:03}' for i in range(1,51) if not (OUT/'scenes'/f'GPT50_{i:03}'/'items.json').exists()]
        if not missing:publish();return
        print(json.dumps({'cycle':cycle+1,'missing':missing}),flush=True)
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            jobs={pool.submit(scene_job,i,s,[r for r in source if r['story_id']==s],plan):s for i,s in enumerate(missing)}
            for future in as_completed(jobs):
                try:future.result()
                except Exception as e:
                    row={'cycle':cycle+1,'scene':jobs[future],'error':str(e),'type':type(e).__name__};attempts.append(row);print(json.dumps(row),flush=True)
                save(OUT/'completion_attempts.json',attempts)
    publish()  # Fail explicitly if any required scene is still absent.

if __name__=='__main__':main()
