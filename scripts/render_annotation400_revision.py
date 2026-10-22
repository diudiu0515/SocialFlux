"""Isolated 4–5 second checkpoint videos; never replaces the frozen release.

Run prepare/audio/asr/motion/video/sync in the appropriate local environments.
Full replies remain text; the checkpoint line is an explicitly versioned excerpt
or paraphrase, never an assertion that the old spoken stimulus is unchanged.
"""
import argparse
import copy
from difflib import SequenceMatcher
import hashlib
import inspect
from importlib.metadata import version as package_version
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha

REVISION = ROOT / 'data/offline_checkpoint_v2_20261022'
VERSION = 'checkpoint_4s5s_v2'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def implementation(*objects):
    return digest([inspect.getsource(obj) for obj in objects])


def file_fingerprints(paths):
    return {str(Path(path).relative_to(ROOT)): sha(path) for path in sorted(set(map(Path, paths)))}


def safe_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(REVISION.resolve()):
        raise ValueError('Revision writes must stay inside the independent revision directory')
    return path


def validate_request(row):
    path = safe_path(row['request_path'])
    request = load(path)
    spec = {k: v for k, v in request.items() if k != 'spec_sha256'}
    if (digest(spec) != request['spec_sha256'] or request['spec_sha256'] != row['spec_sha256']
            or request['node_id'] != row['node_id'] or request['scenario_id'] != row['scenario_id']):
        raise ValueError('Request has changed since this manifest was prepared')
    # Upstream runtimes have two intentional read-only model/config links.
    # Reject all other links that could redirect output into the old release.
    for existing in path.parent.rglob('*'):
        if existing.is_symlink():
            resolved = existing.resolve()
            allowed_model = (existing.name in ('checkpoints', 'configs') and
                resolved == (ROOT / '.local_tools/annotation400-latentsync' / existing.name).resolve())
            if not allowed_model:
                safe_path(existing)
    return path


def run(args):
    subprocess.run([str(x) for x in args], check=True)


def prepare(line_files, manifest):
    originals = {r['node_id']: r for r in load(OUT / 'local_av/manifest.json')['nodes']}
    lines = []
    for path in line_files:
        data = load(path)
        lines.extend(data if isinstance(data, list) else data['nodes'])
    if len({x['node_id'] for x in lines}) != len(lines):
        raise ValueError('Duplicate checkpoint node')
    rows = []
    for line in lines:
        old_path = ROOT / originals[line['node_id']]['request_path']
        old = load(old_path)
        if line['original_response'] != old['source_public_response']:
            raise ValueError('Source response changed: ' + line['node_id'])
        text = line['checkpoint_text'].strip()
        if not 4 <= len(re.findall(r"\b[\w]+(?:['’][\w]+)*\b", text)) <= 14:
            raise ValueError('Checkpoint line must be a short complete utterance: ' + text)
        if not line['source_quote'] or line['source_quote'] not in old['source_public_response']:
            raise ValueError('Support must be an exact public source quote')
        if line['verbatim_excerpt'] and text not in old['source_public_response']:
            raise ValueError('Verbatim excerpt is not present in the source')
        request = copy.deepcopy(old)
        request.pop('spec_sha256')
        request.update(source_public_response=text, full_public_response=old['source_public_response'],
                       method=VERSION, checkpoint_line=line, source_spec_sha256=old['spec_sha256'],
                       source_request_path=str(old_path.relative_to(ROOT)),
                       target_seconds=4.6, speed=1.0, stimulus_status='revision_candidate')
        request['spec_sha256'] = digest(request)
        directory = safe_path(REVISION / old['scenario_id'] / old['node_id'] / request['spec_sha256'][:12])
        directory.mkdir(parents=True, exist_ok=True)
        save(directory / 'request.json', request)
        rows.append({'node_id': old['node_id'], 'scenario_id': old['scenario_id'],
                     'spec_sha256': request['spec_sha256'], 'request_path': str(directory / 'request.json')})
    save(safe_path(manifest), {'version': VERSION, 'nodes': rows, 'node_count': len(rows),
         'source_bank_sha256': sha(OUT / 'items.jsonl'), 'full_reply_text_preserved': True,
         'human_review': 'pending', 'release_eligible': False, 'published': False})
    print(json.dumps({'prepared': len(rows), 'manifest': str(manifest)}), flush=True)


def current(directory, name, generation):
    output = directory / (name + ('.wav' if name == 'speech' else '.mp4'))
    receipt = directory / (name + '.json')
    return (output.exists() and receipt.exists()
            and load(receipt).get('generation_sha256') == digest(generation)
            and load(receipt).get('sha256') == sha(output))


def trim_edges(samples, sample_rate):
    """Only trim quiet ends, retaining 100/160ms margins around detected speech."""
    import numpy as np
    window = int(.01 * sample_rate)
    energy = np.array([np.sqrt(np.mean(samples[i:i+window] ** 2))
                       for i in range(0, len(samples), window)])
    active = np.flatnonzero(energy > max(.0005, float(energy.max()) * .008))
    if not len(active):
        raise ValueError('No audible speech')
    start = max(0, int(active[0] * window - .1 * sample_rate))
    end = min(len(samples), int((active[-1] + 1) * window + .16 * sample_rate))
    return samples[start:end], {'start_samples': start, 'end_samples': end,
                               'original_samples': len(samples)}


class Speech:
    def __init__(self):
        import torch
        from kokoro import KModel, KPipeline
        self.torch = torch
        self.weights = ROOT / '.local_models/annotation400-kokoro'
        model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(self.weights / 'config.json'),
                       model=str(self.weights / 'kokoro-v1_0.pth')).to('cuda').eval()
        self.pipeline = KPipeline(lang_code='a', model=model, repo_id='hexgrad/Kokoro-82M')
        self.model_sha = sha(self.weights / 'kokoro-v1_0.pth')
        self.dependencies = {'config_sha256': sha(self.weights / 'config.json'),
                             'kokoro_version': package_version('kokoro'),
                             'torch_version': package_version('torch')}

    def render(self, path):
        import numpy as np
        import soundfile as sf
        request = load(path)
        directory = safe_path(path.parent)
        voice_path = self.weights / 'voices' / (request['voice'] + '.pt')
        generation = {'version': VERSION, 'source_sha256': implementation(Speech, trim_edges),
                      'spec_sha256': request['spec_sha256'], 'model_sha256': self.model_sha,
                      'voice_sha256': sha(voice_path), 'target_seconds': request['target_seconds'],
                      'dependencies': self.dependencies}
        if current(directory, 'speech', generation):
            return
        voice = self.torch.load(voice_path, map_location='cpu', weights_only=True)
        speed = 1.0
        for attempt in range(2):
            results = list(self.pipeline(request['source_public_response'], voice=voice, speed=speed))
            raw = np.concatenate([result.audio.cpu().numpy() for result in results])
            samples, trim = trim_edges(raw, 24000)
            duration = len(samples) / 24000
            if attempt == 0 and (duration > 4.4 or duration < 3.5):
                speed = min(1.15, max(.8, duration / 4.1))
                continue
            break
        sf.write(directory / 'speech-untrimmed.wav', raw, 24000, subtype='PCM_16')
        sf.write(directory / 'speech-trimmed.wav', samples, 24000, subtype='PCM_16')
        # Pitch-preserving minor adjustment only. A sentence that cannot fit
        # naturally fails here instead of dropping a word or racing the voice.
        tempo = max(.85, duration / 3.6) if duration < 3.5 else max(1.0, duration / 4.4)
        if tempo > 1.15:
            raise ValueError(f'Checkpoint needs shorter wording ({duration:.2f}s): {request["node_id"]}')
        run(['ffmpeg', '-v', 'error', '-y', '-i', directory / 'speech-trimmed.wav',
             '-af', f'atempo={tempo:.8f},adelay=80,apad', '-t', request['target_seconds'],
             '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', directory / 'speech.wav'])
        actual = sf.info(directory / 'speech.wav').duration
        save(directory / 'speech.json', {'spec_sha256': request['spec_sha256'],
             'sha256': sha(directory / 'speech.wav'), 'generation_sha256': digest(generation),
             'generation_spec': generation, 'spoken_text': request['source_public_response'],
             'model': 'hexgrad/Kokoro-82M', 'voice': request['voice'], 'speed': speed,
             'tempo': tempo, 'edge_trim': trim, 'duration_seconds': actual,
             'speech_seconds_before_padding': duration / tempo, 'human_review': 'pending'})
        print(json.dumps({'node_id': request['node_id'], 'audio_seconds': actual,
                          'speech_seconds': round(duration / tempo, 3)}), flush=True)


class ASR:
    def __init__(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16',
            cpu_threads=2, download_root=str(ROOT / '.local_models/faster-whisper'), local_files_only=True)

    def render(self, path):
        from scripts.screen_annotation400_av import speech_normalized, critical_content_matches
        from offline.revision_checks import ASR_SCREEN_VERSION, audio_evidence_valid
        request_sha_before = sha(path)
        request = load(path)
        directory = safe_path(path.parent)
        audio = directory / 'speech.wav'
        audio_sha_before = sha(audio)
        segments, info = self.model.transcribe(str(audio), beam_size=5, vad_filter=False,
                                              condition_on_previous_text=False)
        transcript = ''.join(x.text for x in segments).strip()
        expected = request['source_public_response']
        similarity = SequenceMatcher(None, speech_normalized(expected), speech_normalized(transcript), autojunk=False).ratio()
        critical = critical_content_matches(expected, transcript)
        audio_sha_after, request_sha_after = sha(audio), sha(path)
        stable = audio_sha_before == audio_sha_after and request_sha_before == request_sha_after
        result = {'version': ASR_SCREEN_VERSION, 'spec_sha256': request['spec_sha256'],
                  'sha256': audio_sha_before, 'input_stable': stable,
                  'input_sha256_before': audio_sha_before, 'input_sha256_after': audio_sha_after,
                  'request_sha256_before': request_sha_before, 'request_sha256_after': request_sha_after,
                  'expected': expected, 'transcript': transcript, 'language': info.language,
                  'normalized_similarity': similarity, 'critical_content_match': critical,
                  'model': 'large-v3-turbo', 'unprompted': True,
                  'machine_screen_passed': True,
                  'human_review': 'pending'}
        result['machine_screen_passed'] = audio_evidence_valid(result)
        save(directory / 'audio_screen.json', result)
        print(json.dumps({'node_id': request['node_id'], **result}), flush=True)
        if not stable:
            raise ValueError('ASR input changed during checking; the result is invalid')


class Motion:
    def __init__(self):
        from scripts.animate_annotation400_local import Animator, TOOL
        self.animator = Animator()
        config = self.animator.config
        paths = [getattr(config, 'checkpoint_' + key) for key in ('F', 'M', 'G', 'W', 'S')]
        paths.extend([config.models_config, self.animator.cropper.crop_cfg.landmark_ckpt_path])
        paths.extend(Path(self.animator.cropper.crop_cfg.insightface_root).rglob('*.onnx'))
        paths.extend(TOOL / path for path in ('src/live_portrait_wrapper.py', 'src/config/inference_config.py',
            'src/config/crop_config.py', 'src/utils/cropper.py', 'src/utils/crop.py',
            'src/utils/resources/mask_template.png', 'src/utils/resources/lip_array.pkl'))
        self.dependencies = file_fingerprints(paths)
        # Match the official thresholded normalization: don't alter an already
        # closed natural mouth before the speech model generates articulation.
        wrapper = self.animator.wrapper
        original_retarget = wrapper.retarget_lip
        wrapper.retarget_lip = lambda keypoints, ratio: (original_retarget(keypoints, ratio)
            if float(ratio[0][0]) >= config.lip_normalize_threshold
            else self.animator.torch.zeros_like(keypoints))

    def render(self, path):
        # Reuse the established application of public controls; all changes are
        # local to this process, without editing the frozen renderer or assets.
        import scripts.animate_annotation400_local as original
        import offline.revision_motion as motion
        import soundfile as sf
        request = load(path)
        directory = safe_path(path.parent)
        if sha(ROOT / request['identity']['identity_path']) != request['identity']['identity_sha256']:
            raise ValueError('Identity source changed')
        duration = sf.info(directory / 'speech.wav').duration
        original.controls = lambda req, t: motion.revision_controls(req, t, duration)
        original.CONTROLS_VERSION = motion.PROFILE_VERSION
        original.CONTROLS_SOURCE_SHA256 = digest({'application': sha(Path(original.__file__)),
                                                'profile': sha(Path(motion.__file__)),
                                                'renderer': implementation(Motion),
                                                'dependencies': self.dependencies})
        self.animator.render(path)
        receipt = load(directory / 'motion.json')
        receipt['dependencies'] = self.dependencies
        receipt['lip_normalization'] = 'source_ratio_at_least_0.03'
        save(directory / 'motion.json', receipt)


class Video:
    def __init__(self, steps=40, guidance=None):
        from scripts.lipsync_annotation400_local import Renderer, TOOL
        self.base = Renderer()
        self.base.helper.disable()
        self.tool, self.steps, self.guidance = TOOL, steps, guidance
        self.dependencies = file_fingerprints(TOOL / path for path in (
            'checkpoints/vae/diffusion_pytorch_model.safetensors', 'checkpoints/vae/config.json',
            'checkpoints/whisper/tiny.pt', 'configs/scheduler_config.json',
            'latentsync/pipelines/lipsync_pipeline.py', 'latentsync/models/unet.py',
            'latentsync/whisper/audio2feature.py', 'latentsync/utils/util.py',
            'latentsync/utils/affine_transform.py'))
        # Input is already 25fps. Skip the upstream's redundant lossy encode.
        import latentsync.pipelines.lipsync_pipeline as pipeline_module
        from latentsync.utils.util import read_video
        pipeline_module.read_video = lambda path, **kwargs: read_video(path, **{**kwargs, 'change_fps': False})

    def render(self, path):
        request = load(path)
        directory = safe_path(path.parent)
        speech, motion = directory / 'speech.wav', directory / 'motion.mp4'
        screen = load(directory / 'audio_screen.json')
        if (not screen['machine_screen_passed'] or screen['sha256'] != sha(speech)
                or screen['spec_sha256'] != request['spec_sha256']
                or screen['expected'] != request['source_public_response']):
            raise ValueError('Independent speech check has not passed: ' + request['node_id'])
        motion_receipt = load(directory / 'motion.json')
        if (motion_receipt['spec_sha256'] != request['spec_sha256']
                or motion_receipt['audio_sha256'] != sha(speech)
                or motion_receipt['sha256'] != sha(motion)
                or motion_receipt['identity_sha256'] != request['identity']['identity_sha256']):
            raise ValueError('Motion is not bound to this checkpoint and waveform')
        source_video = load((ROOT / request['source_request_path']).with_name('video.json'))
        settings_path = REVISION / 'render-settings.json'
        settings = load(settings_path).get('nodes', {}) if settings_path.exists() else {}
        guidance = self.guidance if self.guidance is not None else settings.get(
            request['node_id'], {}).get('guidance_scale', source_video['guidance_scale'])
        repair_path = directory / 'render-repair.json'
        if self.guidance is None and repair_path.exists():
            repair = load(repair_path)
            if repair.get('spec_sha256') == request['spec_sha256']:
                guidance = repair['guidance_scale']
        if guidance not in (1.0, 1.5, 2.0):
            raise ValueError('Unsupported guidance scale')
        mask = self.tool / self.base.config.data.mask_image_path
        seed = int(request['source_spec_sha256'][:8], 16) % (2 ** 31)
        generation = {'version': VERSION, 'source_sha256': implementation(Video),
            'spec_sha256': request['spec_sha256'], 'audio_sha256': sha(speech),
            'motion_sha256': sha(motion), 'motion_source_sha256': motion_receipt['controls_source_sha256'],
            'model_sha256': self.base.model_sha256, 'mask_sha256': sha(mask),
            'dependencies': self.dependencies,
            'config_sha256': sha(self.tool / 'configs/unet/stage2_512.yaml'),
            'steps': self.steps, 'deepcache': False, 'guidance_scale': guidance, 'seed': seed}
        if current(directory, 'video', generation):
            return
        if (directory / 'video.mp4').exists():
            import shutil
            history = directory / 'video_history' / sha(directory / 'video.mp4')
            history.mkdir(parents=True, exist_ok=True)
            for name in ('video.mp4', 'video.json', 'lipsync_screen.json'):
                if (directory / name).exists() and not (history / name).exists():
                    shutil.copy2(directory / name, history / name)
        runtime = directory / 'runtime'
        runtime.mkdir(exist_ok=True)
        for name in ('checkpoints', 'configs'):
            link = runtime / name
            if not link.exists():
                link.symlink_to(self.tool / name, target_is_directory=True)
        previous = Path.cwd()
        try:
            os.chdir(runtime)
            self.base.torch.manual_seed(seed)
            raw = runtime / 'synced.mp4'
            self.base.pipeline(video_path=str(motion), audio_path=str(speech), video_out_path=str(raw),
                num_frames=self.base.config.data.num_frames, num_inference_steps=self.steps,
                guidance_scale=guidance, weight_dtype=self.base.torch.float16,
                width=self.base.config.data.resolution, height=self.base.config.data.resolution,
                mask_image_path=str(mask), temp_dir=str(runtime / 'render-temp'))
            run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-i', speech, '-map', '0:v:0',
                 '-map', '1:a:0', '-vf', 'tpad=stop_mode=clone:stop_duration=0.16',
                 '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-t', request['target_seconds'],
                 '-movflags', '+faststart', directory / 'video.mp4'])
        finally:
            os.chdir(previous)
        metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                    '-show_format', '-of', 'json', str(directory / 'video.mp4')]))
        video = next(x for x in metadata['streams'] if x['codec_type'] == 'video')
        audio = next(x for x in metadata['streams'] if x['codec_type'] == 'audio')
        if not 4 <= float(metadata['format']['duration']) <= 5 or abs(float(video['duration']) - float(audio['duration'])) > .1:
            raise ValueError('Invalid checkpoint media duration')
        save(directory / 'video.json', {'spec_sha256': request['spec_sha256'],
            'sha256': sha(directory / 'video.mp4'), 'audio_sha256': sha(speech), 'motion_sha256': sha(motion),
            'generation_sha256': digest(generation), 'generation_spec': generation,
            'spoken_text': request['source_public_response'], 'human_review': 'pending',
            'structural_metadata': {'duration_seconds_actual': float(metadata['format']['duration']),
                                    'video_duration_seconds': float(video['duration']),
                                    'audio_duration_seconds': float(audio['duration'])}})
        print(json.dumps({'node_id': request['node_id'], 'video': str(directory / 'video.mp4')}), flush=True)


class Sync:
    def __init__(self):
        from scripts.audit_annotation400_lipsync import TOOL
        sys.path.insert(0, str(TOOL))
        from eval.syncnet import SyncNetEval
        self.tool = TOOL
        self.model = SyncNetEval(device='cuda')
        self.weights = TOOL / 'checkpoints/auxiliary/syncnet_v2.model'
        self.model.loadParameters(str(self.weights))
        self.detector = None

    @staticmethod
    def media_shape(path):
        data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames',
            '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames,avg_frame_rate',
            '-of', 'json', str(path)]))['streams'][0]
        numerator, denominator = map(int, data['avg_frame_rate'].split('/'))
        return int(data['nb_read_frames']), numerator / denominator

    @staticmethod
    def audio_frame_count(path):
        # Match the evaluator's 16kHz PCM decode and floor(samples / 640).
        audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path),
            '-async', '1', '-ac', '1', '-vn', '-ar', '16000', '-f', 's16le', 'pipe:1'])
        return (len(audio) // 2) // 640

    def detect_tracks(self, video):
        """Capture original detections before upstream tracking consumes them."""
        if self.detector is None:
            from eval.syncnet_detect import SyncNetDetector
            self.detector = SyncNetDetector(device='cuda', detect_results_dir='detect_results')
        detector = self.detector
        original_detect, original_crop = detector.detect_face, detector.crop_video
        detections, captured = {}, {'decoded_frame_count': 0, 'tracks': []}

        def detect(*args, **kwargs):
            faces = original_detect(*args, **kwargs)
            captured['decoded_frame_count'] = len(faces)
            for frame_faces in faces:
                for face in frame_faces:
                    detections.setdefault(int(face['frame']), []).append(list(map(float, face['bbox'])))
            return faces

        def crop(track, cropfile, *args, **kwargs):
            result = original_crop(track, cropfile, *args, **kwargs)
            frames = list(map(int, track['frame']))
            actual = [frame for frame, box in zip(frames, track['bbox'])
                      if any(len(box) == len(source) and all(abs(float(x) - y) <= 1e-7
                             for x, y in zip(box, source)) for source in detections.get(frame, []))]
            captured['tracks'].append({'track_id': Path(cropfile).name, 'frame_indices': frames,
                'detected_frame_indices': actual, 'interpolated_frame_indices': sorted(set(frames) - set(actual))})
            return result

        detector.detect_face, detector.crop_video = detect, crop
        try:
            detector(video_path=str(video), min_track=50)
        finally:
            detector.detect_face, detector.crop_video = original_detect, original_crop
        captured['detected_frame_indices'] = sorted(detections)
        return captured

    def render(self, path):
        from offline.revision_checks import (SYNC_SCREEN_VERSION, sync_coverage,
                                             sync_window_evidence, sync_evidence_valid)
        request_sha_before = sha(path)
        request = load(path)
        directory = safe_path(path.parent)
        video = directory / 'video.mp4'
        video_sha_before = sha(video)
        source_frames, source_fps = self.media_shape(video)
        runtime = directory / 'syncnet-runtime'
        runtime.mkdir(exist_ok=True)
        if not (runtime / 'checkpoints').exists():
            (runtime / 'checkpoints').symlink_to(self.tool / 'checkpoints', target_is_directory=True)
        previous = Path.cwd()
        try:
            os.chdir(runtime)
            detected = self.detect_tracks(video)
            tracks = detected['tracks']
            crops = {p.stem for p in Path('detect_results/crop').glob('*.mp4')}
            if crops != {track['track_id'] for track in tracks}:
                raise ValueError('Detected crop files do not match the captured tracks')
            for track in tracks:
                crop = Path('detect_results/crop') / (track['track_id'] + '.mp4')
                crop_sha_before = sha(crop)
                crop_frames, crop_fps = self.media_shape(crop)
                if crop_fps != 25:
                    raise ValueError('SyncNet crop is not 25fps')
                window = sync_window_evidence(track['frame_indices'], crop_frames, self.audio_frame_count(crop))
                offset, _, confidence = self.model.evaluate(video_path=str(crop), temp_dir=str(runtime / 'temp'))
                crop_sha_after = sha(crop)
                track.update(crop_sha256=crop_sha_before, crop_frame_count=crop_frames,
                    input_sha256_before=crop_sha_before, input_sha256_after=crop_sha_after,
                    input_stable=crop_sha_before == crop_sha_after, model_window=window,
                    offset_frames=int(offset), confidence=float(confidence))
        finally:
            os.chdir(previous)
        video_sha_after, request_sha_after = sha(video), sha(path)
        stable = (video_sha_before == video_sha_after and request_sha_before == request_sha_after
                  and all(track['input_stable'] for track in tracks))
        coverage = sync_coverage(source_frames, detected['decoded_frame_count'],
                                 detected['detected_frame_indices'], tracks, source_fps)
        result = {'version': SYNC_SCREEN_VERSION, 'spec_sha256': request['spec_sha256'],
                  'video_sha256': video_sha_before, 'model_sha256': sha(self.weights),
                  'input_stable': stable, 'input_sha256_before': video_sha_before,
                  'input_sha256_after': video_sha_after, 'request_sha256_before': request_sha_before,
                  'request_sha256_after': request_sha_after, 'coverage': coverage, 'tracks': tracks,
                  'complete_clip': coverage['fully_tracked'] and coverage['fully_detected'],
                  'offset_frames': max(tracks, key=lambda t: abs(t['offset_frames']))['offset_frames'] if tracks else None,
                  'confidence': min(t['confidence'] for t in tracks) if tracks else None,
                  'machine_screen_passed': True, 'human_review': 'pending'}
        result['machine_screen_passed'] = sync_evidence_valid(result)
        save(directory / 'lipsync_screen.json', result)
        print(json.dumps({'node_id': request['node_id'], 'version': SYNC_SCREEN_VERSION,
                          'complete_clip': result['complete_clip'], 'tracks': len(tracks),
                          'confidence': result['confidence'], 'offset_frames': result['offset_frames'],
                          'machine_screen_passed': result['machine_screen_passed']}), flush=True)
        if not stable:
            raise ValueError('Synchronization input changed during checking; the result is invalid')


class Render:
    """One shard holds its models and finishes each checkpoint before the next."""
    def __init__(self, steps=40, guidance=None):
        self.motion = Motion()
        self.video = Video(steps, guidance)
        self.sync = Sync()

    def render(self, path):
        self.motion.render(path)
        self.video.render(path)
        self.sync.render(path)
        directory = path.parent
        screen = load(directory / 'lipsync_screen.json')
        generation = load(directory / 'video.json')['generation_spec']
        if not screen['machine_screen_passed'] and generation['guidance_scale'] == 1.0:
            # One bounded repair, keeping the failed candidate and its score.
            # Stronger settings are never escalated without a separate review.
            save(directory / 'render-repair.json', {
                'spec_sha256': load(path)['spec_sha256'], 'guidance_scale': 1.5,
                'reason': 'Initial full-clip synchronization check failed at guidance 1.0',
                'previous_screen': screen})
            self.video.render(path)
            self.sync.render(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'audio', 'asr', 'motion', 'video', 'sync', 'render'])
    parser.add_argument('--lines', type=Path, nargs='+')
    parser.add_argument('--manifest', type=Path, default=REVISION / 'manifest.json')
    parser.add_argument('--node-id', nargs='*')
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--steps', type=int, default=40)
    parser.add_argument('--guidance', type=float)
    args = parser.parse_args()
    safe_path(args.manifest)
    if args.phase == 'prepare':
        if not args.lines:
            parser.error('prepare requires --lines')
        return prepare(args.lines, args.manifest)
    if not 0 <= args.shard < args.shards or not 20 <= args.steps <= 50:
        parser.error('Invalid shard or quality settings')
    selected = []
    for index, row in enumerate(load(args.manifest)['nodes']):
        if index % args.shards == args.shard and (not args.node_id or row['node_id'] in args.node_id):
            selected.append((row, validate_request(row)))
    worker = {'audio': Speech, 'asr': ASR, 'motion': Motion, 'video': lambda: Video(args.steps, args.guidance),
              'sync': Sync, 'render': lambda: Render(args.steps, args.guidance)}[args.phase]()
    failures = []
    for row, path in selected:
        try:
            worker.render(path)
        except Exception as error:
            failure = {'node_id': row['node_id'], 'phase': args.phase,
                       'error': str(error), 'request_path': str(path)}
            failures.append(failure)
            print(json.dumps(failure), flush=True)
            traceback.print_exc()
    save(safe_path(args.manifest.with_name(f'{args.manifest.stem}-{args.phase}-{args.shard}-failures.json')), failures)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
