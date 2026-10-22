"""Local, unprompted CTC transcription; the recognizer never receives a target line."""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import sha

REPO = 'facebook/wav2vec2-large-960h-lv60-self'
VERSION = 'local_ctc_greedy_unprompted_v1'


class CTCTranscriber:
    def __init__(self, device='cpu'):
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        self.torch = torch
        self.device = device
        self.lock = threading.Lock()
        self.directory = ROOT / '.local_models/annotation400-asr-ctc'
        weights = self.directory / 'pytorch_model.bin'
        self.weight_sha256 = sha(weights)
        if device == 'cuda':
            # This job shares its 48 GB GPU with the existing lip-sync worker.
            torch.cuda.set_per_process_memory_fraction(.20)
        self.processor = Wav2Vec2Processor.from_pretrained(self.directory, local_files_only=True)
        self.model = Wav2Vec2ForCTC.from_pretrained(self.directory,
            local_files_only=True).to(device).eval()

    def transcribe(self, media):
        from faster_whisper.audio import decode_audio
        # The same decoder accepts a WAV file or the audio stream of an MP4.
        audio = decode_audio(str(media), sampling_rate=16000)
        with self.lock, self.torch.inference_mode():
            inputs = self.processor(audio, sampling_rate=16000,
                return_tensors='pt', padding=True).to(self.device)
            logits = self.model(**inputs).logits
            ids = self.torch.argmax(logits, dim=-1)
            transcript = self.processor.batch_decode(ids)[0]
        return {'model': 'wav2vec2-large-960h-lv60-self',
            'checkpoint_repo': REPO, 'checkpoint_sha256': self.weight_sha256,
            'transcript': transcript, 'language': 'en',
            'language_source': 'english_only_checkpoint', 'device': self.device,
            'compute_type': 'float32', 'decoder': 'greedy_argmax_no_lm_no_prompt',
            'unprompted': True, 'version': VERSION}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--media', nargs='+', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    model = CTCTranscriber(args.device)
    for media in args.media:
        print(json.dumps({'media': str(media), 'sha256': sha(media),
            **model.transcribe(media)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
