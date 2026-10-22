"""Render exact frozen public English lines using a local Kokoro checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_annotation400 import OUT, load, save, sha

GENERATOR_VERSION = 'local_kokoro_public_lines_v2'


def phoneme_results(pipeline, request, voice, repair):
    """Change specified pronunciations while keeping all input words frozen."""
    speed = repair.get('speed', request['speed'])
    assert .8 <= speed <= 1.15, 'Speech-rate correction is outside the supported range'
    replacements = repair.get('token_phonemes', {})
    if not replacements:
        yield from pipeline(request['source_public_response'], voice=voice, speed=speed)
        return
    _, tokens = pipeline.g2p(request['source_public_response'])
    matched = set()
    for token in tokens:
        if token.text in replacements:
            token.phonemes = replacements[token.text]
            matched.add(token.text)
    assert matched == set(replacements), ('Unmatched pronunciation overrides', set(replacements) - matched)
    yield from pipeline.generate_from_tokens(tokens, voice=voice, speed=speed)


def archive_previous_audio(target):
    if not target.exists():
        return
    directory = target.parent / 'audio_history' / sha(target)
    directory.mkdir(parents=True, exist_ok=True)
    for name in ['speech.wav', 'speech.json', 'audio_screen.json', 'audio_large_review.json']:
        source = target.with_name(name)
        destination = directory / name
        if source.exists() and not destination.exists():
            shutil.copy2(source, destination)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scene', nargs='*')
    p.add_argument('--location', nargs='*')
    p.add_argument('--node-id', nargs='*')
    p.add_argument('--repairs', type=Path, default=OUT / 'local_av/audio_repairs.json')
    a = p.parse_args()
    import numpy as np
    import soundfile as sf
    import torch
    from kokoro import KModel, KPipeline

    weights = ROOT / '.local_models/annotation400-kokoro'
    repairs = load(a.repairs).get('nodes', {}) if a.repairs.exists() else {}
    model_sha256 = sha(weights / 'kokoro-v1_0.pth')
    model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(weights / 'config.json'),
                   model=str(weights / 'kokoro-v1_0.pth')).to('cuda').eval()
    pipeline = KPipeline(lang_code='a', model=model, repo_id='hexgrad/Kokoro-82M')
    for row in load(OUT / 'local_av/manifest.json')['nodes']:
        if a.scene and row['scenario_id'] not in a.scene:
            continue
        if a.node_id and row['node_id'] not in a.node_id:
            continue
        request_path = ROOT / row['request_path']
        request = load(request_path)
        if a.location and request['location'] not in a.location:
            continue
        target = request_path.parent / 'speech.wav'
        receipt_path = target.with_suffix('.json')
        repair = repairs.get(request['node_id'], {})
        assert set(repair) <= {'reason', 'speed', 'token_phonemes'}, 'Unsupported audio correction'
        assert not repair or repair.get('reason'), 'Audio corrections require a recorded reason'
        voice_path = weights / 'voices' / (request['voice'] + '.pt')
        voice_sha256 = sha(voice_path)
        generation_spec = {'version': GENERATOR_VERSION, 'spec_sha256': request['spec_sha256'],
            'model_sha256': model_sha256, 'voice_sha256': voice_sha256,
            'speed': repair.get('speed', request['speed']), 'pronunciation_repair': repair}
        generation_sha256 = hashlib.sha256(json.dumps(generation_spec, sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if target.exists() and receipt_path.exists():
            old = load(receipt_path)
            if old['spec_sha256'] == request['spec_sha256'] and old['sha256'] == sha(target):
                if old.get('generation_sha256') == generation_sha256:
                    continue
                # Preserve unchanged original renders created before explicit repair keys.
                if not repair and not old.get('generation_sha256'):
                    continue
        voice = torch.load(voice_path, map_location='cpu', weights_only=True)
        parts, chunks = [], []
        for result in phoneme_results(pipeline, request, voice, repair):
            parts.append(result.audio.cpu().numpy())
            chunks.append({'text': result.graphemes, 'phonemes': result.phonemes})
        assert parts and all(len(x) > 0 for x in parts)
        # Natural lead/tail silence, plus short pauses at model chunk boundaries.
        sequence = [np.zeros(2400, dtype=np.float32)]
        for index, part in enumerate(parts):
            if index:
                sequence.append(np.zeros(3600, dtype=np.float32))
            sequence.append(part)
        sequence.append(np.zeros(4800, dtype=np.float32))
        audio = np.concatenate(sequence)
        archive_previous_audio(target)
        temporary = target.with_suffix('.tmp.wav')
        sf.write(temporary, audio, 24000, subtype='PCM_16')
        temporary.replace(target)
        save(receipt_path, {'spec_sha256': request['spec_sha256'], 'sha256': sha(target),
            'spoken_text': request['source_public_response'], 'speech_language': 'en',
            'model': 'hexgrad/Kokoro-82M', 'model_sha256': model_sha256,
            'voice': request['voice'], 'voice_sha256': voice_sha256,
            'speed': generation_spec['speed'], 'duration_seconds': len(audio) / 24000,
            'generation_sha256': generation_sha256, 'generation_spec': generation_spec,
            'chunks': chunks, 'human_review': 'pending', 'speech_verified': False})
        print(json.dumps({'node_id': request['node_id'], 'audio_seconds': round(len(audio)/24000, 2)}), flush=True)


if __name__ == '__main__':
    main()
