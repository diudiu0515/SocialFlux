"""Local AV screening keeps the original numeric guard and waits for final media."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_annotation400 import sha
from scripts.screen_annotation400_local_av import (
    critical_content_matches, legacy_critical_content_matches, ready_media,
)


class LocalScreenTests(unittest.TestCase):
    def test_dot_clock_stays_rejected_but_original_word_clock_passes(self):
        expected = "I'll send it by three-thirty, before four."
        self.assertFalse(legacy_critical_content_matches(expected, "I'll send it by 3.30, before 4."))
        self.assertFalse(critical_content_matches(expected, "I'll send it by 3.30, before 4."))
        self.assertTrue(critical_content_matches(expected, "I'LL SEND IT BY THREE THIRTY BEFORE FOUR"))

    def test_wrong_hour_minute_negation_and_extra_number_stay_rejected(self):
        expected = 'I will not send three copies by five-thirty, before six.'
        for observed in [
            'I will not send three copies by four thirty before six',
            'I will not send three copies by five forty before six',
            'I will send three copies by five thirty before six',
            'I will not send four copies by five thirty before six',
            'I will not send three copies by five thirty before six seven',
        ]:
            self.assertFalse(critical_content_matches(expected, observed), observed)

    def test_in_progress_or_stale_video_cannot_be_screened(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            request = {'spec_sha256': 'current-spec'}
            path.write_text(json.dumps(request))
            speech = path.with_name('speech.wav')
            speech.write_bytes(b'current audio')
            video = path.with_name('video.mp4')
            video.write_bytes(b'incomplete video')
            self.assertIsNotNone(ready_media(path, request, 'video')[2])
            receipt = path.with_name('video.json')
            record = {'spec_sha256': 'current-spec', 'sha256': sha(video), 'audio_sha256': sha(speech)}
            receipt.write_text(json.dumps(record))
            self.assertIsNone(ready_media(path, request, 'video')[2])
            video.write_bytes(b'changed or still muxing video')
            self.assertIsNotNone(ready_media(path, request, 'video')[2])
            record['sha256'] = sha(video)
            record['spec_sha256'] = 'old-spec'
            receipt.write_text(json.dumps(record))
            self.assertIsNotNone(ready_media(path, request, 'video')[2])
            record['spec_sha256'] = 'current-spec'
            record['audio_sha256'] = 'old-audio'
            receipt.write_text(json.dumps(record))
            self.assertIsNotNone(ready_media(path, request, 'video')[2])


if __name__ == '__main__':
    unittest.main()
