"""Deterministic public-only motion for isolated annotation video revisions.

This module returns the existing renderer's seven controls; it does not load a
model, alter media, or read private state. Phrase boundaries are seconds from the
public utterance's audio. They are optional timing hints, never emotional cues.
"""
from functools import lru_cache
import hashlib
import math
import random

from scripts.animate_annotation400_local import public_motion_cues

PROFILE_VERSION = 'public_revision_motion_v3'
# Visual amplitude calibration after comparing the same source identity at
# 0/-4/-8/-10. This changes visibility of an already public cue, never adds an
# emotion. Keep the exact node and cue together; it is not a scene-wide default.
CALIBRATION_VERSION = 'public_brief_tension_amplitude_001_v1'
_CALIBRATED_BRIEF_TENSION = {'GPT50_001-t1-e30dc6556d3865ac': 8.0}
# Keep the sampled blink/pose timing stable when tuning only expression strength.
_SCHEDULE_VERSION = 'public_revision_motion_v1'


def _rng(node_id, channel):
    seed = hashlib.sha256((_SCHEDULE_VERSION + '\0' + node_id + '\0' + channel).encode()).digest()
    return random.Random(int.from_bytes(seed[:16], 'big'))


def _ease(value):
    """C2 continuous interpolation, including at either endpoint."""
    value = max(0.0, min(1.0, value))
    return value ** 3 * (value * (value * 6.0 - 15.0) + 10.0)


def _pulse(t, center, attack, release):
    if t <= center:
        return _ease((t - center + attack) / attack)
    return 1.0 - _ease((t - center) / release)


def _near_boundary(target, boundaries, tolerance):
    candidates = [value for value in boundaries if abs(value - target) <= tolerance]
    return min(candidates, key=lambda value: abs(value - target)) if candidates else target


@lru_cache(maxsize=512)
def _schedule(node_id, duration, boundaries):
    # Separate random streams prevent a gaze or an eyebrow edit from resetting
    # the blink pattern. Every event is generated once, with no modulo cycles.
    rng = _rng(node_id, 'blinks')
    blinks = []
    next_blink = min(rng.uniform(1.2, 2.8), duration * .48)
    while .25 < next_blink < duration - .3:
        center = _near_boundary(next_blink, boundaries, .25)
        if .25 < center < duration - .3 and (not blinks or center - blinks[-1][0] > 1.7):
            blinks.append((center, rng.uniform(.08, .11), rng.uniform(.14, .21)))
        # The current 4–5 s sentence checkpoints need at most one blink.
        # Keep a little headroom for encoded frame/audio-tail rounding.
        if duration <= 5.5:
            break
        next_blink += rng.uniform(2.3, 5.7)

    poses = []
    for channel, limit in (('pitch', .22), ('yaw', .35), ('roll', .16)):
        rng = _rng(node_id, channel)
        knots = [(0.0, 0.0)]
        time = rng.uniform(1.1, 1.8)
        while time < duration - .8:
            knots.append((time, rng.uniform(-limit, limit)))
            time += rng.uniform(1.6, 3.1)
        knots.append((duration, 0.0))
        poses.append(tuple(knots))

    actions = []
    for channel, start, stop in (('nod', .25, .55), ('tilt', .35, .65), ('gaze', .4, .7), ('face', .2, .4)):
        target = duration * _rng(node_id, channel).uniform(start, stop)
        eligible = tuple(value for value in boundaries if duration * .15 < value < duration * .82)
        actions.append(_near_boundary(target, eligible, min(1.2, duration * .12)))
    return tuple(blinks), tuple(poses), tuple(actions)


def _pose(t, knots):
    for (start, left), (end, right) in zip(knots, knots[1:]):
        if t <= end:
            return left + (right - left) * _ease((t - start) / (end - start))
    return knots[-1][1]


def revision_controls(request, t, duration, phrase_boundaries=()):
    """Return bounded controls at ``t`` seconds without using hidden evidence.

    Explicit nod/tilt/gaze cues occur once during the utterance, and settle back
    to the source pose. Neutral idle movement is small and non-periodic. Only
    cues selected by the existing negation-aware, two-class public parser can
    affect expression or gaze. A sustained state stays present at the end;
    only an explicitly brief or relaxing cue releases its tension. Identifiers
    seed variation; private fields and spec hashes are excluded from the profile.
    """
    duration, t = float(duration), float(t)
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(t):
        raise ValueError('Motion time must be finite and duration must be positive')
    boundaries = tuple(float(value) for value in phrase_boundaries)
    if not all(math.isfinite(value) for value in boundaries):
        raise ValueError('Phrase boundaries must be finite seconds')
    boundaries = tuple(sorted(set(value for value in boundaries if 0 < value < duration)))
    t = max(0.0, min(duration, t))
    public_request = {'source_observable_expression': request['source_observable_expression']}
    cues = public_motion_cues(public_request)
    node_id = str(request.get('node_id', 'public-portrait'))
    blinks, poses, (nod_time, tilt_time, gaze_time, face_time) = _schedule(node_id, duration, boundaries)
    blink = max((_pulse(t, center, attack, release) for center, attack, release in blinks), default=0.0)
    pitch, yaw, roll = (_pose(t, knots) for knots in poses)
    if cues['nod']:
        pitch += 1.8 * _pulse(t, nod_time, min(.45, duration * .12), min(.7, duration * .18))
    if cues['head_tilt']:
        roll += 1.15 * _pulse(t, tilt_time, min(.85, duration * .18), min(1.3, duration * .25))
    glance = _pulse(t, gaze_time, min(.6, duration * .12), min(1.1, duration * .22))
    eyebrow = 0.0
    phase = t / duration
    # The official LivePortrait eyebrow UI spans [-30, 30]. Defaults use about
    # 10–13% of that range. An explicitly audited identity may have a separately
    # versioned amplitude calibration; no smile/surprise controls are introduced.
    if cues['eyebrow'] == 'brief_tension':
        strength = _CALIBRATED_BRIEF_TENSION.get(node_id, 4.0)
        eyebrow = -strength * _pulse(t, face_time, min(.7, duration * .16), min(1.4, duration * .28))
    elif cues['eyebrow'] == 'tension':
        # A tense state does not imply later relief. Settle into the state,
        # then hold it through the ending instead of inventing relaxation.
        eyebrow = -3.2 * _ease(phase / .2)
    elif cues['eyebrow'] == 'relaxing':
        # Begin with the supported tension and release it gradually. Building
        # fresh tension first would contradict a cue that already says easing.
        eyebrow = -3.5 * (1.0 - _ease((phase - .08) / .77))
    return {'eyebrow': eyebrow, 'blink': blink,
            'gaze_x': 2.2 * glance if cues['look_away'] else 0.0,
            'gaze_y': -2.2 * glance if cues['look_down'] else 0.0,
            'pitch': pitch, 'yaw': yaw, 'roll': roll}
