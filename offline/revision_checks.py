"""CPU-only evidence contracts for independent checkpoint media checks.

These validate receipts, not the current files. Consumers must also bind each
receipt to the actual media SHA, request spec and public checkpoint text.
"""
import math

ASR_SCREEN_VERSION = 'checkpoint_asr_stable_v2'
SYNC_SCREEN_VERSION = 'checkpoint_sync_tracks_v2'


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _stable(receipt, media_key):
    value = receipt.get(media_key)
    return (_sha(value) and receipt.get('input_stable') is True
            and receipt.get('input_sha256_before') == value == receipt.get('input_sha256_after')
            and _sha(receipt.get('request_sha256_before'))
            and receipt.get('request_sha256_before') == receipt.get('request_sha256_after'))


def audio_evidence_valid(receipt):
    """Whether a new ASR receipt proves stable inputs and passing speech checks."""
    return (isinstance(receipt, dict) and receipt.get('version') == ASR_SCREEN_VERSION
            and _stable(receipt, 'sha256') and receipt.get('machine_screen_passed') is True
            and receipt.get('language') == 'en' and receipt.get('unprompted') is True
            and receipt.get('critical_content_match') is True
            and _number(receipt.get('normalized_similarity'))
            and .98 <= receipt['normalized_similarity'] <= 1)


def _frames(values, total=None):
    if (not isinstance(values, list) or any(type(x) is not int or x < 0 for x in values)
            or values != sorted(set(values))
            or (total is not None and any(x >= total for x in values))):
        raise ValueError('Frame indices must be sorted, unique, zero-based integers')
    return set(values)


def sync_window_evidence(frame_indices, crop_frame_count, audio_frame_count):
    """Describe this local SyncNet's actual five-frame feature windows.

    Its loop is range(min(video_frames, floor(audio_samples / 640)) - 5).
    Thus a full N-frame crop has N-5 windows and its final frame is not used.
    This model edge is disclosed separately; it never excuses a missing track
    frame, a missing face detection, or truncated crop audio.
    """
    _frames(frame_indices)
    if any(type(n) is not int or n < 0 for n in (crop_frame_count, audio_frame_count)):
        raise ValueError('Invalid model input lengths')
    if crop_frame_count != len(frame_indices):
        raise ValueError('Crop frame count differs from its recorded track')
    usable = min(crop_frame_count, audio_frame_count)
    count = max(0, usable - 5)
    used = frame_indices[:usable - 1] if count else []
    return {'window_size_frames': 5, 'video_frame_count': crop_frame_count,
            'audio_frame_count': audio_frame_count, 'usable_frame_count': usable,
            'window_count': count, 'window_start_frame_indices': frame_indices[:count],
            'feature_input_frame_indices': used,
            'unscored_frame_indices': sorted(set(frame_indices) - set(used)),
            'edge_policy': 'local_syncnet_range_usable_minus_5_final_frame_unused'}


def sync_coverage(source_frame_count, decoded_frame_count, detected_frame_indices, tracks, source_fps=25.0):
    """Separate source frames, actual detections and interpolated track boxes."""
    if (type(source_frame_count) is not int or source_frame_count <= 0
            or type(decoded_frame_count) is not int or decoded_frame_count < 0
            or not _number(source_fps) or source_fps <= 0 or not isinstance(tracks, list)):
        raise ValueError('Invalid source coverage')
    detected = _frames(detected_frame_indices, decoded_frame_count)
    tracked, track_detected = set(), set()
    for track in tracks:
        indices = _frames(track['frame_indices'], decoded_frame_count)
        actual = _frames(track['detected_frame_indices'], decoded_frame_count)
        if not actual <= indices or not actual <= detected:
            raise ValueError('Track detections must be actual detector frames inside the track')
        if track.get('interpolated_frame_indices') != sorted(indices - actual):
            raise ValueError('Interpolated frames cannot count as face detections')
        tracked.update(indices)
        track_detected.update(actual)
    expected = set(range(source_frame_count))
    return {'source_frame_count': source_frame_count, 'source_fps': source_fps,
            'decoded_frame_count': decoded_frame_count,
            'detected_frame_indices': sorted(detected), 'tracked_frame_indices': sorted(tracked),
            'track_detected_frame_indices': sorted(track_detected),
            'interpolated_frame_indices': sorted(tracked - track_detected),
            'missing_track_frame_indices': sorted(expected - tracked),
            'missing_detection_frame_indices': sorted(expected - track_detected),
            'fully_tracked': decoded_frame_count == source_frame_count and tracked == expected,
            'fully_detected': decoded_frame_count == source_frame_count and track_detected == expected}


def sync_scores_pass(tracks):
    """Every track must pass independently; opposite offsets never cancel."""
    return (isinstance(tracks, list) and bool(tracks)
            and all(isinstance(t, dict) and _number(t.get('confidence')) and t['confidence'] >= 3
                    and _number(t.get('offset_frames')) and abs(t['offset_frames']) <= 2
                    for t in tracks))


def sync_evidence_valid(receipt):
    """Whether stable input, exact coverage, and every track's score all pass."""
    try:
        if (not isinstance(receipt, dict) or receipt.get('version') != SYNC_SCREEN_VERSION
                or not _stable(receipt, 'video_sha256') or receipt.get('complete_clip') is not True
                or receipt.get('machine_screen_passed') is not True):
            return False
        tracks, coverage = receipt['tracks'], receipt['coverage']
        if not sync_scores_pass(tracks) or not isinstance(coverage, dict):
            return False
        if len({t['track_id'] for t in tracks}) != len(tracks):
            return False
        for track in tracks:
            frames = track['frame_indices']
            _frames(frames)
            if (len(frames) <= 50 or frames != list(range(frames[0], frames[-1] + 1))
                    or not _sha(track.get('crop_sha256')) or track.get('input_stable') is not True
                    or track.get('input_sha256_before') != track['crop_sha256']
                    or track.get('input_sha256_after') != track['crop_sha256']):
                return False
            window = track['model_window']
            if (window != sync_window_evidence(frames, track['crop_frame_count'], window['audio_frame_count'])
                    or window['audio_frame_count'] < len(frames) or window['window_count'] <= 0):
                return False
        expected = sync_coverage(coverage['source_frame_count'], coverage['decoded_frame_count'],
                                 coverage['detected_frame_indices'], tracks, coverage['source_fps'])
        return (coverage == expected and coverage['source_fps'] == 25
                and coverage['fully_tracked'] and coverage['fully_detected']
                and receipt.get('confidence') == min(t['confidence'] for t in tracks)
                and receipt.get('offset_frames') == max(tracks, key=lambda t: abs(t['offset_frames']))['offset_frames'])
    except (KeyError, TypeError, ValueError, IndexError):
        return False
