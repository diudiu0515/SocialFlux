"""Local LatentSync 1.6 inference with isolated temporary files per node."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha

TOOL = ROOT / '.local_tools/annotation400-latentsync'


def repair_for(path):
    index = OUT / 'local_av/lipsync_repairs.json'
    repairs = load(index).get('nodes', {}) if index.exists() else {}
    return repairs.get(load(path)['node_id'], {})


def guidance_for(path, default):
    repair = repair_for(path)
    guidance = repair.get('guidance_scale', default)
    assert guidance in (1.0, 1.5, 2.0), 'Unsupported guidance correction'
    assert not repair or repair.get('reason'), 'Guidance corrections require a recorded reason'
    return guidance


def current_video(path, guidance):
    directory = path.parent
    required = ['speech.wav', 'motion.mp4', 'video.mp4', 'video.json']
    if not all((directory / name).exists() for name in required):
        return False
    old, request = load(directory / 'video.json'), load(path)
    return (old['spec_sha256'] == request['spec_sha256']
        and old['audio_sha256'] == sha(directory / 'speech.wav')
        and old['motion_sha256'] == sha(directory / 'motion.mp4')
        and old['sha256'] == sha(directory / 'video.mp4')
        and old['guidance_scale'] == guidance)


def ready_motion(path):
    directory = path.parent
    required = ['speech.wav', 'audio_screen.json', 'motion.mp4', 'motion.json']
    if not all((directory / name).exists() for name in required):
        return False
    audio_sha = sha(directory / 'speech.wav')
    screen, motion = load(directory / 'audio_screen.json'), load(directory / 'motion.json')
    return (screen['machine_screen_passed'] and screen['sha256'] == audio_sha
        and motion['audio_sha256'] == audio_sha and motion['sha256'] == sha(directory / 'motion.mp4'))


class Renderer:
    def __init__(self, guidance=1.0):
        sys.path.insert(0, str(TOOL))
        import torch
        from omegaconf import OmegaConf
        from diffusers import AutoencoderKL, DDIMScheduler
        from latentsync.models.unet import UNet3DConditionModel
        from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
        from latentsync.whisper.audio2feature import Audio2Feature
        from DeepCache import DeepCacheSDHelper
        self.torch = torch
        self.guidance = guidance
        self.config = OmegaConf.load(TOOL / 'configs/unet/stage2_512.yaml')
        dtype = torch.float16
        scheduler = DDIMScheduler.from_pretrained(str(TOOL / 'configs'))
        encoder = Audio2Feature(model_path=str(TOOL / 'checkpoints/whisper/tiny.pt'), device='cuda',
                                num_frames=self.config.data.num_frames, audio_feat_length=self.config.data.audio_feat_length)
        vae = AutoencoderKL.from_pretrained(str(TOOL / 'checkpoints/vae'), torch_dtype=dtype, local_files_only=True)
        vae.config.scaling_factor = 0.18215
        vae.config.shift_factor = 0
        model_path = TOOL / 'checkpoints/latentsync_unet.pt'
        unet, _ = UNet3DConditionModel.from_pretrained(OmegaConf.to_container(self.config.model), str(model_path), device='cpu')
        self.pipeline = LipsyncPipeline(vae=vae, audio_encoder=encoder, unet=unet.to(dtype=dtype), scheduler=scheduler).to('cuda')
        helper = DeepCacheSDHelper(pipe=self.pipeline)
        helper.set_params(cache_interval=3, cache_branch_id=0)
        helper.enable()
        self.helper = helper
        self.model_sha256 = sha(model_path)

    def render(self, path):
        request = load(path)
        directory = path.parent
        speech = directory / 'speech.wav'
        motion = directory / 'motion.mp4'
        target = directory / 'video.mp4'
        output = directory / 'video.json'
        guidance = guidance_for(path, self.guidance)
        audio_screen = load(directory / 'audio_screen.json')
        assert audio_screen['sha256'] == sha(speech) and audio_screen['machine_screen_passed'], request['node_id']
        motion_receipt = load(directory / 'motion.json')
        assert motion_receipt['sha256'] == sha(motion)
        assert motion_receipt['audio_sha256'] == sha(speech), 'Motion was rendered for a different waveform'
        assert motion_receipt['spec_sha256'] == request['spec_sha256']
        assert motion_receipt['identity_sha256'] == request['identity']['identity_sha256']
        if output.exists() and target.exists():
            old = load(output)
            if old['spec_sha256'] == request['spec_sha256'] and old['audio_sha256'] == sha(speech) and old['motion_sha256'] == sha(motion) and old['sha256'] == sha(target) and old['guidance_scale'] == guidance:
                return
            archive = directory / 'video_history' / sha(target)
            archive.mkdir(parents=True, exist_ok=True)
            for name in ['video.mp4', 'video.json', 'video_screen.json', 'lipsync_screen.json']:
                if (directory / name).exists() and not (archive / name).exists():
                    shutil.copy2(directory / name, archive / name)
        runtime = directory / 'runtime'
        runtime.mkdir(exist_ok=True)
        for name in ('checkpoints', 'configs'):
            link = runtime / name
            if not link.exists():
                link.symlink_to(TOOL / name, target_is_directory=True)
        # Upstream read_video() creates a relative `temp` folder. Keeping cwd
        # unique prevents GPU workers from deleting each other's frame files.
        os.chdir(runtime)
        seed = int(request['spec_sha256'][:8], 16) % (2 ** 31)
        self.torch.manual_seed(seed)
        raw = runtime / 'synced.mp4'
        self.pipeline(video_path=str(motion), audio_path=str(speech), video_out_path=str(raw),
            num_frames=self.config.data.num_frames, num_inference_steps=20, guidance_scale=guidance,
            weight_dtype=self.torch.float16, width=self.config.data.resolution,
            height=self.config.data.resolution, mask_image_path=str(TOOL / self.config.data.mask_image_path),
            temp_dir=str(runtime / 'render-temp'))
        assert raw.exists()
        # Mux the complete verified waveform; keep browser-compatible video and
        # a small padded tail so the final word is never truncated by rounding.
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-i', str(speech),
            '-map', '0:v:0', '-map', '1:a:0', '-vf', 'tpad=stop_mode=clone:stop_duration=0.12',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '128k', '-ar', '48000',
            '-t', str(load(directory / 'speech.json')['duration_seconds']),
            '-movflags', '+faststart', str(target)], check=True)
        metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(target)]))
        streams = metadata['streams']
        video = next(s for s in streams if s['codec_type'] == 'video')
        audio = next(s for s in streams if s['codec_type'] == 'audio')
        assert abs(float(video['duration']) - float(audio['duration'])) < .15
        save(output, {'spec_sha256': request['spec_sha256'], 'sha256': sha(target),
            'audio_sha256': sha(speech), 'motion_sha256': sha(motion),
            'identity_sha256': request['identity']['identity_sha256'],
            'spoken_text': request['source_public_response'], 'speech_language': 'en',
            'model': 'ByteDance/LatentSync-1.6', 'model_sha256': self.model_sha256,
            'seed': seed, 'inference_steps': 20, 'guidance_scale': guidance, 'deepcache': True,
            'render_repair': repair_for(path),
            'structural_metadata': {'duration_seconds_actual': float(metadata['format']['duration']),
                'video_duration_seconds': float(video['duration']), 'audio_duration_seconds': float(audio['duration']),
                'audio_stream_count': sum(s['codec_type'] == 'audio' for s in streams),
                'video_stream_count': sum(s['codec_type'] == 'video' for s in streams)},
            'human_review': 'pending', 'speech_verified': False})
        print(json.dumps({'node_id': request['node_id'], 'video': str(target)}), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scene', nargs='*')
    p.add_argument('--location', nargs='*')
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    p.add_argument('--guidance', type=float, default=1.0)
    p.add_argument('--queue', action='store_true', help='Share ready jobs through per-node local file locks')
    a = p.parse_args()
    renderer = Renderer(guidance=a.guidance)
    paths = []
    for index, row in enumerate(load(OUT / 'local_av/manifest.json')['nodes']):
        if index % a.shards != a.shard or (a.scene and row['scenario_id'] not in a.scene):
            continue
        path = ROOT / row['request_path']
        if a.location and load(path)['location'] not in a.location:
            continue
        paths.append(path)
    if not a.queue:
        for path in paths:
            renderer.render(path)
        return
    while True:
        pending, rendered = 0, 0
        for path in sorted(paths, key=lambda p: not bool(repair_for(p))):
            if current_video(path, guidance_for(path, a.guidance)):
                continue
            pending += 1
            with (path.parent / 'render.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                if not ready_motion(path):
                    continue
                if not current_video(path, guidance_for(path, a.guidance)):
                    renderer.render(path)
                    rendered += 1
        if not pending:
            return
        if not rendered:
            print(json.dumps({'queue_pending': pending, 'waiting_for_prerequisites_or_other_workers': True}), flush=True)
            time.sleep(20)


if __name__ == '__main__':
    main()
