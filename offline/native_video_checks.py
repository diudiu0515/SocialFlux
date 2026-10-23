"""Native-video ASR and complete-track sync checks; no rendering dependency."""
from pathlib import Path
from difflib import SequenceMatcher
import hashlib
import json
import os
import subprocess
import sys
from shared.artifacts import atomic_json as save
ROOT = Path(__file__).resolve().parents[1]
def load(path):
    return json.loads(Path(path).read_text())
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_path(path):
    path = Path(path).resolve()
    if not any(path.is_relative_to(p) for p in [ROOT / 'data/seedance_state_v2_20261023', ROOT / 'data/gpt50/experiment/seedance_state_online_v4']):
        raise ValueError('Native QA writes must remain in the new revision')
    return path

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

class Sync:
    def __init__(self):
        TOOL = ROOT / ".local_tools/annotation400-latentsync"
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
