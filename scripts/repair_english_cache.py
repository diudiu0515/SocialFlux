"""Retranslate audited invalid cached strings, preserving all other staged content."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from scripts.localize_current_data import *
from collections import defaultdict


def repair(scene, keys, items):
    directory = STAGE / 'scenes' / scene
    rows = [i for i in items if i['story_id'] == scene]
    documents = {p: clean(load(ROOT / p)) for p in load(directory / 'status.json')['source_files']}
    original = {digest(s): s for s in strings({'items': rows, 'documents': documents})}
    cache = load(directory / 'cache.json')
    marker = directory / 'cache_repair.json'
    repaired = load(marker).get('hashes', []) if marker.exists() else []
    missing = [k for k in keys if k not in repaired]
    provider = provider_for(0) if missing else None
    while missing:
        batch, size = [], 0
        while missing and (not batch or size + len(original[missing[0]]) < 2500):
            key = missing.pop(0)
            batch.append(key)
            size += len(original[key])
        def validate(value):
            result = value.get('translations') if isinstance(value, dict) else None
            if not isinstance(result, list) or len(result) != len(batch):
                raise ValueError('Translation count changed')
            for key, target in zip(batch, result):
                try:
                    same_structure(original[key], target)
                except AssertionError as exc:
                    raise ValueError(str(exc)) from exc
            return value
        result = complete_json(provider, [
            {'role': 'system', 'content': PROMPT + '\nTranslate each quoted string itself; do not answer it or replace a short quotation with a larger utterance or dialogue.'},
            {'role': 'user', 'content': json.dumps({'texts': [original[k] for k in batch]}, ensure_ascii=False)},
        ], {'temperature': 0, 'max_tokens': 6000}, validate, context='Repair invalid legacy translation cache', max_attempts=3)
        cache.update(zip(batch, result['translations']))
        repaired.extend(batch)
        atomic_json(directory / 'cache.json', cache)
        atomic_json(marker, {'hashes': repaired, 'semantic_equivalence_review': 'pending'})
    mapping = {key: cache[key] for key in keys}
    def patch(before, after):
        if isinstance(before, str):
            return mapping.get(digest(before), after)
        if isinstance(before, dict):
            return {k: patch(v, after[k]) for k, v in before.items()}
        if isinstance(before, list):
            return [patch(a, b) for a, b in zip(before, after)]
        return after
    atomic_json(directory / 'items.json', patch(rows, load(directory / 'items.json')))
    for path, source in documents.items():
        atomic_json(STAGE / 'files' / path, patch(source, clean(load(STAGE / 'files' / path))))
    return {'scene': scene, 'repaired': len(keys)}


if __name__ == '__main__':
    items = [json.loads(s) for s in (BANK / 'items.jsonl').read_text().splitlines() if s]
    groups = defaultdict(list)
    for row in load(STAGE / 'invalid_cached_utterances.json'):
        groups[row['scene']].append(row['hash'])
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(repair, scene, keys, items) for scene, keys in groups.items()]
        for f in as_completed(futures):
            print(json.dumps(f.result()), flush=True)
