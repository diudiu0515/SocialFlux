"""Publishable silent references from this project's original synthetic videos."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import OUT,load,save,sha
from scripts.prepare_annotation400_av import prepare_scene
from scripts.run_multimodal_video_queue import run_record,DEFAULT_KEY_FILE

DIRECTORY=OUT/'silent_identity_references'
URL='https://socialflux-annotation-demo-20261021.junqiao24.chatgpt.site'

def bootstrap(scene):
    m=load(prepare_scene(scene));r=m['requests'][0]
    return {'scene':scene,**run_record(ROOT,r,key_file=DEFAULT_KEY_FILE,model=m['provider']['model'],resolution=m['provider']['resolution'],submit_new=True,poll_seconds=15,max_wait_seconds=1800)}

def prepare(site):
    source=load(OUT/'source.media.json');rows=[];missing=[]
    for i in range(1,51):
        scene=f'GPT50_{i:03}';path=OUT/'audio_video'/scene/'manifest.json';current=load(path) if path.exists() else None
        video=ROOT/current['requests'][0]['video_file'] if current else None
        if video and video.exists():kind='generated_english_anchor'
        else:
            videos=source[f'SFV2-{i:03}-T1-01']['media']
            if not videos:missing.append(scene);continue
            video=site/'public/media'/(videos[0]['sha256']+'.mp4');assert sha(video)==videos[0]['sha256'];kind='existing_original_nonverbal_video'
        target=DIRECTORY/(scene+'.mp4');sidecar=target.with_suffix('.json');source_hash=sha(video)
        transformation='silent_identity_reference_3s_512w_v1'
        if not sidecar.exists() or load(sidecar)['source_sha256']!=source_hash or not target.exists() or load(sidecar).get('transformation')!=transformation:
            target.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(video),'-t','3','-map','0:v:0','-an','-vf','scale=512:-2,fps=24','-c:v','libx264','-preset','medium','-crf','26','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)
            save(sidecar,{'scene':scene,'source_path':str(video),'source_sha256':source_hash,'sha256':sha(target),'source_kind':kind,'transformation':transformation})
        row=load(sidecar);assert sha(target)==row['sha256']
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(target)]))
        assert [s['codec_type'] for s in probe['streams']]==['video']
        dest=site/'public/media'/('identity-ref-'+row['sha256']+'.mp4')
        if not dest.exists():shutil.copyfile(target,dest)
        rows.append({**row,'path':str(target.relative_to(ROOT)),'url':URL+'/media/'+dest.name,'hosted':False})
    save(DIRECTORY/'manifest.json',{'source':'project_original_synthetic_character_videos','references':rows,'missing_scenes':missing,'hosted':False})
    print(json.dumps({'silent_references':len(rows),'missing_scenes':missing}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--site-dir',type=Path,default=ROOT/'build/annotation400-site');p.add_argument('--bootstrap',nargs='*',default=[]);p.add_argument('--wait-for',type=int);a=p.parse_args()
    if a.wait_for:
        while Path(f'/proc/{a.wait_for}/cmdline').exists() and b'run_annotation400_av.py' in Path(f'/proc/{a.wait_for}/cmdline').read_bytes():time.sleep(15)
    if a.bootstrap:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for row in pool.map(bootstrap,a.bootstrap):print(json.dumps(row),flush=True)
    prepare(a.site_dir)
