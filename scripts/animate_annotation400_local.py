"""Subtle, public-cue portrait motion for the original fictional characters.

Uses the official LivePortrait wrapper and its documented retargeting controls.
Rendering inputs are the frozen public-only requests. Full-body actions are not
invented: this renderer selects facial expression and gaze, with an optional
small nod only when the public observable description explicitly includes one.
"""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha

TOOL = ROOT / '.local_tools/annotation400-liveportrait-code'
FPS = 25
CONTROLS_VERSION = 'public_motion_cues_v2'
# Include the renderer itself so any change to the application of these public
# controls also invalidates cached motion. The audit preserves the old source.
CONTROLS_SOURCE_SHA256 = sha(Path(__file__))


def affirmed(pattern, text):
    """Recognize an explicit positive cue, respecting local clause negation."""
    for match in re.finditer(pattern, text.lower()):
        prefix = re.split(r'[.!?;,:]|\b(?:but|then|however)\b', text[:match.start()].lower())[-1]
        if not re.search(r"\b(?:no|not|never|without|cannot)\b|n't\b", prefix):
            return True
    return False


def public_motion_cues(request):
    """Select at most two supported cue classes from public descriptions only.

    A neutral face consumes no slot. Explicit facial changes take priority,
    followed by a nod or head tilt, then gaze; body and hand actions are omitted.
    """
    expression = request['source_observable_expression']
    face = expression.get('facial_expression', '').lower()
    behaviors = expression.get('behavioral_cues', [])
    face_and_behavior = '; '.join([face, *behaviors]).lower()
    eyebrow = None
    if 'brief' in face and affirmed(r'\b(?:tight\w*|tens\w*)\b', face):
        eyebrow = 'brief_tension'
    elif affirmed(r'\b(?:relax\w*|easing|relief|relieved)\b', face):
        eyebrow = 'relaxing'
    elif affirmed(r'\b(?:tense|tension|concern\w*|frown\w*|furrow\w*)\b', face):
        eyebrow = 'tension'
    nod = affirmed(r'\bnod(?:s|ded|ding)?\b', face_and_behavior)
    tilt = affirmed(r'\bhead\s+tilt\b|\btilt(?:s|ed|ing)?\s+(?:(?:the|her|his|their)\s+)?head\b',
                    face_and_behavior)
    # Only behaviors explicitly describing looking/attention become gaze input;
    # mentions of notes in a hand action do not imply a new glance.
    gaze_fields = [expression.get('gaze', '')]
    gaze_fields.extend(b for b in behaviors if re.search(
        r'\b(?:look(?:s|ed|ing)?|glanc(?:e|es|ed|ing)|gaze|attention)\b|\beye contact\b', b.lower()))
    gaze = '; '.join(gaze_fields).lower()
    look_down = affirmed(r'\b(?:notes?|desk|screen|records?|documents?|documentation|down\w*|'
                         r'workbench|workstation|materials?|agenda|papers?)\b', gaze)
    look_away = affirmed(r'\b(?:away|aside|side|shift(?:s|ed|ing)?|alternat(?:e|es|ed|ing))\b', gaze_fields[0])
    # A behavior such as "shifts attention back to the record" supplies a
    # document glance, not an additional sideways movement.
    look_away = look_away or affirmed(r'\b(?:away|aside|side|alternat(?:e|es|ed|ing))\b',
                                     '; '.join(gaze_fields[1:]))
    selected = []
    if eyebrow:
        selected.append('facial_expression')
    if nod:
        selected.append('nod')
    elif tilt:
        selected.append('head_tilt')
    if (look_down or look_away) and len(selected) < 2:
        selected.append('gaze')
    return {'selected_cues': selected, 'eyebrow': eyebrow,
            'nod': nod and 'nod' in selected, 'head_tilt': tilt and 'head_tilt' in selected,
            'look_down': look_down and 'gaze' in selected, 'look_away': look_away and 'gaze' in selected}


def controls(request, t):
    cues = public_motion_cues(request)
    pulse = math.exp(-((t - 1.2) / 0.7) ** 2)
    eyebrow = 0.0
    if cues['eyebrow'] == 'brief_tension':
        eyebrow = -2.5 * pulse
    elif cues['eyebrow'] == 'relaxing':
        eyebrow = -1.3 * math.exp(-t / 1.8)
    elif cues['eyebrow'] == 'tension':
        eyebrow = -1.0
    phase = (t % 4.1) - 2.7
    blink = math.exp(-(phase / 0.09) ** 2)
    glance = math.exp(-(((t % 6.5) - 4.0) / 0.8) ** 2)
    nod = 2.0 * math.sin(math.pi * (t - 0.7) / 1.1) ** 2 if cues['nod'] and 0.7 < t < 1.8 else 0.0
    tilt = 1.4 * math.exp(-((t - 1.4) / .8) ** 2) if cues['head_tilt'] else 0.0
    return {'eyebrow': eyebrow, 'blink': blink,
            'gaze_x': 3.0 * glance if cues['look_away'] else 0.0,
            'gaze_y': -3.0 * glance if cues['look_down'] else 0.0,
            'pitch': nod + 0.15 * math.sin(t * 1.1),
            'yaw': 0.2 * math.sin(t * 0.7), 'roll': tilt + 0.1 * math.sin(t * 0.5)}


class Animator:
    def __init__(self):
        sys.path.insert(0, str(TOOL))
        import torch
        from src.config.inference_config import InferenceConfig
        from src.config.crop_config import CropConfig
        from src.live_portrait_wrapper import LivePortraitWrapper
        from src.utils.cropper import Cropper
        self.config = InferenceConfig()
        self.wrapper = LivePortraitWrapper(self.config)
        self.cropper = Cropper(crop_cfg=CropConfig())
        self.torch = torch

    def render(self, request_path):
        import cv2
        import numpy as np
        import soundfile as sf
        from src.utils.crop import prepare_paste_back, paste_back
        from src.utils.camera import get_rotation_matrix
        from src.utils.retargeting_utils import calc_eye_close_ratio
        request = load(request_path)
        audio = request_path.parent / 'speech.wav'
        info = sf.info(audio)
        frame_count = math.ceil(info.duration * FPS)
        target = request_path.parent / 'motion.mp4'
        receipt = target.with_suffix('.json')
        if receipt.exists() and target.exists():
            old = load(receipt)
            if (old['spec_sha256'] == request['spec_sha256'] and old['audio_sha256'] == sha(audio)
                    and old['sha256'] == sha(target) and old.get('controls_version') == CONTROLS_VERSION
                    and old.get('controls_source_sha256') == CONTROLS_SOURCE_SHA256):
                return
        identity = ROOT / request['identity']['identity_path']
        assert sha(identity) == request['identity']['identity_sha256']
        image = cv2.cvtColor(cv2.imread(str(identity)), cv2.COLOR_BGR2RGB)
        # Preserve the original frame and its background outside the face crop.
        crop = self.cropper.crop_source_image(image, self.cropper.crop_cfg)
        assert crop is not None, request['node_id']
        wrapper = self.wrapper
        mask = prepare_paste_back(self.config.mask_crop, crop['M_c2o'], dsize=(image.shape[1], image.shape[0]))
        with self.torch.inference_mode():
            source = wrapper.prepare_source(crop['img_crop_256x256'])
            source_info = wrapper.get_kp_info(source)
            features = wrapper.extract_feature_3d(source)
            source_kp = wrapper.transform_keypoint(source_info)
            eye_ratio = float(calc_eye_close_ratio(crop['lmk_crop'][None]).mean())
            lip_ratio = wrapper.calc_combined_lip_ratio([[0.01]], crop['lmk_crop'])
            closed_lips = wrapper.retarget_lip(source_kp, lip_ratio)
            command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                       '-s', f'{image.shape[1]}x{image.shape[0]}', '-r', str(FPS), '-i', '-', '-an',
                       '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)]
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
            try:
                for index in range(frame_count):
                    c = controls(request, index / FPS)
                    rotation = get_rotation_matrix(source_info['pitch'] + c['pitch'], source_info['yaw'] + c['yaw'], source_info['roll'] + c['roll'])
                    expression = source_info['exp'].clone()
                    eyebrow = c['eyebrow']
                    # Official LivePortrait eyebrow/gaze controls, kept subtle.
                    expression[0, 1, 0] -= eyebrow * 0.001
                    expression[0, 2, 0] += eyebrow * 0.001
                    expression[0, 1, 1] += eyebrow * 0.0003
                    expression[0, 2, 1] -= eyebrow * 0.0003
                    expression[0, 11, 0] += c['gaze_x'] * 0.0007
                    expression[0, 15, 0] += c['gaze_x'] * 0.001
                    expression[0, 11, 1] -= c['gaze_y'] * 0.0005
                    expression[0, 15, 1] -= c['gaze_y'] * 0.0005
                    driven = source_info['scale'] * (source_info['kp'] @ rotation + expression) + source_info['t']
                    eye = wrapper.calc_combined_eye_ratio([[max(0.02, eye_ratio * (1 - 0.92 * c['blink']))]], crop['lmk_crop'])
                    driven += wrapper.retarget_eye(source_kp, eye) + closed_lips
                    driven = wrapper.stitching(source_kp, driven)
                    decoded = wrapper.warp_decode(features, source_kp, driven)
                    face = wrapper.parse_output(decoded['out'])[0]
                    result = paste_back(face, crop['M_c2o'], image, mask)
                    encoder.stdin.write(np.ascontiguousarray(result).tobytes())
                encoder.stdin.close()
                assert encoder.wait() == 0
            except BaseException:
                encoder.kill()
                encoder.wait()
                raise
        save(receipt, {'spec_sha256': request['spec_sha256'], 'sha256': sha(target),
            'audio_sha256': sha(audio), 'identity_sha256': sha(identity),
            'method': 'LivePortrait_public_cues_v1', 'frames': frame_count, 'fps': FPS,
            'controls_version': CONTROLS_VERSION, 'controls_source_sha256': CONTROLS_SOURCE_SHA256,
            'selected_cues': public_motion_cues(request)['selected_cues'],
            'baseline_motion': 'subtle_blink_and_head_micro_motion',
            'body_action_synthesis': False, 'human_review': 'pending'})
        print(json.dumps({'node_id': request['node_id'], 'motion_frames': frame_count}), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scene', nargs='*')
    p.add_argument('--location', nargs='*')
    p.add_argument('--node-id', nargs='*')
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    a = p.parse_args()
    animator = Animator()
    for index, row in enumerate(load(OUT / 'local_av/manifest.json')['nodes']):
        if index % a.shards != a.shard or (a.scene and row['scenario_id'] not in a.scene):
            continue
        if a.node_id and row['node_id'] not in a.node_id:
            continue
        path = ROOT / row['request_path']
        if a.location and load(path)['location'] not in a.location:
            continue
        animator.render(path)


if __name__ == '__main__':
    main()
